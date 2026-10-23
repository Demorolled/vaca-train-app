"""Near-miss mining: preference pairs from answers that were already right.

The gate that matters is the set, not this module's opinion of a mutation: a
candidate is kept only when it still builds and its run now disagrees with the
reference. These tests pin that rule, the single-edit shape of a mutant, and the
hand-off into the night's export.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from unittest import mock

from trainapp import functionprobe, nearmiss, overnight

TOTAL = ("def total(items):\n"
         "    out = 0\n"
         "    for item in items:\n"
         "        out += item\n"
         "    return out\n")


def totals_set(task_id: str = "probe/totals") -> dict:
    return {
        "id": task_id,
        "language": "python",
        "target": "main.py",
        "title": "sum a list and scale it",
        "files": [
            {"path": "main.py",
             "content": ("from util import scale\n\n\n" + TOTAL + "\n\n"
                         "def render(items):\n"
                         "    print('total', scale(total(items)))\n\n\n"
                         "if __name__ == '__main__':\n"
                         "    render([1, 2, 3])\n")},
            {"path": "util.py", "content": "def scale(n):\n    return n * 2\n"},
        ],
    }


class FakeClient:
    def __init__(self, reply: str = TOTAL) -> None:
        self.reply = reply
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return self.reply


class TempDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self._restore)
        self.root = Path(self.tmp.name) / "night"
        overnight.clear_stop()

    def _restore(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev


class MutationTests(unittest.TestCase):
    def test_every_mutant_is_one_edit_that_still_parses(self) -> None:
        mutants = nearmiss.mutants(TOTAL, "python")
        self.assertGreaterEqual(len(mutants), 2)
        for mutant in mutants:
            self.assertNotEqual(mutant["code"], TOTAL)
            compile(mutant["code"], "<mutant>", "exec")

    def test_a_strategy_that_does_not_apply_is_skipped(self) -> None:
        plain = "def greet(name):\n    return 'hi ' + name\n"
        names = {m["mutation"] for m in nearmiss.mutants(plain, "python")}
        self.assertNotIn("seed", names)
        self.assertNotIn("range-end", names)

    def test_ruby_ranges_flip_exclusive_to_inclusive(self) -> None:
        code = "(0...n).each do |i|\n  puts i\nend\n"
        mutants = nearmiss.mutants(code, "ruby")
        self.assertTrue(any("..n" in m["code"] and "..." not in m["code"]
                            for m in mutants))

    def test_the_seed_mutant_shifts_only_the_literal(self) -> None:
        mutant = nearmiss._seed(TOTAL, "python")
        self.assertIn("out = 1", mutant)
        self.assertIn("out += item", mutant)


class MineTests(TempDataTest):
    def passing_records(self, task: dict | None = None) -> list[dict]:
        task = task or totals_set()
        overnight.run(hours=0, rounds=1, root=self.root,
                      client=FakeClient(), tasks=[task])
        return overnight.records(self.root)

    def test_a_passing_answer_yields_a_pair_on_its_own_prompt(self) -> None:
        records = self.passing_records()
        self.assertEqual(len(records), 1)
        result = nearmiss.mine(records, [totals_set()])
        self.assertEqual(result["counts"]["accepted"], 1)
        pair = result["rows"][0]
        self.assertEqual(pair["origin"], "nearmiss:pair")
        self.assertIn("out += item", pair["chosen"])
        self.assertNotEqual(pair["chosen"].strip(), pair["rejected"].strip())
        # The rejected half is a real near miss: it built, and it printed
        # something other than the reference.
        self.assertTrue(pair["rejected_output"])
        self.assertNotEqual(pair["rejected_output"], pair["reference"])
        self.assertEqual(pair["task_id"], "probe/totals")
        self.assertEqual(pair["language"], "python")

    def test_a_mutation_that_breaks_the_build_is_not_a_pair(self) -> None:
        records = self.passing_records()
        blocked = {"mutation": "seed", "code": "def total(items):\n    out = 0\n"}
        original = nearmiss.mutants
        nearmiss.mutants = lambda code, language, limit=0: [blocked]
        self.addCleanup(setattr, nearmiss, "mutants", original)
        result = nearmiss.mine(records, [totals_set()])
        self.assertEqual(result["counts"]["accepted"], 0)
        self.assertEqual(result["counts"]["built"], 1)

    def test_a_mutation_that_leaves_the_output_alone_is_dropped(self) -> None:
        records = self.passing_records()
        # `scale` is not on the prompt, but an edit to a sibling-shaped name
        # still builds and changes nothing the set prints.
        quiet = {"mutation": "noop",
                 "code": TOTAL.replace("    out = 0\n", "    out = 0\n    unused = 1\n")}
        original = nearmiss.mutants
        nearmiss.mutants = lambda code, language, limit=0: [quiet]
        self.addCleanup(setattr, nearmiss, "mutants", original)
        result = nearmiss.mine(records, [totals_set()])
        self.assertEqual(result["counts"]["accepted"], 0)
        self.assertEqual(result["counts"]["same_output"], 1)

    def test_a_row_whose_set_no_longer_reproduces_its_reference_is_skipped(self) -> None:
        records = self.passing_records()
        records[0]["reference"] = "total 999"
        result = nearmiss.mine(records, [totals_set()])
        self.assertEqual(result["counts"]["unstable"], 1)
        self.assertEqual(result["rows"], [])

    def test_pairs_land_where_the_trainer_reads_them(self) -> None:
        records = self.passing_records()
        result = nearmiss.mine(records, [totals_set()])
        summary = nearmiss.write(self.root, result["rows"], result["counts"])
        self.assertEqual(summary["pair_rows"], 1)
        loaded = overnight.load_export(self.root)["pairs"]
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["chosen"], result["rows"][0]["chosen"])

    def test_two_identical_answers_never_repeat_the_same_pair(self) -> None:
        records = self.passing_records()
        doubled = [records[0], dict(records[0])]
        result = nearmiss.mine(doubled, [totals_set()])
        keys = {(r["prompt"], r["chosen"], r["rejected"]) for r in result["rows"]}
        self.assertEqual(len(keys), len(result["rows"]))
        self.assertGreaterEqual(len(result["rows"]), 1)

    def test_the_limit_stops_after_that_many_passing_rows(self) -> None:
        records = self.passing_records()
        result = nearmiss.mine(records + records, [totals_set()], limit=1)
        self.assertEqual(result["counts"]["records"], 1)


class BalanceTests(unittest.TestCase):
    """Mining must not become a sampler for whichever family passes most."""

    def task(self, n: int, description: str) -> dict:
        return {"id": f"probe/s{n}", "language": "python", "target": "main.py",
                "title": description, "description": description,
                "files": [{"path": "main.py",
                           "content": TOTAL + "\n\ndef render(x):\n    print(total(x))\n"}]}

    def records(self, task: dict, n: int = 4) -> list[dict]:
        return [{"task_id": task["id"], "match": True, "reply": TOTAL,
                 "function": "def total(items):", "function_lines": 5,
                 "prompt": f"{task['id']} prompt {i}", "reference": "ref",
                 "language": "python"} for i in range(n)]

    def test_rows_are_walked_round_robin_by_family(self) -> None:
        a = self.task(1, "a cli that prints a running total")
        b = self.task(2, "a cli that prints a histogram")
        rows = self.records(a, 3) + self.records(b, 2)
        order = nearmiss.interleaved(rows, {a["id"]: a, b["id"]: b})
        families = [row["task_id"] for row in order]
        self.assertEqual(families[:4], [a["id"], b["id"], a["id"], b["id"]])

    def test_one_program_cannot_fill_the_sheet(self) -> None:
        tasks = [self.task(n, f"a cli that does thing {n}") for n in range(3)]
        records = [row for task in tasks for row in self.records(task, 4)]

        class Stub:
            """Original runs match the reference; mutations print something else."""
            ok = True
            error = ""
            stderr = ""

            def __init__(self) -> None:
                self.calls = 0
                self.stdout = "ref"

        calls = {"n": 0}

        def run_set(task, code, timeout_s=25, probes=None):
            calls["n"] += 1
            result = Stub()
            result.stdout = "ref" if calls["n"] % 2 else "mut"
            return result

        with mock.patch.object(nearmiss.functionprobe, "run_set", run_set):
            capped = nearmiss.mine(records, tasks, per_family=1)
            uncapped = nearmiss.mine(records, tasks)
        self.assertEqual(len(capped["rows"]), 3)
        self.assertGreater(capped["counts"]["capped"], 0)
        self.assertEqual(len(capped["counts"]["families"]), 3)
        self.assertEqual(max(capped["counts"]["families"].values()), 1)
        self.assertEqual(len(uncapped["rows"]), 12)

class FunctionLookupTests(unittest.TestCase):
    def test_the_asked_for_function_is_found_by_signature(self) -> None:
        task = totals_set()
        row = {"function": "def total(items):", "function_lines": 5}
        fn = nearmiss._function_for(task, row)
        self.assertIsNotNone(fn)
        self.assertIn("out += item", fn["block"])

    def test_an_unknown_signature_is_not_guessed(self) -> None:
        task = totals_set()
        self.assertIsNone(nearmiss._function_for(task, {"function": "def nope():",
                                                        "function_lines": 9}))


if __name__ == "__main__":
    unittest.main()
