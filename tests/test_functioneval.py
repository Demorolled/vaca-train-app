"""Held-out function sets: one deterministic split, shared by training and scoring."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import functioneval


def task_set(task_id: str, prints: str = "42") -> dict:
    return {
        "id": task_id,
        "language": "python",
        "target": "main.py",
        "title": "print a number",
        "files": [{"path": "main.py",
                   "content": (f"def value():\n    return {prints}\n\n\n"
                               "def main():\n    print(value())\n\n\n"
                               "if __name__ == '__main__':\n    main()\n")}],
    }


class FakeCoder:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


class SplitTests(unittest.TestCase):
    def setUp(self) -> None:
        # A real data directory has a night export, and `held_out_tasks` only
        # keeps sets the night proved judgeable; isolate so the pool is the
        # one this test names.
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self.restore)

    def restore(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev

    def test_the_split_is_deterministic_and_by_task_id(self) -> None:
        ids = [f"vaca-export/set-{n}" for n in range(40)]
        first = {i for i in ids if functioneval.is_held_out(i)}
        again = {i for i in ids if functioneval.is_held_out(i)}
        self.assertEqual(first, again)
        # Roughly one in five, never all or none, for a set this size.
        self.assertTrue(8 <= len(first) <= 20, len(first))

    def test_rows_of_a_held_out_task_are_named(self) -> None:
        ids = [f"task/{n}" for n in range(20)]
        rows = [{"task_id": i} for i in ids] + [{"task_id": ""}]
        held = functioneval.holdout_task_ids(rows)
        self.assertEqual(held, {i for i in ids if functioneval.is_held_out(i)})

    def test_held_out_tasks_selects_from_the_library_pool(self) -> None:
        tasks = [{"id": f"task/{n}", "language": "python"} for n in range(20)]
        chosen = functioneval.held_out_tasks(tasks)
        self.assertTrue(chosen)
        self.assertTrue(all(functioneval.is_held_out(t["id"]) for t in chosen))


class FamilyTests(unittest.TestCase):
    def test_the_same_program_in_two_languages_is_one_family(self) -> None:
        java = {"id": "vaca-export/fib-java-1",
                "description": "a java cli that prints the first 12 fibonacci numbers"}
        go = {"id": "vaca-export/fib-go-2",
              "description": "a go cli that prints the first 12 fibonacci numbers"}
        self.assertEqual(functioneval.family_of(java), functioneval.family_of(go))

    def test_a_different_program_is_a_different_family(self) -> None:
        one = {"id": "task/a", "description": "a cli that prints the first 12 numbers"}
        two = {"id": "task/b", "description": "a cli that reverses a string"}
        self.assertNotEqual(functioneval.family_of(one), functioneval.family_of(two))

    def test_a_family_with_one_set_is_never_held_out(self) -> None:
        """Its score would be one draw, which is what made +3 look like a gain."""
        singles = [{"id": f"single/{n}", "language": "python",
                    "title": f"program {n} that prints a number"} for n in range(30)]
        pairs = [{"id": f"pair/{n}-{lang}", "language": lang,
                  "title": f"shared program {n} that prints a number"}
                 for n in range(10) for lang in ("python", "go")]
        chosen = functioneval.held_out_tasks(singles + pairs, by_family=True)
        families = {functioneval.family_of(t) for t in chosen}
        self.assertTrue(families)
        for family in families:
            for task in singles:
                self.assertNotEqual(functioneval.family_of(task), family)

    def test_a_held_family_brings_its_siblings(self) -> None:
        tasks = [{"id": f"pair/{n}-{lang}", "language": lang,
                  "title": f"shared program {n} that prints a number"}
                 for n in range(10) for lang in ("python", "go")]
        chosen = functioneval.held_out_tasks(tasks, by_family=True)
        by_family: dict[str, int] = {}
        for task in chosen:
            key = functioneval.family_of(task)
            by_family[key] = by_family.get(key, 0) + 1
        self.assertTrue(by_family)
        self.assertTrue(all(count >= 2 for count in by_family.values()), by_family)

    def test_no_family_owns_the_pool(self) -> None:
        family = next(f"huge program {n} that prints" for n in range(50)
                      if functioneval.is_family_held_out(f"huge program {n} that prints"))
        tasks = [{"id": f"huge/{n}", "language": "python", "title": family}
                 for n in range(40)]
        chosen = functioneval.held_out_tasks(tasks, by_family=True)
        self.assertEqual(len(chosen), functioneval.MAX_FAMILY_SETS)

    def test_the_file_half_of_a_title_is_not_the_family(self) -> None:
        main = {"id": "task/a", "title": "stock table — main.py"}
        other = {"id": "task/b", "title": "stock table — report.rb"}
        self.assertEqual(functioneval.family_of(main), functioneval.family_of(other))
        self.assertEqual(functioneval.family_of(main), "stock table")

    def test_an_explicit_family_field_wins(self) -> None:
        task = {"id": "task/a", "family": "Histogram Buckets",
                "description": "something else entirely"}
        self.assertEqual(functioneval.family_of(task), "histogram buckets")

    def test_a_family_split_is_deterministic_and_selects_whole_families(self) -> None:
        tasks = [{"id": f"task/{n}-{lang}", "language": lang,
                  "description": f"a cli that does thing {n}"}
                 for n in range(15) for lang in ("python", "go")]
        scored = functioneval.held_out_tasks(tasks, by_family=True)
        held = {t["id"] for t in scored}
        again = {t["id"] for t in functioneval.held_out_tasks(tasks, by_family=True)}
        self.assertEqual(held, again)
        # Every measurable family is held out: power comes from discordant sets,
        # and sampling the eligible families threw half of them away.
        self.assertEqual(len(held), len(tasks))
        chosen = {functioneval.family_of(t) for t in scored}
        self.assertEqual(len(chosen), 15)
        # Selection is by sibling count now, not by hash: a family with two
        # scored sets is measurable whatever the hash says about its name.
        self.assertTrue(all(
            len({t["id"] for t in tasks if functioneval.family_of(t) == f}) >= 2
            for f in chosen))
        for family in chosen:
            ids = {t["id"] for t in tasks if functioneval.family_of(t) == family}
            self.assertEqual(len(ids & held),
                             min(len(ids), functioneval.MAX_FAMILY_SETS))

    def test_family_holdout_ids_covers_every_task_in_a_held_family(self) -> None:
        tasks = [{"id": f"task/{n}", "description": "a cli that prints primes"}
                 for n in range(4)]
        ids = functioneval.family_holdout_ids(tasks)
        self.assertEqual(ids, {t["id"] for t in tasks})

    def test_a_single_set_family_is_left_in_training(self) -> None:
        tasks = [{"id": "task/a", "description": "a cli that prints primes"}]
        self.assertEqual(functioneval.family_holdout_ids(tasks), set())


class PoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self.restore)

    def restore(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev

    def test_only_sets_a_night_proved_judgeable_are_evaluated(self) -> None:
        tasks = [{"id": f"task/{n}", "language": "python"} for n in range(20)]
        held = [t for t in tasks if functioneval.is_held_out(t["id"])]
        export = Path(self.tmp.name) / "overnight" / "export"
        export.mkdir(parents=True)
        rows = [{"task_id": held[0]["id"], "verified": "behaviour",
                 "instruction": "i", "input": "n", "output": "x\n"},
                {"task_id": held[1]["id"], "verified": "compile",
                 "instruction": "i", "input": "n", "output": "x\n"}]
        (export / "sft.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        chosen = functioneval.held_out_tasks(tasks)
        self.assertEqual([t["id"] for t in chosen], [held[0]["id"]])


class ScoreTests(unittest.TestCase):
    def test_a_correct_function_matches_and_a_wrong_one_does_not(self) -> None:
        tasks = [task_set("task/a")]
        good = functioneval.score(FakeCoder("def value():\n    return 42\n"), tasks)
        self.assertEqual(good["stats"]["attempts"], 1)
        self.assertEqual(good["stats"]["match"], 1)
        bad = functioneval.score(FakeCoder("def value():\n    return 41\n"), tasks)
        self.assertEqual(bad["stats"]["match"], 0)
        self.assertEqual(bad["stats"]["compile"], 1)

    def test_one_arm_failing_does_not_stop_the_other(self) -> None:
        class Dead:
            def complete(self, prompt: str) -> str:
                raise RuntimeError("model died")

        result = functioneval.evaluate(
            {"base": Dead(), "adapter": FakeCoder("def value():\n    return 42\n")},
            [task_set("task/a")])
        self.assertEqual(result["arms"]["base"]["match"], 0)
        self.assertEqual(result["arms"]["adapter"]["match"], 1)
        self.assertIn("model died", result["rows"]["base"][0]["error"])

    def test_the_split_is_written_with_the_result(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            result = functioneval.evaluate(
                {"base": FakeCoder("def value():\n    return 42\n")},
                [task_set("task/a")], out=out)
            written = json.loads((out / "eval.json").read_text(encoding="utf-8"))
            self.assertEqual(written["held_out"], result["held_out"])
            self.assertTrue((out / "base.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
