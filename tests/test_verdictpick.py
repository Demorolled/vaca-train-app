"""verdictpick: the QA verdict is labelled by the toolchain, never by QA itself."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import library, orchestra, verdictpick

STAMP = "20261026T031603Z"


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prev_data = os.environ.get("TRAIN_APP_DATA")
        self.prev_root = os.environ.get("VACA_ROOT")
        os.environ["TRAIN_APP_DATA"] = str(self.root / "data")
        os.environ["VACA_ROOT"] = str(self.root / "no-vaca")
        self.addCleanup(self.restore)

    def restore(self) -> None:
        for key, value in (("TRAIN_APP_DATA", self.prev_data),
                           ("VACA_ROOT", self.prev_root)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # ── a copy, written the way orchestra.save_run writes it ────────────────

    def copy(self, slug: str = "print-the-sum", ok: bool = True,
             matches: bool | None = True, status: str = "PASSED",
             errors: list[str] | None = None, build_error: str = "",
             requirement: str = "print the sum of 2 and 3",
             expected: str = "5", stdout: str = "5",
             code: str = "print(5)\n") -> Path:
        target = (Path(os.environ["TRAIN_APP_DATA"]) / "band" / STAMP / slug)
        (target / "files").mkdir(parents=True, exist_ok=True)
        (target / "files" / "main.py").write_text(code, encoding="utf-8")
        board = {
            "user_requirement": requirement, "language": "python",
            "project_manifest": {"main.py": "prints the sum"},
            "design_ledger": {"main.py": "add and print"},
            "code_repository": {"main.py": code},
            "bug_tracker": [], "loop_count": 1, "max_loops": 3,
            "entry": "main.py", "run_cmd": "", "inputs": {},
            "expected_stdout": expected, "stdout_from": "request",
            "dependencies": {"main.py": []},
        }
        verdict = {"status": status, "errors": errors or [],
                   "scope": "code", "files": ["main.py"] if status == "FAILED" else [],
                   "build_ok": ok, "output_ok": matches,
                   "advisory": status == "FAILED" and ok and matches is True}
        (target / "state.json").write_text(json.dumps({
            "user_requirement": requirement, "language": "python",
            "model": "vaca-r40-q4:latest",
            "seats": {"qa": "vaca-r40-q4:latest"},
            "passed": ok and matches is True, "attempts": 1, "board": board,
            "qa": [verdict],
            "build": {"ok": ok, "command": "python3 main.py", "exit_code": 0,
                      "expected": expected, "stdout": stdout,
                      "matches": matches, "error": build_error},
        }, indent=2), encoding="utf-8")
        (target / "blueprint.json").write_text(json.dumps({
            "tree": "main.py", "entry": "main.py", "run": "", "run_from": "",
            "inputs": {}, "inputs_from": "", "expected_stdout": expected,
            "stdout_from": "request", "dependencies": {"main.py": []},
            "project_manifest": {"main.py": "prints the sum"},
        }, indent=2), encoding="utf-8")
        (target / "qa.jsonl").write_text(json.dumps(verdict) + "\n", encoding="utf-8")
        (target / "build.txt").write_text("ok: true\n", encoding="utf-8")
        return target


class LabelTests(Case):
    def run_of(self, **kwargs) -> dict:
        from trainapp import harvest

        self.copy(**kwargs)
        runs = [r for r in harvest.all_runs() if r.get("kind") == "orchestra"]
        self.assertEqual(len(runs), 1)
        return runs[0]

    def test_a_compared_pass_is_labelled_passed(self) -> None:
        run = self.run_of(ok=True, matches=True, status="PASSED")
        label = verdictpick.label_for(run)
        self.assertEqual(label["status"], "PASSED")
        self.assertEqual(label["errors"], [])

    def test_an_unchecked_run_has_no_label(self) -> None:
        run = self.run_of(ok=True, matches=None, status="PASSED")
        self.assertIsNone(verdictpick.label_for(run))

    def test_a_failed_build_is_failed_with_the_toolchain_words(self) -> None:
        run = self.run_of(ok=False, matches=None, status="PASSED",
                          build_error="NameError: name 'total' is not defined")
        label = verdictpick.label_for(run)
        self.assertEqual(label["status"], "FAILED")
        self.assertIn("NameError", label["errors"][0])

    def test_a_wrong_output_is_failed_even_though_it_ran(self) -> None:
        run = self.run_of(ok=True, matches=False, status="PASSED", stdout="6",
                          build_error="the run printed '6' but a correct run prints '5'")
        label = verdictpick.label_for(run)
        self.assertEqual(label["status"], "FAILED")
        self.assertIn("printed", label["errors"][0])


class RowTests(Case):
    def test_a_labelled_run_becomes_one_row_in_the_seats_prompt(self) -> None:
        self.copy()
        rows = verdictpick.rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["system"], orchestra.QA_SYSTEM)
        self.assertTrue(row["instruction"].startswith("Requirement:"))
        self.assertIn("print the sum of 2 and 3", row["instruction"])
        self.assertIn("print(5)", row["instruction"])
        self.assertIn("Reply with JSON only", row["instruction"])
        self.assertIn("FILE: main.py", row["instruction"])
        self.assertEqual(json.loads(row["output"])["status"], "PASSED")
        self.assertEqual(row["meta"]["label_from"], "toolchain")
        self.assertTrue(row["meta"]["agrees"])

    def test_an_unchecked_run_contributes_no_row(self) -> None:
        self.copy(matches=None)
        self.assertEqual(verdictpick.rows(), [])
        self.assertEqual(verdictpick.stats()["unlabelled_unchecked"], 1)

    def test_a_contract_the_requirement_contradicts_gets_no_row(self) -> None:
        # "the sum of 2 and 3" derives 5; a run graded against 999 passed a
        # contract nobody should have written, so it proves nothing about QA.
        self.copy(expected="999", stdout="999", ok=True, matches=True,
                  status="FAILED", errors=["print(result) instead of print(999)"])
        self.assertEqual(verdictpick.rows(), [])
        self.assertEqual(verdictpick.pairs(), [])
        self.assertEqual(verdictpick.stats()["refused_contract"], 1)

    def test_a_reviewer_that_overruled_a_verified_build_becomes_a_pair(self) -> None:
        self.copy(status="FAILED", ok=True, matches=True,
                  errors=["print(result) instead of print(999)"])
        pairs = verdictpick.pairs()
        self.assertEqual(len(pairs), 1)
        pair = pairs[0]
        self.assertEqual(json.loads(pair["chosen"])["status"], "PASSED")
        self.assertEqual(json.loads(pair["rejected"])["status"], "FAILED")
        self.assertEqual(pair["meta"]["why"], "overruled a verified build")
        self.assertTrue(pair["meta"]["label_from"] == "toolchain")

    def test_a_verdict_that_agreed_produces_no_pair(self) -> None:
        self.copy(status="FAILED", ok=False, matches=None,
                  build_error="the run failed")
        self.assertEqual(verdictpick.pairs(), [])

    def test_the_sheets_are_rewritten_not_appended(self) -> None:
        self.copy(status="FAILED", ok=True, matches=True, errors=["wrong"])
        first = verdictpick.write()
        second = verdictpick.write()
        self.assertEqual(first["sft_rows"], second["sft_rows"])
        self.assertEqual(first["pair_rows"], second["pair_rows"])
        lines = Path(second["pairs"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(Path(second["sft"]), library.library_dir() / "qa_sft.jsonl")

    def test_stats_counts_agreement_and_refusal(self) -> None:
        self.copy(slug="agreed", status="PASSED", ok=True, matches=True)
        self.copy(slug="unchecked", matches=None)
        stats = verdictpick.stats()
        self.assertEqual(stats["runs"], 2)
        self.assertEqual(stats["labelled"], 1)
        self.assertEqual(stats["unlabelled_unchecked"], 1)
        self.assertEqual(stats["agreed"], 1)
        self.assertEqual(stats["disagreed"], 0)


if __name__ == "__main__":
    unittest.main()
