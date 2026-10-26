"""The second connection's build: plan, files, repair, and the capture pool."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import builder


class FakeChat:
    def __init__(self, replies: list[dict]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.model = "fake-builder-30b"
        self.url = "http://example/v1"

    def ask(self, system: str, user: str) -> dict:
        self.prompts.append(user)
        reply = self.replies.pop(0)
        return {"content": reply.get("content", ""), "reasoning": reply.get("reasoning", ""),
                "model": self.model, "usage": {}, "seconds": 0.1}


PLAN = json.dumps({
    "plan": "one file, print the numbers",
    "files": [{"path": "main.py", "purpose": "entry"}],
    "entry": "main.py", "run": "python3 main.py", "expected_stdout": "42"})
FILES = """FILE: main.py
```python
def main():
    print(42)


if __name__ == "__main__":
    main()
```"""


class ParseTests(unittest.TestCase):
    def test_a_plan_survives_fences_and_chatter(self) -> None:
        reply = "Sure, here it is:\n```json\n" + PLAN + "\n```"
        plan = builder.parse_plan(reply)
        self.assertEqual(plan["entry"], "main.py")
        self.assertEqual(plan["files"][0]["path"], "main.py")

    def test_file_blocks_keep_their_paths_and_contents(self) -> None:
        files = builder.parse_files(FILES, "python")
        self.assertEqual([f["path"] for f in files], ["main.py"])
        self.assertIn("print(42)", files[0]["content"])

    def test_several_files_are_split_on_their_markers(self) -> None:
        reply = ("FILE: a.py\n```python\nx = 1\n```\n\n"
                 "FILE: b.py\n```python\ny = 2\n```\n")
        files = builder.parse_files(reply, "python")
        self.assertEqual([f["path"] for f in files], ["a.py", "b.py"])
        self.assertIn("y = 2", files[1]["content"])
        self.assertNotIn("FILE:", files[0]["content"])

    def test_a_reply_without_markers_falls_back_to_the_planned_path(self) -> None:
        files = builder.parse_files("```python\nprint(1)\n```", "python",
                                    [{"path": "main.py"}])
        self.assertEqual(files[0]["path"], "main.py")

    def test_no_files_at_all_is_empty_not_a_crash(self) -> None:
        self.assertEqual(builder.parse_files("I cannot help with that.", "python"), [])


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self.restore)
        self.spec = {"id": "app/one", "language": "python",
                     "brief": "print the answer"}

    def restore(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev

    def test_a_good_build_is_captured_with_plan_reasoning_and_files(self) -> None:
        chat = FakeChat([{"content": PLAN, "reasoning": "the brief is trivial"},
                         {"content": FILES, "reasoning": "one function"}])
        with mock.patch.object(builder, "_run",
                               return_value=mock.Mock(ok=True, stdout="42\n",
                                                      error="", stderr="",
                                                      command="python3 main.py",
                                                      exit_code=0)):
            record = builder.build_app(self.spec, chat=chat)
        self.assertTrue(record["ok"])
        self.assertEqual(record["model"], "fake-builder-30b")
        self.assertEqual(record["label"], "fake-builder-30b")
        self.assertEqual(record["files"][0]["path"], "main.py")
        self.assertEqual(record["attempts"][0]["plan_reasoning"], "the brief is trivial")
        self.assertEqual(record["attempts"][0]["files_reasoning"], "one function")
        self.assertEqual(record["runs"], 1)
        self.assertTrue(record["sha256"])

    def test_a_failed_build_is_repaired_with_the_toolchains_words(self) -> None:
        chat = FakeChat([{"content": PLAN}, {"content": FILES},
                         {"content": PLAN}, {"content": FILES}])
        failed = mock.Mock(ok=False, stdout="", stderr="SyntaxError: bad", error="",
                           command="python3 main.py", exit_code=1)
        passed = mock.Mock(ok=True, stdout="42\n", stderr="", error="",
                           command="python3 main.py", exit_code=0)
        with mock.patch.object(builder, "_run", side_effect=[failed, passed]):
            record = builder.build_app(self.spec, chat=chat, attempts=2)
        self.assertTrue(record["ok"])
        self.assertEqual(record["runs"], 2)
        self.assertIn("SyntaxError", chat.prompts[3])
        self.assertEqual(record["attempts"][0]["build"]["ok"], False)

    def test_an_unreachable_builder_is_recorded_not_raised(self) -> None:
        chat = mock.Mock()
        chat.model = "fake-builder-30b"
        chat.url = "http://example/v1"
        chat.ask.side_effect = builder.BuilderError("connection refused")
        record = builder.build_app(self.spec, chat=chat)
        self.assertFalse(record["ok"])
        self.assertIn("connection refused", record["error"])

    def test_the_pool_is_labelled_per_model_and_deduped(self) -> None:
        record = {"label": "fake-builder-30b", "task": {"id": "app/one"},
                  "sha256": "abc", "ok": True, "files": [{"path": "main.py"}],
                  "runs": 1}
        first = builder.write_pool([record])
        second = builder.write_pool([record])
        self.assertEqual(first["added"], 1)
        self.assertEqual(second["added"], 0)
        summary = builder.index()
        self.assertEqual(summary["models"]["fake-builder-30b"]["apps"], 1)

    def test_two_models_make_two_pools_side_by_side(self) -> None:
        for label in ("builder-30b", "builder-7b"):
            builder.write_pool([{"label": label, "task": {"id": "app/one",
                                                          "language": "python"},
                                 "sha256": label, "ok": True, "files": [],
                                 "runs": 1}])
        models = builder.index()["models"]
        self.assertEqual(sorted(models), ["builder-30b", "builder-7b"])

    def test_dependencies_are_extracted_from_the_answer(self) -> None:
        files = [{"path": "main.go",
                  "content": 'package main\n\nimport (\n\t"sort"\n)\n\nfunc main() {}\n'}]
        deps = builder._dependencies(files)
        self.assertEqual(deps["main.go"], ["sort"])


class MarkerStyleTests(unittest.TestCase):
    def test_heading_markers_are_read_as_files(self) -> None:
        reply = ("### main.py\n```python\nprint(1)\n```\n\n"
                 "### util.py\n```python\nX = 2\n```\n")
        files = builder.parse_files(reply, "python")
        self.assertEqual([f["path"] for f in files], ["main.py", "util.py"])

    def test_a_bold_path_marker_is_read(self) -> None:
        reply = "**main.py**\n```python\nprint(2)\n```\n"
        files = builder.parse_files(reply, "python")
        self.assertEqual(files[0]["path"], "main.py")

    def test_fences_never_land_in_the_file(self) -> None:
        reply = "FILE: main.py\n```python\nprint(3)\n```\n"
        content = builder.parse_files(reply, "python")[0]["content"]
        self.assertEqual(content, "print(3)\n")
        self.assertNotIn("```", content)

    def test_a_whole_answer_wrapped_in_one_fence_is_cleaned(self) -> None:
        self.assertEqual(builder.clean_block("```python\nx = 1\n```\n"), "x = 1\n")


class ArgsTests(unittest.TestCase):
    def test_the_plans_invocation_supplies_the_arguments(self) -> None:
        self.assertEqual(builder.args_from_run("python3 main.py 3+4*(2-1)", "main.py"),
                         ["3+4*(2-1)"])
        self.assertEqual(builder.args_from_run("go run main.go --count 5", "main.go"),
                         ["--count", "5"])
        self.assertEqual(builder.args_from_run("python3 main.py", "main.py"), [])
        self.assertEqual(builder.args_from_run("", "main.py"), [])
        self.assertEqual(builder.args_from_run('python3 "a b.py" x', "a b.py"), ["x"])


if __name__ == "__main__":
    unittest.main()


class SpecTests(unittest.TestCase):
    def test_an_explicit_brief_is_one_app_in_the_first_lane(self) -> None:
        specs = builder.specs_from_library(["go", "python"], 3, "print hello")
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["language"], "go")
        self.assertEqual(specs[0]["id"], "brief/0")

    def test_a_brief_with_no_lane_is_python(self) -> None:
        self.assertEqual(builder.specs_from_library([], 1, "x")[0]["language"], "python")

    def test_no_brief_falls_back_to_the_library_apps(self) -> None:
        specs = builder.specs_from_library(["python"], 2)
        self.assertTrue(specs)
        self.assertLessEqual(len(specs), 2)
        self.assertTrue(all(s["source"] == "library" for s in specs))

    def test_a_lane_with_no_library_apps_is_no_specs(self) -> None:
        self.assertEqual(builder.specs_from_library(["cobol"], 3), [])


class SeriesJobTests(unittest.TestCase):
    """The job the app starts, watched through `status`."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self.restore)
        builder.JOB.update({"state": "idle", "error": "", "records": [], "apps": 0,
                            "done": 0, "current": "", "model": "", "scaffold": {}})

    def restore(self) -> None:
        builder.JOB.update({"state": "idle", "error": "", "records": []})
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev

    def test_a_series_writes_the_pool_after_each_app(self) -> None:
        record = {"ok": True, "runs": 1, "files": [{"path": "main.py"}],
                  "conventions": True, "at": "now"}
        specs = [{"id": f"app/{n}", "language": "python", "brief": "b"} for n in (1, 2)]
        with mock.patch.object(builder, "specs_from_library", return_value=specs), \
             mock.patch.object(builder, "chat_for",
                               return_value=mock.Mock(model="fake-7b")), \
             mock.patch.object(builder, "build_app", return_value=record) as build, \
             mock.patch.object(builder, "write_pool", return_value={"added": 1}) as pool:
            started = builder.start(brief="b")
            self.assertEqual(started["state"], "running")
            self.assertEqual(started["model"], "fake-7b")
            builder._THREAD.join(timeout=5)
        self.assertEqual(build.call_count, 2)
        self.assertEqual(pool.call_count, 2)
        final = builder.status()
        self.assertEqual(final["state"], "done")
        self.assertEqual(final["done"], 2)
        self.assertEqual([r["id"] for r in final["records"]], ["app/1", "app/2"])
        self.assertTrue(final["records"][0]["conventions"])
        self.assertTrue(builder.status_path().exists())

    def test_a_second_series_is_refused_while_one_runs(self) -> None:
        builder.JOB["state"] = "running"
        with mock.patch.object(builder, "specs_from_library",
                               return_value=[{"id": "a", "language": "python"}]):
            result = builder.start(brief="b")
        self.assertIn("already running", result["error"])

    def test_an_unknown_connection_is_refused_not_guessed(self) -> None:
        with mock.patch.object(builder, "specs_from_library",
                               return_value=[{"id": "a", "language": "python"}]):
            result = builder.start(brief="b", connection="not-a-connection")
        self.assertIn("no connection named", result["error"])
        self.assertNotEqual(builder.JOB["state"], "running")

    def test_a_build_that_raises_fails_the_job_with_its_words(self) -> None:
        specs = [{"id": "app/1", "language": "python", "brief": "b"}]
        with mock.patch.object(builder, "specs_from_library", return_value=specs), \
             mock.patch.object(builder, "chat_for",
                               return_value=mock.Mock(model="fake-7b")), \
             mock.patch.object(builder, "build_app",
                               side_effect=RuntimeError("model went away")):
            builder.start(brief="b")
            builder._THREAD.join(timeout=5)
        final = builder.status()
        self.assertEqual(final["state"], "failed")
        self.assertIn("model went away", final["error"])

    def test_the_last_finished_run_survives_a_restart(self) -> None:
        builder._publish(state="done", apps=3, done=3, model="fake-7b", records=[])
        builder.JOB.update({"state": "idle", "records": []})
        restored = builder.status()
        self.assertEqual(restored["state"], "done")
        self.assertEqual(restored["done"], 3)
