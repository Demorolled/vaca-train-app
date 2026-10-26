"""Harvest: every run logged, every verified build a library task, monthly sheets."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import harvest, library, librarysft


class HarvestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prev_data = os.environ.get("TRAIN_APP_DATA")
        self.prev_root = os.environ.get("VACA_ROOT")
        os.environ["TRAIN_APP_DATA"] = str(self.root / "data")
        # The code-bible ingest reads VACA's checkout; harvest does not need it.
        os.environ["VACA_ROOT"] = str(self.root / "no-vaca")
        self.addCleanup(self.restore)

    def restore(self) -> None:
        for key, value in (("TRAIN_APP_DATA", self.prev_data),
                           ("VACA_ROOT", self.prev_root)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # ── fixtures: a real copy on disk, exactly as the builders write it ─────

    def orchestra_run(self, slug: str = "print-the-answer", ok: bool = True,
                      files: dict | None = None, language: str = "python",
                      matches: bool | None = True) -> Path:
        target = Path(os.environ["TRAIN_APP_DATA"]) / "band" / "20261026T010000Z" / slug
        (target / "files").mkdir(parents=True, exist_ok=True)
        files = files or {"main.py": "print(42)\n"}
        for path, code in files.items():
            (target / "files" / path).parent.mkdir(parents=True, exist_ok=True)
            (target / "files" / path).write_text(code, encoding="utf-8")
        (target / "state.json").write_text(json.dumps({
            "user_requirement": "print the answer", "language": language,
            "model": "fake-14b", "passed": ok, "attempts": 2,
            "scaffolding": {"entry": "main.py", "files": [{"path": "main.py"}]},
            "reasoning_steps": "print 42",
            "build": {"ok": ok, "exit_code": 0, "matches": matches,
                      "expected": "42", "stdout": "42",
                      "command": "python3 main.py"},
        }), encoding="utf-8")
        (target / "qa.jsonl").write_text(json.dumps({"status": "PASSED"}) + "\n",
                                         encoding="utf-8")
        return target

    def builder_copy(self, slug: str = "fake--brief-0", ok: bool = True,
                     matches: bool | None = True) -> Path:
        target = Path(os.environ["TRAIN_APP_DATA"]) / "builds" / "20261026T020000Z" / slug
        (target / "files").mkdir(parents=True, exist_ok=True)
        (target / "files" / "main.go").write_text('package main\n\nfunc main() {}\n',
                                                  encoding="utf-8")
        (target / "record.json").write_text(json.dumps({
            "model": "fake-30b", "ok": ok, "runs": 1,
            "task": {"id": "brief/0", "language": "go",
                     "brief": "a go program that does nothing"},
            "files": [{"path": "main.go", "content": "package main\n"}],
            "build": {"ok": ok, "command": "go run main.go", "exit_code": 0,
                      "expected": "ok", "stdout": "ok", "matches": matches},
        }), encoding="utf-8")
        return target


class ScanTests(HarvestCase):
    def test_both_kinds_of_copy_are_found(self) -> None:
        self.orchestra_run()
        self.builder_copy()
        scanned = harvest.scan()
        self.assertEqual(scanned["runs"], 2)
        self.assertEqual(scanned["verified"], 2)
        self.assertEqual(scanned["by_kind"], {"orchestra": 1, "builder": 1})

    def test_a_run_that_failed_is_counted_but_not_verified(self) -> None:
        self.orchestra_run(ok=False)
        scanned = harvest.scan()
        self.assertEqual(scanned["runs"], 1)
        self.assertEqual(scanned["verified"], 0)
        self.assertEqual(scanned["failed"], 1)

    def test_a_run_who_output_was_never_compared_is_not_verified(self) -> None:
        self.orchestra_run(matches=None)
        scanned = harvest.scan()
        self.assertEqual(scanned["runs"], 1)
        self.assertEqual(scanned["verified"], 0)
        self.assertEqual(scanned["unchecked"], 1)

    def test_an_empty_build_directory_is_not_a_run(self) -> None:
        empty = Path(os.environ["TRAIN_APP_DATA"]) / "band" / "20261026T010000Z" / "empty"
        empty.mkdir(parents=True)
        self.assertEqual(harvest.scan()["runs"], 0)


class IngestTests(HarvestCase):
    def test_a_verified_run_becomes_a_library_task(self) -> None:
        self.orchestra_run()
        result = harvest.ingest()
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["by_language"], {"python": 1})
        task = result["tasks"][0]
        self.assertTrue(task["id"].startswith("band-build/"))
        self.assertEqual(task["origin"], "band-build")
        self.assertEqual(task["code"], "print(42)\n")
        self.assertEqual(task["title"], "print the answer")
        self.assertIn("harvest", task["tags"])

    def test_a_run_that_rested_on_an_exit_code_is_logged_but_not_added(self) -> None:
        # Nothing compared the output, so "it built" is not evidence of an app.
        self.orchestra_run(matches=None)
        result = harvest.ingest()
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["new_runs"], 1)
        self.assertEqual(result["unverified"], 1)
        self.assertEqual(result["unchecked"], 1)
        self.assertEqual(library.load_tasks(all_languages=True), [])

    def test_a_run_whose_output_differed_is_never_added(self) -> None:
        self.orchestra_run(matches=False)
        result = harvest.ingest()
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["unchecked"], 0)

    def test_the_task_is_visible_to_every_library_reader(self) -> None:
        self.orchestra_run()
        harvest.ingest()
        ids = [t["id"] for t in library.load_tasks(all_languages=True)]
        self.assertEqual(len([i for i in ids if i.startswith("band-build/")]), 1)

    def test_a_builder_copy_with_no_comparison_is_held_back_too(self) -> None:
        # The builder now records its own comparison; a copy from before that,
        # or one whose plan stated no expected output, is not evidence.
        self.builder_copy(matches=None)
        result = harvest.ingest()
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["unchecked"], 1)
        self.assertEqual(library.load_tasks(all_languages=True), [])

    def test_a_verified_run_writes_a_verified_validation_record(self) -> None:
        self.orchestra_run()
        task = harvest.ingest()["tasks"][0]
        record = library.load_validation()[task["id"]]
        self.assertEqual(record["status"], "verified")
        self.assertEqual(record["source"], "harvest")

    def test_the_run_itself_is_logged_even_when_it_failed(self) -> None:
        self.orchestra_run(ok=False)
        result = harvest.ingest()
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["new_runs"], 1)
        runs = [json.loads(line) for line in harvest.runs_path().read_text().splitlines()]
        self.assertEqual(len(runs), 1)
        self.assertFalse(runs[0]["ok"])
        self.assertEqual(runs[0]["requirement"], "print the answer")
        self.assertIn("qa", runs[0])

    def test_ingesting_twice_adds_nothing_twice(self) -> None:
        self.orchestra_run()
        self.builder_copy()
        first = harvest.ingest()
        second = harvest.ingest()
        self.assertEqual(first["added"], 2)
        self.assertEqual(second["new_runs"], 0)
        self.assertEqual(second["added"], 0)
        rows = (library.library_dir() / library.BAND_FILE).read_text().splitlines()
        self.assertEqual(len(rows), 2)

    def test_the_same_code_from_two_runs_is_one_task(self) -> None:
        self.orchestra_run()
        self.orchestra_run(slug="another-name")
        result = harvest.ingest()
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["skipped"], 1)

    def test_a_multi_file_run_keeps_its_set_and_its_target(self) -> None:
        self.orchestra_run(files={"app.py": "from util import x\nprint(x)\n",
                                  "util.py": "x = 1\n"})
        task = harvest.ingest()["tasks"][0]
        self.assertTrue(library.is_multi_file(task))
        self.assertEqual(task["target"], "app.py")
        self.assertEqual([f["path"] for f in task["files"]], ["app.py", "util.py"])
        self.assertEqual(task["code"], "from util import x\nprint(x)\n")

    def test_a_dry_run_writes_nothing(self) -> None:
        self.orchestra_run()
        result = harvest.ingest(dry_run=True)
        self.assertEqual(result["added"], 1)
        self.assertFalse(harvest.runs_path().exists())
        self.assertFalse((library.library_dir() / library.BAND_FILE).exists())


class PoolTests(HarvestCase):
    """The builder's pool predates the copies, and holds real builds."""

    def pool(self, *, ok: bool = True, code: str = "print(7)\n",
             matches: bool | None = True) -> None:
        path = Path(os.environ["TRAIN_APP_DATA"]) / "builder" / "pool.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "at": "2026-10-24T18:07:39Z", "model": "fake-7b", "label": "fake-7b",
            "ok": ok, "runs": 1, "sha256": "abc12345",
            "task": {"id": "brief/0", "language": "python", "brief": "print seven"},
            "files": [{"path": "main.py", "content": code}],
            "build": {"ok": ok, "command": "python3 main.py", "exit_code": 0,
                      "expected": "7", "stdout": "7", "matches": matches},
        }) + "\n", encoding="utf-8")

    def test_a_pool_record_is_scanned_and_ingested(self) -> None:
        self.pool()
        self.assertEqual(harvest.scan()["runs"], 1)
        result = harvest.ingest()
        self.assertEqual(result["added"], 1)
        self.assertTrue(result["tasks"][0]["id"].startswith("band-build/"))

    def test_a_pool_record_that_failed_is_logged_but_not_a_task(self) -> None:
        self.pool(ok=False)
        result = harvest.ingest()
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["new_runs"], 1)

    def test_a_pool_record_with_no_comparison_is_held_back(self) -> None:
        self.pool(matches=None)
        result = harvest.ingest()
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["unchecked"], 1)

    def test_the_same_build_in_the_pool_and_a_copy_is_one_task(self) -> None:
        self.pool(code="print(42)\n")
        self.orchestra_run()
        result = harvest.ingest()
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["skipped"], 1)


class MonthlyTests(HarvestCase):
    def test_the_month_sheets_hold_the_run_and_its_training_rows(self) -> None:
        self.orchestra_run()
        result = harvest.run(force=True)
        self.assertEqual(result["state"], "done")
        self.assertEqual(result["sft_rows"], 1)
        snapshot = Path(result["snapshot"])
        self.assertTrue(snapshot.is_file())
        self.assertEqual(len(snapshot.read_text().strip().splitlines()), 1)
        rows = [json.loads(line) for line in
                Path(result["sft_sheet"]).read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertIn("print the answer", rows[0]["instruction"])
        self.assertEqual(rows[0]["output"], "print(42)")
        self.assertEqual(rows[0]["meta"]["origin"], "band-build")
        self.assertEqual(rows[0]["source"], "library:band-build")

    def test_the_rows_are_the_shape_the_trainer_reads(self) -> None:
        self.orchestra_run()
        harvest.run(force=True)
        rows = librarysft.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["meta"]["origin"], "band-build")

    def test_a_second_harvest_inside_28_days_is_skipped(self) -> None:
        self.orchestra_run()
        harvest.run(force=True)
        again = harvest.run()
        self.assertEqual(again["state"], "skipped")
        self.assertIn("last harvest", again["reason"])

    def test_force_runs_again_and_still_adds_nothing_twice(self) -> None:
        self.orchestra_run()
        harvest.run(force=True)
        again = harvest.run(force=True)
        self.assertEqual(again["state"], "done")
        self.assertEqual(again["added"], 0)

    def test_a_file_set_is_not_forced_into_one_instruction(self) -> None:
        self.orchestra_run(files={"app.py": "print(1)\n", "util.py": "x = 1\n"})
        result = harvest.run(force=True)
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["sft_rows"], 0)
        self.assertEqual(result["sft_skipped_multi_file"], 1)

    def test_a_dry_run_does_not_touch_the_library(self) -> None:
        self.orchestra_run()
        result = harvest.run(dry_run=True)
        self.assertEqual(result["state"], "dry-run")
        self.assertEqual(result["added"], 1)
        self.assertFalse((library.library_dir() / library.BAND_FILE).exists())

    def test_a_manual_ingest_still_lands_in_this_months_sheet(self) -> None:
        self.orchestra_run()
        harvest.ingest()             # read by hand earlier the same month
        result = harvest.run(force=True)
        self.assertEqual(result["added"], 0)          # already in the library
        self.assertEqual(result["month_tasks"], 1)    # but new to the sheet
        self.assertEqual(result["sft_rows"], 1)
        sheet = Path(result["snapshot"]).read_text().strip().splitlines()
        self.assertEqual(len(sheet), 1)

    def test_the_sheet_is_not_rewritten_by_a_second_run(self) -> None:
        self.orchestra_run()
        first = harvest.run(force=True)
        second = harvest.run(force=True)
        self.assertEqual(second["month_tasks"], 0)
        self.assertEqual(second["sft_rows"], 0)
        rows = Path(first["snapshot"]).read_text().strip().splitlines()
        self.assertEqual(len(rows), 1)

    def test_status_survives_for_the_next_reader(self) -> None:
        self.orchestra_run()
        harvest.run(force=True)
        saved = harvest.status()
        self.assertEqual(saved["state"], "done")
        self.assertEqual(saved["added"], 1)
        self.assertTrue(saved["at"])


if __name__ == "__main__":
    unittest.main()
