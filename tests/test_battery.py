"""Battery: held-out task selection, balanced sampling, honest scoring."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import battery


def task(tid: str, language: str = "go", runnable: bool = True) -> dict:
    return {"id": tid, "language": language, "runnable": runnable, "code": "x",
            "title": tid, "description": "do the thing"}


class SelectionTests(unittest.TestCase):
    def test_pairs_tasks_are_excluded(self) -> None:
        tasks = [task("seen"), task("fresh")]
        picked = battery.select_tasks(tasks, {"seen"}, 5, proven={"seen", "fresh"})
        self.assertEqual([t["id"] for t in picked], ["fresh"])

    def test_unrunnable_and_unknown_languages_are_excluded(self) -> None:
        tasks = [task("a", runnable=False), task("b", language="brainfuck"), task("c")]
        picked = battery.select_tasks(tasks, set(), 5, proven={"a", "b", "c"})
        self.assertEqual([t["id"] for t in picked], ["c"])

    def test_only_proven_tasks_are_selected(self) -> None:
        # `runnable` is an ingest guess; without a validation record the task
        # could only ever be skipped, so it is not picked at all.
        tasks = [task("guessed"), task("proven")]
        picked = battery.select_tasks(tasks, set(), 5, proven={"proven"})
        self.assertEqual([t["id"] for t in picked], ["proven"])

    def test_round_robin_does_not_let_one_language_fill_the_battery(self) -> None:
        tasks = [task(f"c{i}", "c") for i in range(6)] + [task("go1", "go")]
        picked = battery.select_tasks(tasks, set(), 4, proven={t["id"] for t in tasks})
        self.assertEqual([t["language"] for t in picked], ["c", "go", "c", "c"])

    def test_language_filter_is_honoured(self) -> None:
        tasks = [task("a", "c"), task("b", "go")]
        picked = battery.select_tasks(tasks, set(), 5, {"go"}, proven={"a", "b"})
        self.assertEqual([t["id"] for t in picked], ["b"])

    def test_prompt_is_the_training_prompt(self) -> None:
        text = battery.prompt_for({"language": "go", "title": "sum", "description": "add"})
        self.assertIn("Write a go implementation of: sum", text)
        self.assertIn("### Response", text)


class HeldOutTests(unittest.TestCase):
    """The battery may not score what either trained sheet already taught."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.dataset = Path(self.tmp.name) / "dataset"
        self.dataset.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev
        self.tmp.cleanup()

    def write(self, name: str, rows: list[dict]) -> None:
        with (self.dataset / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def test_sft_sheet_ids_come_from_both_splits(self) -> None:
        self.write("train.jsonl", [{"instruction": "x", "meta": {"task_id": "base/a"}}])
        self.write("val.jsonl", [{"instruction": "y", "meta": {"task_id": "medium/b"}}])
        self.assertEqual(battery.sft_task_ids(), {"base/a", "medium/b"})

    def test_rows_without_a_task_id_are_ignored(self) -> None:
        self.write("train.jsonl", [{"instruction": "x", "meta": {}}, {"instruction": "z"}])
        self.assertEqual(battery.sft_task_ids(), set())

    def test_missing_sheet_is_empty_not_an_error(self) -> None:
        self.assertEqual(battery.sft_task_ids(), set())

    def test_tasks_the_sft_sheet_taught_are_excluded(self) -> None:
        self.write("train.jsonl", [{"instruction": "x", "meta": {"task_id": "learned"}}])
        tasks = [task("learned"), task("fresh")]
        picked = battery.select_tasks(tasks, battery.sft_task_ids(), 5,
                                      proven={"learned", "fresh"})
        self.assertEqual([t["id"] for t in picked], ["fresh"])

    def test_held_out_ids_merge_both_sheets(self) -> None:
        self.write("train.jsonl", [{"instruction": "x", "meta": {"task_id": "learned"}}])
        with mock.patch.object(battery.preferences, "collect_pairs",
                               return_value=[{"task_id": "judged"}]):
            self.assertEqual(battery.held_out_ids(), {"judged", "learned"})


class ScoreTests(unittest.TestCase):
    def test_rates_separate_compiling_from_behavior(self) -> None:
        rows = [
            {"language": "go", "valid": True, "deterministic": True, "stdout_match": True,
             "bytes": 100, "runtime_ms": 10},
            {"language": "go", "valid": True, "deterministic": True, "stdout_match": False,
             "bytes": 300, "runtime_ms": 20},
            {"language": "c", "valid": False, "deterministic": True},
            {"language": "rust", "valid": True, "deterministic": False, "stdout_match": False,
             "bytes": 200, "runtime_ms": 30},
        ]
        stats = battery.score(rows)
        self.assertEqual(stats["attempts"], 4)
        self.assertEqual(stats["verified"], 3)
        self.assertEqual(stats["verify_rate"], 0.75)
        self.assertEqual(stats["behavior_checked"], 3)
        self.assertEqual(stats["behavior_matched"], 1)
        self.assertEqual(stats["by_language"]["go"]["attempts"], 2)
        self.assertEqual(stats["by_language"]["go"]["verified"], 2)
        self.assertEqual(stats["by_language"]["go"]["behavior_matched"], 1)
        self.assertEqual(stats["by_language"]["go"]["avg_bytes"], 200)
        self.assertEqual(stats["by_language"]["c"]["verify_rate"], 0.0)
        self.assertEqual(stats["avg_bytes"], 200)

    def test_a_lane_that_stopped_building_is_visible_in_the_split(self) -> None:
        """The trade a total hides: TypeScript compiles lost, Java behaviour won."""
        rows = [
            {"language": "typescript", "valid": False, "deterministic": True},
            {"language": "typescript", "valid": False, "deterministic": True},
            {"language": "java", "valid": True, "deterministic": True,
             "stdout_match": True, "bytes": 120},
        ]
        stats = battery.language_stats(rows)
        self.assertEqual(stats["typescript"]["verify_rate"], 0.0)
        self.assertEqual(stats["typescript"]["avg_bytes"], 0)
        self.assertEqual(stats["java"]["behavior_rate"], 1.0)
        self.assertEqual(list(stats), ["java", "typescript"])

    def test_skipped_rows_do_not_count_as_attempts(self) -> None:
        stats = battery.score([{"language": "go", "skipped": True, "valid": False}])
        self.assertEqual(stats["attempts"], 0)
        self.assertEqual(stats["verify_rate"], 0.0)
        self.assertEqual(stats["behavior_rate"], 0.0)

    def test_nondeterministic_reference_is_not_scored_for_behavior(self) -> None:
        stats = battery.score([{"language": "go", "valid": True, "deterministic": False}])
        self.assertEqual(stats["behavior_checked"], 0)
        self.assertEqual(stats["behavior_rate"], 0.0)


class FailureReasonTests(unittest.TestCase):
    def test_compiler_message_is_the_last_line_of_stderr(self) -> None:
        reason = battery.failure_reason({"stderr": "a.c:1:1: error: boom\n     ^\n2 errors\n"})
        self.assertEqual(reason, "2 errors")

    def test_empty_stderr_does_not_crash_the_run(self) -> None:
        # A reference that compiles and then dies on EOF has no stderr at all.
        self.assertEqual(battery.failure_reason({"stderr": "", "stdout": "",
                                                 "error": "", "exit_code": 1}),
                         "exited 1 with no output")

    def test_no_output_and_no_exit_code_stays_generic(self) -> None:
        self.assertEqual(battery.failure_reason({"stderr": "  \n", "exit_code": None}),
                         "reference does not compile/run here")


class ScaffoldBatteryTests(unittest.TestCase):
    """A multi-file task: siblings in the prompt, the whole set in the grade."""

    def scaffold(self) -> dict:
        return {
            "id": "vaca-export/demo-util", "language": "python", "runnable": True,
            "title": "demo — util.py", "description": "print the total",
            "files": [
                {"path": "main.py", "content": "from util import total\nprint(total())\n"},
                {"path": "util.py", "content": "def total():\n    return 3\n"},
            ],
            "target": "util.py", "code": "def total():\n    return 3\n",
        }

    def test_siblings_are_in_the_prompt_and_adherence_is_scored(self) -> None:
        class Coder:
            def __init__(self) -> None:
                self.prompts: list[str] = []

            def complete(self, prompt: str) -> str:
                self.prompts.append(prompt)
                return "def total():\n    return 3\n"

        coder = Coder()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = battery.run({"arm": coder}, [self.scaffold()], timeout_s=20,
                                  out_dir=out, log=lambda *_: None)
            rows = [json.loads(line) for line in
                    (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
                    if line.strip()]
        row = rows[0]
        self.assertTrue(row["scaffold"])
        self.assertEqual(row["context_files"], 1)
        self.assertTrue(row["valid"])
        self.assertEqual(row["adherence"], 1.0)
        self.assertIn("main.py", coder.prompts[0])
        self.assertIn("from util import total", coder.prompts[0])
        self.assertIn("TARGET FILE: util.py", coder.prompts[0])
        self.assertEqual(summary["arms"]["arm"]["scaffold_verified"], 1)
        self.assertEqual(summary["arms"]["arm"]["adherence_rate"], 1.0)

    def test_a_target_that_breaks_its_sibling_fails_the_set(self) -> None:
        class Coder:
            def complete(self, prompt: str) -> str:
                # Compiles fine on its own; the sibling's import is what breaks.
                return "def other():\n    return 3\n"

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            battery.run({"arm": Coder()}, [self.scaffold()], timeout_s=20,
                        out_dir=out, log=lambda *_: None)
            rows = [json.loads(line) for line in
                    (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
                    if line.strip()]
        # The file compiles on its own; only the sibling's real use of it fails.
        self.assertFalse(rows[0]["valid"])


if __name__ == "__main__":
    unittest.main()
