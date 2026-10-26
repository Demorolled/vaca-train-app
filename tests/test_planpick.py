"""planpick: a decoy enters a row only when a rule can prove it is worse."""
from __future__ import annotations

import unittest
from unittest import mock

from trainapp import library, planpick, plansft, scaffoldsft


def sett(tid: str = "set/two-files", imports: bool = True) -> dict:
    main = ("from util import total\nprint(total())\n" if imports
            else "print(3)\n")
    return {
        "id": tid, "language": "python", "runnable": True, "target": "main.py",
        "title": "demo", "description": "print the total of a fixed list",
        "code": main,
        "files": [{"path": "main.py", "content": main},
                  {"path": "util.py", "content": "def total():\n    return 3\n"}],
    }


class Case(unittest.TestCase):
    def rows_for(self, tasks: list[dict], **kwargs) -> list[dict]:
        with mock.patch.object(library, "load_tasks", return_value=tasks), \
             mock.patch.object(library, "load_validation",
                               return_value={t["id"]: {"status": "verified"} for t in tasks}), \
             mock.patch.object(scaffoldsft, "is_trainable", return_value=True):
            return planpick.rows(**kwargs)

    def pairs_for(self, tasks: list[dict], **kwargs) -> list[dict]:
        with mock.patch.object(library, "load_tasks", return_value=tasks), \
             mock.patch.object(library, "load_validation",
                               return_value={t["id"]: {"status": "verified"} for t in tasks}), \
             mock.patch.object(scaffoldsft, "is_trainable", return_value=True):
            return planpick.pairs(**kwargs)


class PlanTests(Case):
    def test_the_true_plan_is_the_shipped_set(self) -> None:
        lines = planpick.true_plan(sett())
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "main.py (Python) — entry point")
        self.assertIn("util.py (Python)", lines[1])

    def test_a_single_file_set_is_not_a_plan_question(self) -> None:
        task = sett()
        task["files"] = task["files"][:1]
        # One file is a plan, but it is not a choice: there is nothing to pick
        # between, so the set contributes no row and no pair.
        self.assertEqual(len(planpick.true_plan(task)), 1)
        self.assertEqual(planpick.candidates(task), [])
        self.assertEqual(self.rows_for([task]), [])

    def test_references_finds_a_real_import(self) -> None:
        self.assertTrue(planpick.references("from util import total", "util.py"))
        self.assertTrue(planpick.references("require('./util')", "util.js"))
        self.assertTrue(planpick.references('#include "util.h"', "util.h"))
        self.assertTrue(planpick.references("import com.example.WordCounts;",
                                           "WordCounts.java"))
        self.assertFalse(planpick.references("print('nothing here')", "util.py"))

    def test_a_go_grouped_import_names_every_path_in_the_block(self) -> None:
        body = 'package main\n\nimport (\n\t"fmt"\n\t"example/internal/seqs"\n)\n'
        # The second path in the block is the one that matters; the old
        # single-pattern scan only ever saw the first quoted string.
        self.assertTrue(planpick.references(body, "internal/seqs/fiblogic.go"))
        self.assertFalse(planpick.references(body, "internal/other/thing.go"))

    def test_a_symbol_edge_is_found_without_an_import_line(self) -> None:
        bodies = {
            "src/Main.java": "public class Main { WordCounts c = new WordCounts(); }\n",
            "src/WordCounts.java": "public class WordCounts { int count() { return 1; } }\n",
        }
        found = planpick.symbol_edge("src/WordCounts.java", bodies)
        self.assertEqual(found, ("src/Main.java", "WordCounts"))

    def test_a_symbol_two_files_declare_is_not_an_edge(self) -> None:
        bodies = {
            "src/Main.java": "public class Main { Helper h; }\n",
            "src/Helper.java": "public class Helper { }\n",
            "src/Other.java": "public class Helper { }\n",
        }
        self.assertIsNone(planpick.symbol_edge("src/Helper.java", bodies))


class CandidateTests(Case):
    def test_three_plans_exactly_one_true(self) -> None:
        plans = planpick.candidates(sett())
        self.assertEqual(len(plans), 3)
        self.assertEqual([p["letter"] for p in plans], ["A", "B", "C"])
        self.assertEqual(sum(1 for p in plans if p["kind"] == "true"), 1)
        for plan in plans:
            if plan["kind"] != "true":
                self.assertTrue(plan["because"])
                self.assertIn(plan["proof"], ("import", "symbol", "build",
                                              "closed-set", "plan-gate"))

    def test_letters_are_stable_for_the_same_set(self) -> None:
        first = planpick.candidates(sett())
        second = planpick.candidates(sett())
        self.assertEqual([(p["letter"], p["kind"]) for p in first],
                         [(p["letter"], p["kind"]) for p in second])

    def test_a_dropped_file_nothing_imports_is_not_a_decoy(self) -> None:
        self.assertIsNone(planpick._missing_decoy(sett(imports=False),
                                                  ["main.py", "util.py"], False))

    def test_a_drop_the_build_survives_is_refused(self) -> None:
        with mock.patch.object(planpick, "_drops_build", return_value=False):
            decoy = planpick._missing_decoy(sett(), ["main.py", "util.py"], True)
        # The set still built without it, so the plan was a legitimate
        # alternative rather than a wrong answer.
        self.assertIsNone(decoy)

    def test_a_drop_the_build_rejects_is_shipped_as_a_decoy(self) -> None:
        with mock.patch.object(planpick, "_drops_build", return_value=True):
            decoy = planpick._missing_decoy(sett(), ["main.py", "util.py"], True)
        self.assertEqual(decoy["kind"], "missing")
        self.assertEqual(decoy["proof"], "build")
        self.assertIn("does not build", decoy["because"])

    def test_a_consumer_that_cannot_run_falls_back_to_the_target(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake(task, drop="", entry=""):
            calls.append((drop, entry))
            if entry == "consumer.java":       # not runnable on its own
                return (False, "")
            return (True, "") if not drop else (False, "")

        task = sett()
        task["target"] = "main.py"
        with mock.patch.object(planpick, "_builds", side_effect=fake):
            verdict = planpick._drops_build(task, "util.py", entry="consumer.java")
        self.assertTrue(verdict)
        self.assertEqual(calls, [("", "consumer.java"), ("", "main.py"),
                                 ("util.py", "main.py")])

    def test_the_build_proof_runs_the_file_that_imports_it(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake(task, drop="", entry=""):
            calls.append((drop, entry))
            return (True, "") if not drop else (False, "")

        with mock.patch.object(planpick, "_builds", side_effect=fake):
            decoy = planpick._missing_decoy(sett(), ["main.py", "util.py"], True)
        # Baseline and reduced set both run the importer, not the target: the
        # target here is main.py, which is also the importer — and the executor
        # only runs the entry it is given.
        self.assertEqual(calls, [("", "main.py"), ("util.py", "main.py")])
        self.assertEqual(decoy["proof"], "build")

    def test_a_same_package_sibling_becomes_a_missing_decoy(self) -> None:
        task = {
            "id": "set/java-symbols", "language": "java", "runnable": True,
            "target": "src/Main.java", "title": "demo",
            "description": "count words with a helper class",
            "code": "public class Main { WordCounts c = new WordCounts(); }\n",
            "files": [
                {"path": "src/Main.java",
                 "content": "public class Main { WordCounts c = new WordCounts(); }\n"},
                {"path": "src/WordCounts.java",
                 "content": "public class WordCounts { int count() { return 1; } }\n"},
            ],
        }
        decoy = planpick._missing_decoy(task, ["src/Main.java", "src/WordCounts.java"],
                                        False)
        self.assertEqual(decoy["drop"], "src/WordCounts.java")
        self.assertEqual(decoy["proof"], "symbol")
        self.assertIn("WordCounts.java", decoy["because"])

    def test_the_invented_path_is_never_one_the_project_ships(self) -> None:
        task = sett()
        paths = [f["path"] for f in task["files"]]
        invented = planpick._invented_path(task, paths)
        self.assertNotIn(invented, paths)
        self.assertTrue(invented.endswith(".py"))


class RowTests(Case):
    def test_a_row_answers_with_the_true_letter(self) -> None:
        rows = self.rows_for([sett()])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        answer = row["output"].split(":")[-1].strip()
        self.assertEqual(row["output"], f"PLAN: {answer}")
        self.assertIn(answer, "ABC")
        self.assertEqual(row["meta"]["answer"], answer)
        self.assertEqual(len(row["meta"]["decoys"]), 2)
        self.assertIn("PLAN: <letter>", row["instruction"])
        self.assertIn("main.py (Python)", row["instruction"])
        self.assertEqual(row["source"], "library:plan-pick")

    def test_the_answer_letter_marks_the_true_plan(self) -> None:
        task = sett()
        plans = planpick.candidates(task)
        rows = self.rows_for([task])
        true_plan = next(p for p in plans if p["kind"] == "true")
        self.assertEqual(rows[0]["meta"]["answer"], true_plan["letter"])

    def test_the_build_proof_is_used_when_asked_for(self) -> None:
        with mock.patch.object(planpick, "_drops_build", return_value=True):
            rows = self.rows_for([sett()], verify=True)
        kinds = {d["kind"]: d for d in rows[0]["meta"]["decoys"]}
        self.assertIn("missing", kinds)
        self.assertEqual(kinds["missing"]["proof"], "build")

    def test_pairs_carry_both_the_letter_and_the_plan_text(self) -> None:
        pairs = self.pairs_for([sett()])
        kinds = sorted(p["meta"]["kind"] for p in pairs)
        self.assertEqual(kinds, ["plan_pick_pair", "plan_pick_pair",
                                 "plan_text_pair", "plan_text_pair"])
        text = [p for p in pairs if p["meta"]["kind"] == "plan_text_pair"][0]
        self.assertEqual(text["prompt"],
                         plansft.INSTRUCTION.format(title="print the total of a fixed list"))
        self.assertIn("main.py (Python)", text["chosen"])
        self.assertNotEqual(text["chosen"], text["rejected"])

    def test_no_pairs_when_the_set_is_not_a_plan_question(self) -> None:
        task = sett()
        task["files"] = task["files"][:1]
        self.assertEqual(self.pairs_for([task]), [])


if __name__ == "__main__":
    unittest.main()
