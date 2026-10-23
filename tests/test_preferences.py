"""Preference pairs: collected from real tournament runs, split without leakage."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import preferences


def pair(n: int, **overrides) -> dict:
    row = {
        "task_id": f"task/{n}",
        "language": "python",
        "title": f"task {n}",
        "task": f"do the thing {n}",
        "chosen_style": "terse",
        "rejected_style": "readable",
        "chosen": f"print({n})\n",
        "rejected": f"print({n})\n# verbose\n",
        "chosen_bytes": 10,
        "rejected_bytes": 20,
        "reason": "smaller",
    }
    row.update(overrides)
    return row


class PreferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.tournament = Path(self.tmp.name) / "tournament"

    def tearDown(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev
        self.tmp.cleanup()

    def write_run(self, name: str, rows: list[dict]) -> None:
        directory = self.tournament / name
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "pairs.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def test_collects_every_run(self) -> None:
        self.write_run("run1", [pair(1), pair(2)])
        self.write_run("run2", [pair(3)])
        self.assertEqual(len(preferences.collect_pairs()), 3)
        stats = preferences.stats()
        self.assertEqual(stats["pairs"], 3)
        self.assertEqual(stats["by_language"], {"python": 3})

    def test_duplicate_pairs_are_deduped(self) -> None:
        self.write_run("run1", [pair(1)])
        self.write_run("run2", [pair(1)])
        self.assertEqual(len(preferences.collect_pairs()), 1)

    def test_incomplete_pairs_are_ignored(self) -> None:
        self.write_run("run1", [pair(1, rejected=""), {"chosen": "x"}])
        self.assertEqual(preferences.collect_pairs(), [])

    def test_training_row_is_orpo_shaped(self) -> None:
        row = preferences.to_training_pair(pair(7))
        self.assertIn("### Instruction", row["prompt"])
        self.assertIn("python", row["prompt"])
        self.assertIn("task 7", row["prompt"])
        self.assertTrue(row["prompt"].endswith("### Response\n"))
        self.assertEqual(row["chosen"], "print(7)\n")
        self.assertTrue(row["rejected"].startswith("print(7)"))
        self.assertEqual(row["meta"]["chosen_style"], "terse")

    def test_export_is_deterministic_and_never_strands_all_rows_in_val(self) -> None:
        self.write_run("run1", [pair(i) for i in range(1, 12)])
        first = preferences.export_pairs()
        self.assertEqual(first["total_pairs"], 11)
        self.assertEqual(first["train_pairs"] + first["val_pairs"], 11)
        self.assertGreaterEqual(first["train_pairs"], 1)
        train_before = Path(first["train_path"]).read_text(encoding="utf-8")
        second = preferences.export_pairs()
        self.assertEqual(train_before, Path(second["train_path"]).read_text(encoding="utf-8"))

    def test_export_tolerates_an_empty_tournament_history(self) -> None:
        meta = preferences.export_pairs()
        self.assertEqual(meta["total_pairs"], 0)
        self.assertEqual(meta["train_pairs"], 0)


if __name__ == "__main__":
    unittest.main()
