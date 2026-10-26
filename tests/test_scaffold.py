"""Scaffolding reasoning copied from the other connections into prompt text."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

from trainapp import builder, scaffold


def record(model: str, language: str, paths: list[str], plan_text: str = "",
           built: bool = True, entry: str = "main.py",
           run: str = "python3 main.py", purposes: dict | None = None) -> dict:
    """One pool record, in the shape `builder.build_app` captures."""
    purposes = purposes or {}
    plan = {"plan": plan_text,
            "files": [{"path": p, "purpose": purposes.get(p, "")} for p in paths],
            "entry": entry, "run": run}
    return {
        "label": model, "model": model, "ok": built, "sha256": f"{model}-{built}",
        "task": {"id": f"{language}/{model}", "language": language,
                 "brief": "build something"},
        "files": [{"path": p, "content": ""} for p in paths],
        "attempts": [{"n": 1, "plan_reply": json.dumps(plan), "plan_reasoning": "",
                      "build": {"ok": built}}],
    }


class NoteTests(unittest.TestCase):
    def test_one_note_per_model_not_per_app(self) -> None:
        pool = scaffold.notes([
            record("model-a", "python", ["main.py"], "one file"),
            record("model-a", "python", ["main.py"], "one file again"),
            record("model-b", "python", ["app.py", "util.py"], "two files"),
        ])
        self.assertEqual([r["model"] for r in pool["python"]], ["model-a", "model-b"])
        self.assertEqual(len(pool["python"]), 2)

    def test_the_latest_build_replaces_an_earlier_one(self) -> None:
        pool = scaffold.notes([
            record("model-a", "python", ["main.py"], "one file", built=True),
            record("model-a", "python", ["main.py", "store.py", "task.py"],
                   "three files now", built=True),
        ])
        self.assertEqual(pool["python"][0]["layout"],
                         ["main.py", "store.py", "task.py"])
        self.assertEqual(pool["python"][0]["reasoning"], "three files now")

    def test_a_failure_after_a_build_does_not_replace_it(self) -> None:
        pool = scaffold.notes([
            record("model-a", "go", ["main.go", "stack.go"], built=True),
            record("model-a", "go", ["broken.go"], built=False),
        ])
        self.assertTrue(pool["go"][0]["built"])
        self.assertEqual(pool["go"][0]["layout"], ["main.go", "stack.go"])

    def test_a_model_that_built_outranks_the_same_models_failure(self) -> None:
        pool = scaffold.notes([
            record("model-a", "go", ["broken.go"], built=False),
            record("model-a", "go", ["main.go", "store.go"], built=True),
        ])
        self.assertTrue(pool["go"][0]["built"])
        self.assertEqual(pool["go"][0]["layout"][0], "main.go")

    def test_planned_purposes_are_kept_with_the_path(self) -> None:
        pool = scaffold.notes([record("model-a", "python", ["main.py", "store.py"],
                                      purposes={"main.py": "entry point"})])
        self.assertEqual(pool["python"][0]["layout"],
                         ["main.py — entry point", "store.py"])

    def test_config_files_are_separated_from_source(self) -> None:
        pool = scaffold.notes([record("model-a", "typescript",
                                      ["src/app.ts", "tsconfig.json", "package.json"])])
        self.assertNotIn("python", pool)
        self.assertEqual(pool["typescript"][0]["config"], ["tsconfig.json", "package.json"])

    def test_a_record_with_no_files_contributes_nothing(self) -> None:
        empty = record("model-a", "rust", [], entry="main.rs")
        self.assertEqual(scaffold.notes([empty]), {})


class SectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pool = scaffold.notes([
            record("model-a", "python", ["main.py"], "a single file is enough",
                   entry="main.py", run="python3 main.py"),
            record("model-b", "python", ["app.py", "store.py"],
                   "split storage out of the entry", entry="app.py",
                   run="python3 app.py", built=False),
        ])

    def test_both_connections_appear_with_their_own_layouts(self) -> None:
        body = scaffold.section("python", self.pool)
        self.assertIn("model-a (built): main.py", body)
        self.assertIn("model-b (did not build): app.py | store.py", body)

    def test_the_models_own_words_are_copied_verbatim(self) -> None:
        body = scaffold.section("python", self.pool)
        self.assertIn('it said: "a single file is enough"', body)
        self.assertIn("split storage out of the entry", body)

    def test_the_entry_and_invocation_travel_with_the_layout(self) -> None:
        body = scaffold.section("python", self.pool)
        self.assertIn("entry app.py; run `python3 app.py`", body)

    def test_a_lane_no_connection_has_built_has_no_section(self) -> None:
        self.assertEqual(scaffold.section("ruby", self.pool), "")
        self.assertEqual(scaffold.prompt_block("ruby", self.pool), "")

    def test_the_prompt_block_says_what_to_do_with_the_section(self) -> None:
        block = scaffold.prompt_block("python", self.pool)
        self.assertIn("Other connected models have already laid out python apps", block)
        self.assertIn("Follow the conventions that built", block)
        self.assertTrue(block.endswith("\n"))

    def test_a_wrong_convention_is_attributed_to_the_model_that_shipped_it(self) -> None:
        body = scaffold.section("python", self.pool)
        unbuilt = body[body.index("model-b"):]
        self.assertIn("did not build", unbuilt.splitlines()[0])


class PromptTests(unittest.TestCase):
    """The copy is only worth anything if the plan prompt actually carries it."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self.restore)
        self.spec = {"id": "app/one", "language": "python", "brief": "print 42"}

    def restore(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev

    def _chat(self) -> mock.Mock:
        chat = mock.Mock()
        chat.model = "builder-30b"
        chat.url = "http://example/v1"
        chat.ask.side_effect = [
            {"content": json.dumps({"plan": "one file", "files": [{"path": "main.py"}],
                                    "entry": "main.py", "run": "python3 main.py"}),
             "reasoning": "", "seconds": 0.1, "usage": {}},
            {"content": "FILE: main.py\n```python\nprint(42)\n```", "reasoning": "",
             "seconds": 0.1, "usage": {}},
        ]
        return chat

    def _run_ok(self):
        return mock.Mock(ok=True, stdout="42\n", stderr="", error="",
                         command="python3 main.py", exit_code=0)

    def test_the_plans_prompt_carries_the_copied_conventions(self) -> None:
        chat = self._chat()
        with mock.patch.object(scaffold, "prompt_block",
                               return_value="\n- model-a (built): main.py\n"), \
             mock.patch.object(builder, "_run", return_value=self._run_ok()):
            result = builder.build_app(self.spec, chat=chat)
        self.assertIn("model-a (built): main.py", chat.ask.call_args_list[0].args[1])
        self.assertTrue(result["conventions"])

    def test_an_empty_lane_sends_the_prompt_it_always_did(self) -> None:
        chat = self._chat()
        with mock.patch.object(scaffold, "prompt_block", return_value=""), \
             mock.patch.object(builder, "_run", return_value=self._run_ok()):
            result = builder.build_app(self.spec, chat=chat)
        prompt = chat.ask.call_args_list[0].args[1]
        self.assertNotIn("Other connected models", prompt)
        self.assertIn("Brief: print 42", prompt)
        self.assertFalse(result["conventions"])


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self.restore)

    def restore(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev

    def test_the_snapshot_round_trips_without_the_pool(self) -> None:
        with mock.patch.object(scaffold, "notes",
                               return_value={"python": [{"model": "model-a",
                                                         "layout": ["main.py"],
                                                         "built": True, "entry": "",
                                                         "run": "", "config": [],
                                                         "reasoning": ""}]}):
            written = scaffold.write()
        self.assertEqual(written["languages"], ["python"])
        self.assertEqual(scaffold.read()["python"][0]["model"], "model-a")
        self.assertEqual(scaffold.read()["python"][0]["layout"], ["main.py"])

    def test_a_missing_snapshot_is_empty_not_an_error(self) -> None:
        self.assertEqual(scaffold.read(), {})


if __name__ == "__main__":
    unittest.main()


class ExecutedCommandTests(unittest.TestCase):
    """What the harness ran is evidence; the plan's `run` is only intent."""

    def test_paths_are_trimmed_to_names(self) -> None:
        self.assertEqual(
            scaffold.short_command("/home/x/node_modules/.bin/tsx src/index.ts"),
            "tsx src/index.ts")

    def test_the_harness_scratch_binary_says_nothing(self) -> None:
        self.assertEqual(scaffold.short_command("/tmp/vaca-set-abc/.node-bin"), "")

    def test_a_disagreement_is_shown_beside_the_plan(self) -> None:
        row = record("model-a", "typescript", ["src/index.ts"],
                     entry="src/index.ts", run="tsc && node dist/index.js")
        row["build"] = {"ok": True, "command": "/home/x/npm/.bin/tsx src/index.ts"}
        body = scaffold.section("typescript", scaffold.notes([row]))
        self.assertIn("run `tsc && node dist/index.js`", body)
        self.assertIn("the harness ran `tsx src/index.ts`", body)

    def test_agreement_is_not_repeated(self) -> None:
        row = record("model-a", "php", ["squares.php"], entry="squares.php",
                     run="php squares.php")
        row["build"] = {"ok": True, "command": "/usr/local/bin/php squares.php"}
        body = scaffold.section("php", scaffold.notes([row]))
        self.assertNotIn("the harness ran", body)
