"""The overnight loop: resumable, stoppable, and honest about what it produced."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import overnight, repair


def python_set(task_id: str = "probe/set-1") -> dict:
    return {
        "id": task_id,
        "language": "python",
        "target": "main.py",
        "title": "print twice a number",
        "files": [
            {"path": "main.py",
             "content": ("from util import double\n\n\n"
                         "def greet(name):\n"
                         "    return 'hi ' + name\n\n\n"
                         "def main():\n"
                         "    print(greet('bob'), double(21))\n\n\n"
                         "if __name__ == '__main__':\n"
                         "    main()\n")},
            {"path": "util.py", "content": "def double(n):\n    return n * 2\n"},
        ],
    }


ORIGINAL = "def greet(name):\n    return 'hi ' + name"


class FakeClient:
    def __init__(self, reply: str = ORIGINAL, on_call=None) -> None:
        self.reply = reply
        self.on_call = on_call
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.on_call:
            self.on_call()
        return self.reply


class DeadClient:
    def complete(self, prompt: str) -> str:
        raise repair.LLMError("LLM unreachable at http://127.0.0.1:11434")


class TempDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self.restore_env)
        self.root = Path(self.tmp.name) / "runs"
        overnight.clear_stop()

    def restore_env(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev

    def read(self, *parts: str) -> list[dict]:
        path = self.root.joinpath(*parts)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class RunTests(TempDataTest):
    def test_a_passing_function_is_kept_and_exported(self) -> None:
        result = overnight.run(hours=0, rounds=1, root=self.root,
                               client=FakeClient(), tasks=[python_set()])
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["match"], 1)
        self.assertEqual(result["export"]["sft_rows"], 1)
        sft = self.read("export", "sft.jsonl")
        self.assertEqual(len(sft), 1)
        self.assertIn("def greet(name):", sft[0]["output"])
        self.assertEqual(sft[0]["instruction"].startswith("Write ONLY this function"),
                         True)

    def test_status_file_reports_progress_without_the_process(self) -> None:
        overnight.run(hours=0, rounds=1, root=self.root,
                      client=FakeClient("def greet(name):\n    return 2\n"),
                      tasks=[python_set()])
        status = json.loads(overnight.status_path().read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "done")
        self.assertEqual(status["attempts"], 1)
        self.assertEqual(status["match"], 0)
        self.assertEqual(status["round"], 1)
        self.assertIn("finished_at", status)

    def test_failures_are_kept_with_their_error(self) -> None:
        overnight.run(hours=0, rounds=1, root=self.root,
                      client=FakeClient("def greet(name)\n    return 1\n"),
                      tasks=[python_set()])
        paths = list(self.root.rglob("failures.jsonl"))
        self.assertEqual(len(paths), 1)
        failures = [json.loads(line) for line in
                    paths[0].read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(failures), 1)
        self.assertFalse(failures[0]["compile"])
        self.assertTrue(failures[0]["error"])

    def test_a_restart_skips_sets_the_round_already_did(self) -> None:
        task = python_set()
        overnight.run(hours=0, rounds=1, root=self.root, client=FakeClient(),
                      tasks=[task])
        second = overnight.run(hours=0, rounds=1, root=self.root,
                               client=FakeClient(), tasks=[task])
        self.assertEqual(second["attempts"], 0)
        self.assertEqual(second["state"], "done")

    def test_the_stop_file_ends_the_run_between_attempts(self) -> None:
        def stop_after_first() -> None:
            overnight.request_stop()

        result = overnight.run(hours=0, rounds=1, root=self.root,
                               client=FakeClient(on_call=stop_after_first),
                               tasks=[python_set("probe/a"), python_set("probe/b")])
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(result["attempts"], 1)

    def test_a_dead_model_ends_the_night_instead_of_spinning(self) -> None:
        result = overnight.run(hours=0, rounds=1, root=self.root, client=DeadClient(),
                               tasks=[python_set()], max_errors=1, retries=0)
        self.assertEqual(result["state"], "failed")
        self.assertIn("unreachable", result["error"])
        errors = [p for p in self.root.rglob("errors.jsonl")]
        self.assertEqual(len(errors), 1)

    def test_a_later_round_makes_a_pair_not_another_sft_row(self) -> None:
        class Mixed(FakeClient):
            def __init__(self) -> None:
                super().__init__(ORIGINAL)
                self.calls = 0

            def complete(self, prompt: str) -> str:
                self.calls += 1
                return ORIGINAL if self.calls == 1 else "def greet(name):\n    return 2"

        result = overnight.run(hours=0, rounds=2, root=self.root, client=Mixed(),
                               tasks=[python_set()])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["match"], 1)
        # Different rounds start at different points, so one set is enough for both.
        self.assertEqual(result["export"]["sft_rows"], 1)
        self.assertEqual(result["export"]["pair_rows"], 1)
        pair = self.read("export", "pairs.jsonl")[0]
        self.assertIn("hi", pair["chosen"])
        self.assertIn("return 2", pair["rejected"])


class SamplingTests(TempDataTest):
    def test_samples_ask_the_same_prompt_more_than_once(self) -> None:
        result = overnight.run(hours=0, rounds=1, samples=3, root=self.root,
                               client=FakeClient(), tasks=[python_set()])
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["match"], 3)
        # Three identical passes are one demonstration, not three.
        self.assertEqual(result["export"]["sft_rows"], 1)

    def two_function_set(self) -> dict:
        return {"id": "probe/two", "language": "python", "target": "main.py",
                "title": "sum and render",
                "files": [
                    {"path": "main.py",
                     "content": ("from util import scale\n\n\n"
                                 "def total(items):\n"
                                 "    out = 0\n"
                                 "    for item in items:\n"
                                 "        out += item\n"
                                 "    return out\n\n\n"
                                 "def render(items):\n"
                                 "    value = total(items)\n"
                                 "    label = 'total'\n"
                                 "    print(label, scale(value))\n\n\n"
                                 "if __name__ == '__main__':\n"
                                 "    render([1, 2])\n")},
                    {"path": "util.py", "content": "def scale(n):\n    return n * 2\n"},
                ]}

    def test_every_function_is_a_separate_prompt(self) -> None:
        result = overnight.run(hours=0, rounds=1, all_functions=True, root=self.root,
                               client=FakeClient(),
                               tasks=[self.two_function_set()])
        self.assertEqual(result["attempts"], 2)
        rows = [json.loads(line) for line in
                list(self.root.rglob("failures.jsonl"))[0].read_text().splitlines()]
        self.assertEqual(sorted(r["key"] for r in rows),
                         ["probe/two#0", "probe/two#1"])

    def test_resume_skips_each_function_it_already_asked(self) -> None:
        task = python_set()
        overnight.run(hours=0, rounds=1, all_functions=True, root=self.root,
                      client=FakeClient(), tasks=[task])
        again = overnight.run(hours=0, rounds=1, all_functions=True, root=self.root,
                              client=FakeClient(), tasks=[task])
        self.assertEqual(again["attempts"], 0)


class JudgeableTests(TempDataTest):
    def silent_set(self) -> dict:
        return {"id": "probe/silent", "language": "python", "target": "main.py",
                "title": "renders nothing",
                "files": [{"path": "main.py",
                           "content": ("def render():\n    return 'x'\n\n\n"
                                       "if __name__ == '__main__':\n    render()\n")}]}

    def test_a_set_whose_behaviour_is_invisible_is_dropped_before_any_model_call(self) -> None:
        client = FakeClient()
        result = overnight.run(hours=0, rounds=1, root=self.root, client=client,
                               tasks=[python_set(), self.silent_set()])
        self.assertEqual(result["unjudgeable"], 1)
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(client.calls, 1)

    def test_compile_only_sets_are_opt_in(self) -> None:
        result = overnight.run(hours=0, rounds=1, root=self.root,
                               client=FakeClient(),
                               tasks=[python_set(), self.silent_set()],
                               judgeable_only=False)
        self.assertEqual(result["unjudgeable"], 0)
        self.assertEqual(result["attempts"], 2)


class ExportLoadTests(TempDataTest):
    def write_export(self, sft: list[dict], pairs: list[dict]) -> None:
        out = self.root / "export"
        out.mkdir(parents=True, exist_ok=True)
        (out / "sft.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in sft), encoding="utf-8")
        (out / "pairs.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in pairs), encoding="utf-8")

    def test_a_night_without_an_export_is_empty_not_an_error(self) -> None:
        loaded = overnight.load_export(self.root)
        self.assertEqual(loaded, {"sft": [], "pairs": [], "summary": {}})

    def test_only_complete_rows_are_loaded(self) -> None:
        self.write_export(
            [{"instruction": "i", "input": "n", "output": "code\n"},
             {"instruction": "i", "output": ""}],
            [{"prompt": "p", "chosen": "a\n", "rejected": "b\n"},
             {"prompt": "p", "chosen": "a\n"}])
        loaded = overnight.load_export(self.root)
        self.assertEqual(len(loaded["sft"]), 1)
        self.assertEqual(len(loaded["pairs"]), 1)


class SliceTests(TempDataTest):
    def test_an_offset_starts_into_the_pool(self) -> None:
        result = overnight.run(hours=0, rounds=1, offset=1, root=self.root,
                               client=FakeClient(), tasks=[python_set("probe/a"),
                                                           python_set("probe/b")])
        self.assertEqual(result["attempts"], 1)
        status = json.loads(overnight.status_path().read_text(encoding="utf-8"))
        self.assertEqual(status["last"], "probe/b")

    def test_a_limited_round_asks_the_same_sets_next_round(self) -> None:
        class Mixed(FakeClient):
            def __init__(self) -> None:
                super().__init__(ORIGINAL)
                self.calls = 0

            def complete(self, prompt: str) -> str:
                self.calls += 1
                return ORIGINAL if self.calls in (1, 2) else "def greet(name):\n    return 2"

        tasks = [python_set("probe/a"), python_set("probe/b"), python_set("probe/c")]
        result = overnight.run(hours=0, rounds=2, limit=2, root=self.root,
                               client=Mixed(), tasks=tasks)
        # Round 1 {a,b} passes, round 2 {b,c} re-asks b and finds a failure for it.
        self.assertEqual(result["attempts"], 4)
        self.assertGreaterEqual(result["export"]["pair_rows"], 1)


class StatusTests(TempDataTest):
    def test_running_checks_the_process_not_just_the_word(self) -> None:
        overnight.publish(state="running", pid=os.getpid())
        self.assertTrue(overnight.running())
        overnight.publish(state="running", pid=999999)
        self.assertFalse(overnight.running())
        overnight.publish(state="done", pid=os.getpid())
        self.assertFalse(overnight.running())

    def test_a_restart_does_not_inherit_the_last_runs_totals(self) -> None:
        overnight.publish(state="done", finished_at="old", export={"sft_rows": 9},
                          attempts=99)
        overnight.run(hours=0, rounds=1, root=self.root, client=FakeClient(),
                      tasks=[python_set()])
        status = json.loads(overnight.status_path().read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "done")
        self.assertEqual(status["attempts"], 1)
        self.assertNotEqual(status["finished_at"], "old")


class RotationTests(unittest.TestCase):
    def test_each_round_starts_where_the_last_ended(self) -> None:
        tasks = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        self.assertEqual([t["id"] for t in overnight.rotated(tasks, 1)], ["a", "b", "c"])
        self.assertEqual([t["id"] for t in overnight.rotated(tasks, 2)], ["b", "c", "a"])
        self.assertEqual(overnight.rotated([], 3), [])


class ColdFirstTests(TempDataTest):
    def write_round(self, rows: list[dict]) -> None:
        directory = self.root / "20260101T000000"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "samples.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def test_a_short_night_probes_what_no_night_has_measured(self) -> None:
        self.write_round([{"task_id": "a", "match": True},
                          {"task_id": "b", "match": False}])
        pool = [{"id": tid} for tid in ("a", "b", "c", "d")]
        self.assertEqual([t["id"] for t in overnight.cold_first(pool, self.root)],
                         ["c", "d", "b", "a"])

    def test_an_empty_night_keeps_the_library_order(self) -> None:
        pool = [{"id": tid} for tid in ("b", "a")]
        self.assertEqual([t["id"] for t in overnight.cold_first(pool, self.root)],
                         ["b", "a"])
        self.assertEqual(overnight.coverage(self.root), {})


if __name__ == "__main__":
    unittest.main()
