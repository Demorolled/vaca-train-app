"""Build-failure repair rows: only real failures, and only from the trainable side."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import buildfix

TASK = {
    "id": "cli-set/python-cli-set-invoice-totals-11111111",
    "language": "python",
    "target": "main.py",
    "title": "invoice totals",
    "files": [{"path": "main.py",
               "content": ("def summarise(lines):\n"
                           "    total = 0\n"
                           "    for line in lines:\n"
                           "        total += line\n"
                           "    return total\n\n\n"
                           "def main():\n"
                           "    print(summarise([1, 2]))\n")}],
}

# The library's own implementation of the function the rows ask for.
WORKING = ("def summarise(lines):\n"
           "    total = 0\n"
           "    for line in lines:\n"
           "        total += line\n"
           "    return total\n")


def attempt(**over) -> dict:
    row = {
        "task_id": TASK["id"], "language": "python",
        "function": "def summarise(lines):",
        "input": "### Function signature\ndef summarise(lines):\n",
        "prompt": "### Instruction\nWrite ONLY this function.\n",
        "reply": "def summarise(lines):\n    return sum(lines) + 1\n",
        "compile": False,
        "error": "main.py line 3: TypeError: unsupported operand",
        "at": "2026-10-24T10:00:00+00:00",
    }
    row.update(over)
    return row


class MinedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "overnight"
        (self.root / "20261024T100000").mkdir(parents=True)
        self.write([])

    def write(self, rows: list[dict]) -> None:
        path = self.root / "20261024T100000" / "samples.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows),
                        encoding="utf-8")

    def mined(self, rows: list[dict], which: str = "rows") -> list[dict]:
        self.write(rows)
        with mock.patch.object(buildfix.library, "load_tasks",
                               return_value=[TASK]):
            return getattr(buildfix, which)(root=self.root)

    def test_a_build_failure_becomes_a_repair_row_with_the_working_answer(self) -> None:
        rows = self.mined([attempt()])
        self.assertEqual(len(rows), 1)
        self.assertIn("TypeError", rows[0]["instruction"])
        self.assertIn("so the whole project builds", rows[0]["instruction"])
        # The answer is the library's own function, not the model's broken one.
        self.assertEqual(rows[0]["output"], WORKING)
        self.assertEqual(rows[0]["source"], "buildfix:repair")

    def test_a_broken_reply_is_the_rejected_half_of_the_pair(self) -> None:
        pairs = self.mined([attempt()], which="pairs")
        self.assertEqual(len(pairs), 1)
        self.assertIn("total += line", pairs[0]["chosen"])
        self.assertIn("+ 1", pairs[0]["rejected"])
        self.assertIn("def summarise(lines):", pairs[0]["prompt"])

    def test_one_row_per_ask_even_when_the_night_retried_it(self) -> None:
        rows = self.mined([attempt(), attempt(reply="def summarise(lines):\n    pass\n")])
        self.assertEqual(len(rows), 1)

    def test_a_control_block_instead_of_a_function_is_dropped(self) -> None:
        """PHP's detector sometimes asks for a `foreach`; splicing that duplicates code."""
        php = dict(TASK, id="cli-set/php-cli-set-x-22222222", language="php",
                   target="a.php",
                   files=[{"path": "a.php",
                           "content": "<?php\nfunction validate($c) {\n  return $c;\n}\n"}])
        row = attempt(task_id=php["id"], language="php",
                      function="foreach (str_split($body) as $ch) {",
                      error="PHP Fatal error: Cannot redeclare function validate()")
        with mock.patch.object(buildfix.library, "load_tasks", return_value=[php]):
            self.write([row])
            self.assertEqual(buildfix.rows(root=self.root), [])
            ok, why = buildfix.usable(row)
        self.assertFalse(ok)
        self.assertIn("control block", why)

    def test_a_failure_with_no_diagnostic_is_not_taught(self) -> None:
        ok, why = buildfix.usable(attempt(error=""))
        self.assertFalse(ok)
        self.assertIn("no diagnostic", why)

    def test_a_passing_attempt_is_not_a_repair_row(self) -> None:
        ok, why = buildfix.usable(attempt(compile=True))
        self.assertFalse(ok)
        self.assertIn("did not fail", why)

    def test_a_mutation_that_still_builds_is_discarded(self) -> None:
        """Proof-gated: only a failure the toolchain reports becomes a row."""
        with mock.patch.object(buildfix.functionprobe, "run_set") as run, \
                mock.patch.object(buildfix.functionprobe, "pool_candidates",
                                  return_value=[TASK]), \
                mock.patch.object(buildfix.functioneval, "holdout_families",
                                  return_value=set()), \
                mock.patch.object(buildfix, "cache_dir",
                                  return_value=Path(self.tmp.name) / "buildfix"):
            run.return_value = mock.Mock(ok=True)
            result = buildfix.generate(limit=10)
        self.assertEqual(result["rows"], 0)
        self.assertGreater(result["tried"], 0)

    def test_a_broken_build_becomes_a_repair_row_and_a_pair(self) -> None:
        failed = mock.Mock(ok=False, exit_code=1, error="", stderr="", stdout="")
        failed.error = "main.py:3: unexpected end of input"
        with mock.patch.object(buildfix.functionprobe, "pool_candidates",
                               return_value=[TASK]), \
                mock.patch.object(buildfix.functioneval, "holdout_families",
                                  return_value=set()), \
                mock.patch.object(buildfix.functionprobe, "run_set",
                                  return_value=failed), \
                mock.patch.object(buildfix, "cache_dir",
                                  return_value=Path(self.tmp.name) / "buildfix"):
            result = buildfix.generate(limit=10, per_function=1)
            rows = buildfix.rows(root=self.root)
            pairs = buildfix.pairs(root=self.root)
        self.assertEqual(result["rows"], 1)
        self.assertIn("unexpected end of input", rows[0]["instruction"])
        self.assertEqual(rows[0]["output"], WORKING)
        self.assertIn("total += line", pairs[0]["rejected"])
        self.assertNotIn("return total", pairs[0]["rejected"])

    def test_the_stats_say_what_was_dropped_and_why(self) -> None:
        self.write([attempt(), attempt(compile=True, at="2026-10-24T10:01:00+00:00"),
                    attempt(error="", at="2026-10-24T10:02:00+00:00")])
        with mock.patch.object(buildfix.library, "load_tasks", return_value=[TASK]):
            stats = buildfix.stats(root=self.root)
        self.assertEqual(stats["attempts"], 3)
        self.assertEqual(stats["rows"], 1)
        self.assertEqual(stats["by_reason"]["no diagnostic"], 1)


if __name__ == "__main__":
    unittest.main()
