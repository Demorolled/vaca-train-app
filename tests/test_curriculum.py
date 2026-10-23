"""Curriculum: stage selection, efficiency scoring, and the plateau rule."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import curriculum


def task(tid: str, origin: str, language: str = "python", *, files=None,
         runnable: bool = True) -> dict:
    row = {"id": tid, "origin": origin, "language": language, "title": tid,
           "code": f"print({tid!r})", "runnable": runnable}
    if files:
        row["files"] = files
        row["target"] = files[0]["path"]
    return row


class CurriculumTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"TRAIN_APP_DATA": self.tmp.name})
        self.env.start()
        library = self.data / "library"
        library.mkdir(parents=True, exist_ok=True)
        rows = [
            task("base/python", "base-build"),
            task("base/go", "base-build", "go"),
            task("rosetta/one", "rosetta"),
            task("vaca-export/app", "vaca-export", "python",
                 files=[{"path": "main.py", "content": "print(1)"}]),
            task("code-bible/chunk", "code-bible", runnable=False),
        ]
        (library / "tasks.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        (library / "validation.jsonl").write_text(
            "".join(json.dumps({"id": r["id"], "status": "verified",
                                "language": r["language"]}) + "\n" for r in rows),
            encoding="utf-8")

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_stages_select_their_own_origin_and_kind(self) -> None:
        basic = curriculum.stage_tasks("basic")
        self.assertEqual({t["id"] for t in basic}, {"base/python", "base/go"})
        medium = curriculum.stage_tasks("medium")
        self.assertEqual({t["id"] for t in medium}, {"rosetta/one"})
        scaffold = curriculum.stage_tasks("scaffold")
        self.assertEqual({t["id"] for t in scaffold}, {"vaca-export/app"})

    def test_unproven_tasks_are_not_trainable(self) -> None:
        library = self.data / "library"
        rows = (library / "tasks.jsonl").read_text(encoding="utf-8")
        rows += json.dumps(task("base/unproven", "base-build")) + "\n"
        (library / "tasks.jsonl").write_text(rows, encoding="utf-8")
        ids = {t["id"] for t in curriculum.stage_tasks("basic")}
        self.assertNotIn("base/unproven", ids)

    def test_efficiency_rewards_verification_and_punishes_size(self) -> None:
        small = curriculum.efficiency({"arms": {"a": {
            "verify_rate": 1.0, "avg_bytes": 0, "avg_runtime_ms": 0,
            "adherence_rate": 1.0}}})
        big = curriculum.efficiency({"arms": {"a": {
            "verify_rate": 1.0, "avg_bytes": 2000, "avg_runtime_ms": 400,
            "adherence_rate": 1.0}}})
        self.assertEqual(small["efficiency"], 1.0)
        self.assertLess(big["efficiency"], small["efficiency"])
        broken = curriculum.efficiency({"arms": {"a": {
            "verify_rate": 0.0, "avg_bytes": 0, "avg_runtime_ms": 0}}})
        self.assertEqual(broken["efficiency"], 0.0)

    def test_plateau_needs_rounds_before_it_can_agree(self) -> None:
        verdict = curriculum.plateau([{"efficiency": 1.0}], min_rounds=3)
        self.assertFalse(verdict["done"])
        self.assertIn("needs 3", verdict["reason"])

    def test_flat_rounds_are_a_plateau_and_improvement_is_not(self) -> None:
        flat = [{"efficiency": 0.8}, {"efficiency": 0.8}, {"efficiency": 0.8}]
        self.assertTrue(curriculum.plateau(flat, min_rounds=3)["done"])
        tiny = [{"efficiency": 0.8}, {"efficiency": 0.8}, {"efficiency": 0.805}]
        self.assertTrue(curriculum.plateau(tiny, min_rounds=3)["done"])
        climbing = [{"efficiency": 0.6}, {"efficiency": 0.7}, {"efficiency": 0.8}]
        self.assertFalse(curriculum.plateau(climbing, min_rounds=3)["done"])

    def test_advance_refuses_until_the_plateau_rule_agrees(self) -> None:
        first = curriculum.advance()
        self.assertFalse(first["advanced"])
        self.assertEqual(curriculum.load_state()["stage"], "basic")

    def test_advance_moves_to_the_next_stage_when_it_does(self) -> None:
        for _ in range(3):
            curriculum.record({"efficiency": 0.8, "verify_rate": 0.8})
        decision = curriculum.advance()
        self.assertTrue(decision["advanced"])
        self.assertEqual(decision["to"], "medium")
        self.assertEqual(curriculum.load_state()["stage"], "medium")
        self.assertEqual(curriculum.load_state()["rounds"], 0)

    def test_plan_reports_the_stage_and_its_data(self) -> None:
        data = curriculum.plan()
        self.assertEqual(data["stage"], "basic")
        self.assertEqual(data["tasks"], 2)
        self.assertIn("python", data["languages"])
        self.assertIn("advance_rule", data)


if __name__ == "__main__":
    unittest.main()
