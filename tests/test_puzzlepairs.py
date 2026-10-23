"""Only a mutation the build or the output actually caught is a pair."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import puzzlepairs


def puzzle(node_id: str, correct: str, mutant: str, **overrides) -> dict:
    row = {
        "node_id": node_id,
        "path": "src/ai.js",
        "kind": "block",
        "purpose": "game-logic",
        "language": "javascript",
        "correct": correct,
        "mutant": mutant,
        "mutation": "comparison",
    }
    row.update(overrides)
    return row


def score(node_id: str, **overrides) -> dict:
    row = {
        "node_id": node_id,
        "language": "javascript",
        "path": "src/ai.js",
        "purpose": "game-logic",
        "kind": "block",
        "mutation": "comparison",
        "builds": True,
        "behaviour_stable": True,
        "mutant_detected": True,
        "decoy_detected": True,
        "clean": 0.9,
    }
    row.update(overrides)
    return row


class PuzzlePairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.run = Path(self.tmp.name) / "puzzles" / "run1"
        self.run.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev
        self.tmp.cleanup()

    def write(self, name: str, rows: list[dict]) -> None:
        with (self.run / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def test_caught_mutation_is_chosen_correct_rejected_mutant(self) -> None:
        self.write("puzzles.jsonl", [
            puzzle("src/ai.js:1-9", "const x = a > b;", "const x = a < b;"),
        ])
        self.write("scores.jsonl", [score("src/ai.js:1-9")])
        pairs = puzzlepairs.collect()
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["chosen"], "const x = a > b;")
        self.assertEqual(pairs[0]["rejected"], "const x = a < b;")
        rows = puzzlepairs.training_rows()
        self.assertEqual(rows[0]["chosen"], "const x = a > b;\n")
        self.assertIn("src/ai.js", rows[0]["prompt"])
        self.assertIn("game-logic", rows[0]["prompt"])
        self.assertEqual(rows[0]["meta"]["source"], "puzzle:caught-mutation")

    def test_inert_mutation_and_broken_node_are_refused(self) -> None:
        self.write("puzzles.jsonl", [
            puzzle("inert", "return moves.length;", "return moves.size;"),
            puzzle("broken", "const x = 1;", "const x = 2;"),
        ])
        self.write("scores.jsonl", [
            score("inert", mutant_detected=False),
            score("broken", builds=False),
        ])
        self.assertEqual(puzzlepairs.collect(), [])

    def test_duplicate_pairs_across_runs_are_deduped(self) -> None:
        self.write("puzzles.jsonl", [
            puzzle("src/ai.js:1-9", "const x = a > b;", "const x = a < b;"),
        ])
        self.write("scores.jsonl", [score("src/ai.js:1-9")])
        second = Path(self.tmp.name) / "puzzles" / "run2"
        second.mkdir()
        (second / "puzzles.jsonl").write_text(
            (self.run / "puzzles.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
        (second / "scores.jsonl").write_text(
            (self.run / "scores.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(len(puzzlepairs.collect()), 1)


if __name__ == "__main__":
    unittest.main()
