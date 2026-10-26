"""The Distiller's pool as library tasks: only apps that built, and only once."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import distiller, library


def record(*, task_id: str = "medium/15-ruby-report", language: str = "ruby",
           ok: bool = True, plan: str = "a counter module and a report",
           entry: str = "bin/app.rb", stdout_match: bool | None = True,
           files: list[dict] | None = None) -> dict:
    files = files if files is not None else [
        {"path": "lib/world.rb", "content": "module World\nend\n"},
        {"path": "bin/app.rb", "content": "require_relative '../lib/world'\nputs 'hi'\n"},
    ]
    return {
        "at": "2026-10-24T21:00:00Z", "model": "qwen3.6:27b",
        "label": "qwen3.6:27b", "endpoint": "http://127.0.0.1:11434",
        "task": {"id": task_id, "language": language, "brief": "A Ruby word report."},
        "conventions": True, "ok": ok, "files": files, "runs": 1,
        "attempts": [{
            "n": 1,
            "plan_json": {"plan": plan, "files": [], "entry": entry,
                          "run": "ruby bin/app.rb", "expected_stdout": "hi"},
            "parsed_files": [{"path": f["path"], "content": f["content"]} for f in files],
            "build": {"ok": ok, "stdout": "hi", "exit_code": 0},
            "stdout_match": stdout_match,
        }],
        "pool_version": 2,
    }


class DistillerIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.pool = Path(self.tmp.name) / "pool.jsonl"

    def tearDown(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev
        self.tmp.cleanup()

    def _write(self, records: list[dict]) -> None:
        self.pool.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    def test_a_built_app_becomes_a_multi_file_task(self) -> None:
        self._write([record()])
        result = distiller.ingest(pool=str(self.pool))
        self.assertEqual(result["added"], 1)
        rows = library.ingest_distiller()
        self.assertEqual(len(rows), 1)
        task = rows[0]
        self.assertEqual(task["origin"], "distiller-build")
        self.assertEqual(task["language"], "ruby")
        self.assertEqual(task["target"], "bin/app.rb")
        self.assertTrue(task["runnable"])
        self.assertEqual(len(task["files"]), 2)
        # `code` is the target's reference implementation, as every multi-file
        # task in the library keeps it.
        self.assertEqual(task["code"], "require_relative '../lib/world'\nputs 'hi'\n")
        self.assertIn("qwen3.6:27b", task["tags"])
        self.assertIn("stdout-matched", task["tags"])

    def test_an_empty_plan_is_refused(self) -> None:
        # The false pass: the plan came back empty, so the writer never saw the
        # brief and wrote an unrelated app that still compiled and ran.
        empty = record(plan="", files=[
            {"path": "lib/calculator.rb", "content": "class Calculator\nend\n"},
            {"path": "bin/app.rb", "content": "puts 'Calculator App'\n"},
        ], entry="bin/app.rb", stdout_match=None)
        self._write([empty])
        result = distiller.ingest(pool=str(self.pool))
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["skipped"].get("the plan came back empty"), 1)
        self.assertEqual(library.ingest_distiller(), [])

    def test_a_failure_is_refused(self) -> None:
        self._write([record(ok=False)])
        result = distiller.ingest(pool=str(self.pool))
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["skipped"].get("did not build"), 1)

    def test_ingest_is_idempotent(self) -> None:
        self._write([record()])
        self.assertEqual(distiller.ingest(pool=str(self.pool))["added"], 1)
        again = distiller.ingest(pool=str(self.pool))
        self.assertEqual(again["added"], 0)
        self.assertEqual(again["skipped"].get("already in the library"), 1)
        self.assertEqual(len(library.ingest_distiller()), 1)

    def test_the_datasheet_is_kept_beside_the_sheet(self) -> None:
        source = Path(self.tmp.name) / "distillation_datasheet.json"
        source.write_text('{"traces": []}\n', encoding="utf-8")
        self._write([record()])
        result = distiller.ingest(pool=str(self.pool), datasheet=str(source))
        self.assertTrue(result["datasheet"])
        kept = library.library_dir() / "distillation_datasheet.json"
        self.assertTrue(kept.exists())
        self.assertEqual(json.loads(kept.read_text()), {"traces": []})

    def test_the_sheet_is_a_separate_file(self) -> None:
        self._write([record()])
        distiller.ingest(pool=str(self.pool))
        self.assertTrue((library.library_dir() / distiller.SHEET).exists())
        self.assertFalse((library.library_dir() / library.IMPORTED_FILE).exists())
