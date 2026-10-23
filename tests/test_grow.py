"""Growth: only code that compiles, behaves, and beats the reference is added."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import grow, library

TASK = {
    "id": "test/seed",
    "origin": "test",
    "language": "python",
    "title": "print three",
    "description": "print the number three",
    "code": "print(len('a b c'.split()))\n",
    "runnable": True,
    "tags": [],
}


class Coder:
    def __init__(self, by_style: dict[str, str]) -> None:
        self.by_style = by_style
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        for style, code in self.by_style.items():
            if f"**{style}**" in prompt:
                return code
        return "print(3)\n"


def judge_factory(winners: dict[str, str]):
    def fake(task, reference, a, b):
        return {"winner": winners.get(b["style"], "A"), "reason": "fake",
                "source": "fake", "dimensions": {}}
    return fake


class MeasurementGateTests(unittest.TestCase):
    def test_speed_win_within_size_slack_is_accepted(self) -> None:
        ok, why = grow.measurable_improvement(
            {"bytes": 609, "runtime_ms": 87},
            {"bytes": 593, "runtime_ms": 487},
            {"winner": "B", "dimensions": {"faster": "B"}})
        self.assertTrue(ok, why)
        self.assertEqual(why, "faster")

    def test_bigger_and_slower_loses_even_when_the_judge_says_b(self) -> None:
        ok, why = grow.measurable_improvement(
            {"bytes": 900, "runtime_ms": 900},
            {"bytes": 593, "runtime_ms": 487}, {"winner": "B"})
        self.assertFalse(ok)
        self.assertIn("regressed", why)

    def test_no_measured_gain_is_rejected(self) -> None:
        ok, why = grow.measurable_improvement(
            {"bytes": 593, "runtime_ms": 487},
            {"bytes": 593, "runtime_ms": 487}, {"winner": "B"})
        self.assertFalse(ok)
        self.assertIn("no measured improvement", why)

    def test_verdict_that_contradicts_its_dimensions_is_rejected(self) -> None:
        ok, why = grow.measurable_improvement(
            {"bytes": 100, "runtime_ms": 10},
            {"bytes": 300, "runtime_ms": 40},
            {"winner": "B",
             "dimensions": {"smaller": "A", "faster": "A", "versatility": "A"}})
        self.assertFalse(ok)
        self.assertIn("contradicts", why)


class GrowthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.prev = os.environ.get("TRAIN_APP_DATA")
        self.prev_root = os.environ.get("VACA_ROOT")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        os.environ["VACA_ROOT"] = self.tmp.name
        library.build()
        with library.tasks_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(TASK) + "\n")
        with library.validation_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"id": TASK["id"], "status": "verified"}) + "\n")

    def tearDown(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev
        if self.prev_root is None:
            os.environ.pop("VACA_ROOT", None)
        else:
            os.environ["VACA_ROOT"] = self.prev_root
        self.tmp.cleanup()

    def test_a_smaller_verified_winner_is_added(self) -> None:
        coder = Coder({"terse": "print(3)\n"})
        status = grow.expand(1, ["terse"], timeout_s=15, coder=coder,
                             judge_fn=judge_factory({"terse": "B"}))
        self.assertEqual(status["state"], "done")
        self.assertEqual(status["summary"]["accepted"], 1)

        grown = library.load_grown()
        self.assertEqual(len(grown), 1)
        self.assertTrue(grown[0]["id"].startswith("grown/"))
        self.assertEqual(grown[0]["origin"], "grown")
        self.assertEqual(grown[0]["seed_id"], TASK["id"])
        self.assertEqual(grown[0]["style"], "terse")
        self.assertLess(grown[0]["provenance"]["bytes"],
                        grown[0]["provenance"]["reference_bytes"])
        # It joins the library like any other task, and is already confirmed.
        self.assertIn(grown[0]["id"], [t["id"] for t in library.load_tasks()])
        self.assertIn(grown[0]["id"], [t["id"] for t in library.confirmed()])

    def test_seed_ids_pin_the_comparison(self) -> None:
        other = {**TASK, "id": "test/other", "title": "print four",
                 "code": "print(len('ab cd'[:2]))\n"}
        with library.tasks_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(other) + "\n")
        with library.validation_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"id": other["id"], "status": "verified"}) + "\n")
        coder = Coder({"terse": "print(3)\n"})
        status = grow.expand(5, ["terse"], timeout_s=15, coder=coder,
                             judge_fn=judge_factory({"terse": "A"}),
                             seed_ids=[other["id"]])
        decisions_path = Path(status["run_dir"]) / "decisions.jsonl"
        decisions = [json.loads(line) for line in
                     decisions_path.read_text(encoding="utf-8").splitlines()
                     if line.strip()]
        self.assertEqual({d["seed"] for d in decisions}, {other["id"]})

    def test_a_tie_is_not_a_win(self) -> None:
        coder = Coder({"terse": "print(3)\n"})
        status = grow.expand(1, ["terse"], timeout_s=15, coder=coder,
                             judge_fn=judge_factory({"terse": "tie"}))
        self.assertEqual(status["summary"]["accepted"], 0)
        self.assertEqual(status["summary"]["rejected"]["tie"], 1)
        self.assertEqual(library.load_grown(), [])

    def test_a_loss_is_not_added(self) -> None:
        coder = Coder({"terse": "print(3)\n"})
        status = grow.expand(1, ["terse"], timeout_s=15, coder=coder,
                             judge_fn=judge_factory({"terse": "A"}))
        self.assertEqual(status["summary"]["accepted"], 0)
        self.assertEqual(status["summary"]["rejected"]["lost"], 1)

    def test_non_compiling_candidates_never_reach_the_judge(self) -> None:
        calls = []

        def judge(task, reference, a, b):
            calls.append(b["code"])
            return {"winner": "B", "source": "fake"}

        coder = Coder({"terse": "def broken(:\n"})
        status = grow.expand(1, ["terse"], timeout_s=15, coder=coder, judge_fn=judge)
        self.assertEqual(status["summary"]["accepted"], 0)
        self.assertEqual(status["summary"]["rejected"]["invalid"], 1)
        self.assertEqual(calls, [])

    def test_identical_code_is_rejected_before_execution(self) -> None:
        coder = Coder({"terse": TASK["code"]})
        status = grow.expand(1, ["terse"], timeout_s=15, coder=coder,
                             judge_fn=judge_factory({"terse": "B"}))
        self.assertEqual(status["summary"]["accepted"], 0)
        self.assertEqual(status["summary"]["rejected"]["identical"], 1)

    def test_changed_output_is_rejected_even_if_the_judge_prefers_it(self) -> None:
        coder = Coder({"terse": "print(4)\n"})  # judge would pick it, output is wrong
        status = grow.expand(1, ["terse"], timeout_s=15, coder=coder,
                             judge_fn=judge_factory({"terse": "B"}))
        self.assertEqual(status["summary"]["accepted"], 0)
        self.assertEqual(status["summary"]["rejected"]["behavior_mismatch"], 1)

    def test_bloated_slow_candidate_is_rejected_by_the_gate(self) -> None:
        coder = Coder({"terse": "import time\ntime.sleep(0.3)\nprint(3)\n"})
        status = grow.expand(1, ["terse"], timeout_s=15, coder=coder,
                             judge_fn=judge_factory({"terse": "B"}))
        self.assertEqual(status["summary"]["accepted"], 0)
        self.assertEqual(status["summary"]["rejected"]["no_improvement"], 1)
        self.assertEqual(library.load_grown(), [])

    def test_duplicate_candidates_are_not_added_twice(self) -> None:
        coder = Coder({"terse": "print(3)\n"})
        judge_fn = judge_factory({"terse": "B"})
        grow.expand(1, ["terse"], timeout_s=15, coder=coder, judge_fn=judge_fn)
        second = grow.expand(1, ["terse"], timeout_s=15, coder=coder, judge_fn=judge_fn)
        self.assertEqual(second["summary"]["accepted"], 0)
        self.assertEqual(len(library.load_grown()), 1)
        self.assertGreaterEqual(second["summary"]["rejected"]["duplicate"], 1)

    def test_no_confirmed_seed_is_a_clean_failure(self) -> None:
        library.validation_path().write_text("", encoding="utf-8")
        status = grow.expand(1, ["terse"], timeout_s=15, coder=Coder({}),
                             judge_fn=judge_factory({}))
        self.assertEqual(status["state"], "failed")
        self.assertIn("no confirmed runnable tasks", status["error"])

    def test_rebuild_keeps_grown_tasks(self) -> None:
        coder = Coder({"terse": "print(3)\n"})
        grow.expand(1, ["terse"], timeout_s=15, coder=coder,
                    judge_fn=judge_factory({"terse": "B"}))
        library.build()
        self.assertEqual(len(library.load_grown()), 1)
        self.assertIn("grown", library.stats()["index"].get("by_origin", {}))


if __name__ == "__main__":
    unittest.main()
