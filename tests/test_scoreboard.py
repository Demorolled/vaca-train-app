"""Scoreboard: the numbers it reports come from the files, not from a guess."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import library, scoreboard


class ScoreboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"TRAIN_APP_DATA": self.tmp.name})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_summary_has_every_section(self) -> None:
        data = scoreboard.summary()
        for key in ("library", "datasets", "puzzles", "runs", "toolchains"):
            self.assertIn(key, data)
        for key in ("tasks", "confirmed", "by_language", "by_origin", "by_status"):
            self.assertIn(key, data["library"])
        self.assertIn("sft_train", data["datasets"])

    def test_language_table_separates_base_builds_from_file_sets(self) -> None:
        tasks = [
            {"id": "base/python", "language": "python", "origin": "base-build",
             "code": "print(1)"},
            {"id": "vaca-export/app", "language": "python", "origin": "vaca-export",
             "code": "print(1)", "target": "a.py",
             "files": [{"path": "a.py", "content": "print(1)"}]},
        ]
        validation = {"base/python": {"status": "verified"},
                      "vaca-export/app": {"status": "failed"}}
        table = scoreboard.language_table(tasks, validation, {})
        row = next(r for r in table if r["language"] == "python")
        self.assertEqual(row["base_builds"], 1)
        self.assertEqual(row["base_verified"], 1)
        self.assertEqual(row["file_sets"], 1)
        self.assertEqual(row["sets_verified"], 0)
        self.assertEqual(row["verified"], 1)
        self.assertEqual(row["failed"], 1)

    def test_puzzle_ranking_is_ordered_by_clean_score(self) -> None:
        path = Path(self.tmp.name) / "library" / "puzzle_scores.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row) for row in (
            {"task_id": "a", "clean": 0.4, "nodes": 2, "caught": 1, "avg_bytes": 90},
            {"task_id": "b", "clean": 0.95, "nodes": 2, "caught": 2, "avg_bytes": 80},
        )) + "\n", encoding="utf-8")
        data = scoreboard.summary()
        self.assertEqual(data["puzzles"]["top"][0]["task_id"], "b")
        self.assertEqual(data["puzzles"]["weakest"][0]["task_id"], "a")
        self.assertEqual(data["puzzles"]["apps"], 2)

    def test_text_rendering_has_the_coverage_header(self) -> None:
        # An empty data dir is a legal state (a fresh checkout); the header and
        # the live-job line must still render instead of raising.
        text = scoreboard.as_text()
        self.assertIn("VACA TRAINER SCOREBOARD", text)
        self.assertIn("language", text)
        self.assertIn("tournament:", text)

    def test_text_rendering_shows_a_language_from_the_sheet(self) -> None:
        sheet = Path(self.tmp.name) / "library" / library.BASE_FILE
        sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.write_text(json.dumps({
            "id": "base-build/sum-1", "language": "go", "origin": "base-build",
            "code": "package main\nfunc main() { println(1) }", "runnable": True,
        }) + "\n", encoding="utf-8")
        self.assertIn("go", scoreboard.as_text())


if __name__ == "__main__":
    unittest.main()
