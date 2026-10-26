"""The loop merges puzzle pairs without leakage and stops when a round stops paying."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import functioneval, trainloop


def pair(n: int, prefix: str = "tournament") -> dict:
    return {
        "prompt": f"### Instruction\nwrite {prefix} {n}\n\n### Response\n",
        "chosen": f"print({n})\n",
        "rejected": f"print({n})\n# verbose {prefix}\n",
        "meta": {"task_id": f"{prefix}/{n}", "source": prefix},
    }


def bucket(row: dict) -> int:
    key = hashlib.sha256((row["chosen"] + "\0" + row["rejected"]).encode()).hexdigest()
    return int(key[:8], 16) % 100


class TrainLoopTests(unittest.TestCase):
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

    def test_the_rehearsal_sheet_is_written_where_the_trainer_reads_it(self) -> None:
        """ORPO's last pass rehearses the contract from a real file path."""
        path = trainloop.rehearsal_sheet()
        self.assertEqual(path, self.dataset / "rehearsal.jsonl")
        self.assertTrue(path.exists())

    def test_rehearsal_rows_obey_the_family_holdout(self) -> None:
        contract = [
            {"instruction": "i", "input": "x", "output": "print(1)\n",
             "source": "contract", "meta": {"task_id": "held/one"}},
            {"instruction": "i", "input": "y", "output": "print(2)\n",
             "source": "contract", "meta": {"task_id": "kept/two"}},
        ]
        with mock.patch.object(trainloop.contractsft, "rows", return_value=contract), \
                mock.patch.object(trainloop.scaffoldsft, "rows", return_value=[]):
            path = trainloop.rehearsal_sheet({"held/one"})
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["output"] for row in rows], ["print(2)\n"])

    def test_merge_keeps_the_existing_split_and_adds_puzzle_rows(self) -> None:
        tournament = [pair(n) for n in range(30)]
        self.write("pairs_train.jsonl", [r for r in tournament if bucket(r) >= 10])
        self.write("pairs_val.jsonl", [r for r in tournament if bucket(r) < 10])
        puzzles = [pair(n, "puzzle") for n in range(10)]
        meta = trainloop.merge_pairs(puzzles, val_ratio=0.1)
        train = [json.loads(l) for l in
                 (self.dataset / "pairs_train.jsonl").read_text().splitlines()]
        val = [json.loads(l) for l in
               (self.dataset / "pairs_val.jsonl").read_text().splitlines()]
        self.assertEqual(meta["total_pairs"], 40)
        self.assertEqual(len(train) + len(val), 40)
        self.assertEqual(meta["puzzle_pairs"], 10)
        self.assertEqual(meta["sources"], {"tournament": 30, "puzzle": 10})
        self.assertFalse({r["chosen"] for r in train} & {r["chosen"] for r in val})
        # Existing tournament rows keep the side of the hash boundary they had.
        self.assertEqual({r["chosen"] for r in train},
                         {r["chosen"] for r in tournament if bucket(r) >= 10})
        self.assertEqual({r["chosen"] for r in val},
                         {r["chosen"] for r in tournament if bucket(r) < 10})

    def test_merge_is_idempotent(self) -> None:
        self.write("pairs_train.jsonl", [pair(n) for n in range(5)])
        self.write("pairs_val.jsonl", [])
        puzzles = [pair(n, "puzzle") for n in range(3)]
        first = trainloop.merge_pairs(puzzles)
        second = trainloop.merge_pairs(puzzles)
        self.assertEqual(first["total_pairs"], second["total_pairs"])
        self.assertEqual(first["train_pairs"], second["train_pairs"])

    def test_prepare_data_takes_the_nights_export(self) -> None:
        export = Path(self.tmp.name) / "overnight" / "export"
        export.mkdir(parents=True)
        task_id = next(f"night/{n}" for n in range(50)
                       if not functioneval.is_held_out(f"night/{n}"))
        rows = [{"instruction": "Write ONLY this function for `main.py`.",
                 "input": "### Function signature\ndef main():\n",
                 "output": "def main():\n    print(42)\n",
                 "verified": "behaviour",
                 "task_id": task_id, "origin": "function-probe"}]
        pairs = [{"prompt": "### Instruction\nwrite\n\n### Input\n\n### Response\n",
                  "chosen": "def main():\n    print(42)\n",
                  "rejected": "def main():\n    print(41)\n"}]
        (export / "sft.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        (export / "pairs.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in pairs), encoding="utf-8")

        stats = trainloop.prepare_data()
        self.assertEqual(stats["night_rows"], 1)
        self.assertEqual(stats["night_pairs"], 1)
        self.assertEqual(stats["night_holdout"], 0)
        self.assertEqual(stats["pairs"]["total_pairs"], 1)
        train = [json.loads(l) for l in
                 (self.dataset / "train.jsonl").read_text().splitlines()]
        val = [json.loads(l) for l in
               (self.dataset / "val.jsonl").read_text().splitlines()]
        self.assertIn("def main():\n    print(42)\n", [r["output"] for r in train + val])

    def test_the_lane_cut_can_be_lifted_for_one_build(self) -> None:
        """The experiment that asks what the cut cost trains on the whole sheet."""
        seen: dict = {}

        def fake_rows(**kwargs):
            seen.update(kwargs)
            return []

        with mock.patch.object(trainloop.librarysft, "rows", side_effect=fake_rows), \
                mock.patch.object(trainloop.plansft, "rows", side_effect=fake_rows), \
                mock.patch.object(trainloop.contractsft, "rows", side_effect=fake_rows), \
                mock.patch.object(trainloop.scaffoldsft, "rows", side_effect=fake_rows):
            stats = trainloop.prepare_data(all_languages=True)
        self.assertTrue(stats["all_languages"])
        self.assertTrue(seen.get("all_languages"))

    def test_a_programs_only_mix_drops_the_plan_and_contract_sheets(self) -> None:
        """The mix A/B: whole programs only, and the other sheets are not built."""
        called: list[str] = []

        def fake_rows(**kwargs):
            called.append(kwargs.get("all_languages"))
            return []

        with mock.patch.object(trainloop.librarysft, "rows", side_effect=fake_rows), \
                mock.patch.object(trainloop.plansft, "rows", side_effect=fake_rows), \
                mock.patch.object(trainloop.contractsft, "rows", side_effect=fake_rows), \
                mock.patch.object(trainloop.scaffoldsft, "rows", side_effect=fake_rows):
            stats = trainloop.prepare_data(mix="programs")
        self.assertEqual(stats["mix"], "programs")
        self.assertEqual(stats["plan_rows"], 0)
        self.assertEqual(stats["contract_rows"], 0)
        # librarysft + scaffoldsft only: the plan and contract builders never run.
        self.assertEqual(len(called), 2)

    def test_a_family_holdout_keeps_every_sibling_out_of_training(self) -> None:
        export = Path(self.tmp.name) / "overnight" / "export"
        export.mkdir(parents=True)
        # Pick families by the same hash the split uses, so the test does not
        # depend on which side today's seed happens to put a given name on.
        names = [f"a cli that prints pattern {n}" for n in range(40)]
        family = next(n for n in names if functioneval.is_family_held_out(n))
        other = next(n for n in names if not functioneval.is_family_held_out(n))
        held_task = {"id": "night/fib-a", "language": "python",
                     "description": family, "family": family}
        # A family is only held out when it has a sibling to average over, so the
        # held family needs a second set for the split to keep it out at all.
        held_sibling = {"id": "night/fib-b", "language": "go",
                        "description": family, "family": family}
        # One set is not a family that can be measured, so it stays in training.
        keep_task = {"id": "night/ledger-b", "language": "python",
                     "description": other, "family": other}
        tasks = (held_task, held_sibling, keep_task)
        rows = [{"instruction": "Write ONLY this function.",
                 "input": "### Function signature\ndef main():\n",
                 "output": f"def main():\n    print({n})\n",
                 "verified": "behaviour", "task_id": task["id"],
                 "origin": "function-probe"}
                for n, task in enumerate(tasks)]
        (export / "sft.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        pairs = [{"prompt": "p", "chosen": f"print({n})\n",
                  "rejected": f"print({n + 1})\n", "task_id": task["id"],
                  "origin": "nearmiss:pair"}
                 for n, task in enumerate(tasks)]
        (export / "nearmiss.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in pairs), encoding="utf-8")
        with mock.patch.object(trainloop.functionprobe, "candidates",
                               return_value=list(tasks)):
            stats = trainloop.prepare_data(by_family=True)
        self.assertEqual(stats["holdout"], "family")
        # The held family's two sets are gone; the kept family's two remain.
        self.assertEqual(stats["night_rows"], 1)
        self.assertEqual(stats["night_pairs"], 1)
        outputs = [json.loads(line)["output"] for line in
                   (self.dataset / "train.jsonl").read_text().splitlines()]
        self.assertIn("def main():\n    print(2)\n", outputs)
        self.assertNotIn("def main():\n    print(0)\n", outputs)
        self.assertNotIn("def main():\n    print(1)\n", outputs)

    def test_probe_gate_stops_a_round_that_breaks_the_contract(self) -> None:
        models = Path(self.tmp.name) / "models"
        (models / "clean1" / "adapter").mkdir(parents=True)
        baseline = {"arm": "base+clean1", "passed": 9, "total": 10,
                    "passed_ids": ["write-go", "reason-prime"],
                    "failures": [{"id": "plan-node", "reason": "over-planned"}]}
        round_result = {"arm": "base+loop1", "passed": 1, "total": 10,
                        "passed_ids": ["reason-prime"],
                        "failures": [{"id": "write-go", "reason": "2 fence marker(s)"}]}
        with mock.patch.object(trainloop, "prepare_data", return_value={}), \
             mock.patch.object(trainloop, "_train", return_value=0), \
             mock.patch.object(trainloop, "_stop_ollama"), \
             mock.patch.object(trainloop, "_meta", return_value={
                 "val": {"accuracy": 0.70}, "val_before": {"accuracy": 0.55}}), \
             mock.patch.object(trainloop.probes, "evaluate",
                               side_effect=[baseline, round_result]):
            result = trainloop.run(rounds=1)
        self.assertEqual(result["stage"], "probe-gate")
        self.assertEqual(result["adapter"], str(models / "clean1"))
        self.assertEqual([b["id"] for b in result["probe_regressions"]], ["write-go"])
        self.assertIn("write-go", result["reason"])
        history = [json.loads(line) for line in
                   (Path(self.tmp.name) / "trainloop" / "history.jsonl").read_text().splitlines()]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["probe_regressions"], ["write-go"])
        self.assertEqual(history[0]["probes"]["passed"], 1)

    def test_stop_rule_needs_a_real_gain(self) -> None:
        self.assertTrue(trainloop.should_continue([{"accuracy": 0.5}]))
        self.assertTrue(trainloop.should_continue(
            [{"accuracy": 0.5}, {"accuracy": 0.6}]))
        self.assertFalse(trainloop.should_continue(
            [{"accuracy": 0.5}, {"accuracy": 0.502}]))
        self.assertFalse(trainloop.should_continue(
            [{"accuracy": 0.7}, {"accuracy": 0.6}]))


if __name__ == "__main__":
    unittest.main()
