"""App corpus: real exports become multi-file tasks, drafts and builds excluded."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import appcorpus, library

SIDECAR = {
    "version": 1,
    "request": "a tiny timer app in typescript",
    "planFiles": [
        {"path": "src/types.ts", "summary": "shared types", "language": "typescript"},
        {"path": "src/main.ts", "summary": "entry", "language": "typescript"},
    ],
    "files": ["src/types.ts", "src/main.ts", "_first-drafts/src/main.ts"],
}


class AppCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        export = self.root / "backend" / "exports" / "demo-app"
        (export / "src").mkdir(parents=True)
        (export / "_first-drafts" / "src").mkdir(parents=True)
        (export / "src" / "types.ts").write_text(
            "export interface Tick {\n  seconds: number;\n}\n", encoding="utf-8")
        (export / "src" / "main.ts").write_text(
            "import { Tick } from './types';\nconsole.log('tick');\n", encoding="utf-8")
        (export / "_first-drafts" / "src" / "main.ts").write_text(
            "console.log('draft');\n", encoding="utf-8")
        (export / "_training.json").write_text(json.dumps(SIDECAR), encoding="utf-8")
        self.export = export
        self.sidecar = export / "_training.json"

        self.env = mock.patch.dict(os.environ, {
            "VACA_ROOT": str(self.root),
            "TRAIN_APP_DATA": self.data.name,
        })
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()
        self.data.cleanup()

    def test_export_becomes_a_multi_file_task(self) -> None:
        task = appcorpus.task_from_export(self.sidecar)
        self.assertIsNotNone(task)
        assert task is not None
        self.assertEqual(task["origin"], "vaca-export")
        self.assertEqual(task["category"], "scaffold")
        self.assertEqual(task["language"], "typescript")
        self.assertIn("scaffold", task["tags"])
        paths = [f["path"] for f in task["files"]]
        self.assertIn(task["target"], paths)
        # The first planned source file is the target, and `code` is its content.
        self.assertEqual(task["target"], "src/types.ts")
        self.assertIn("interface Tick", task["code"])
        self.assertIn("tiny timer app", task["description"])

    def test_drafts_are_not_part_of_the_set(self) -> None:
        task = appcorpus.task_from_export(self.sidecar)
        assert task is not None
        paths = [f["path"] for f in task["files"]]
        self.assertFalse(any(p.startswith("_first-drafts") for p in paths))
        self.assertEqual(len(paths), 2)

    def test_export_without_source_files_is_skipped(self) -> None:
        bare = self.root / "backend" / "exports" / "assets-only"
        bare.mkdir(parents=True)
        (bare / "index.html").write_text("<html></html>", encoding="utf-8")
        (bare / "_training.json").write_text(json.dumps(
            {"request": "a page", "planFiles": [], "files": ["index.html"]}),
            encoding="utf-8")
        self.assertIsNone(appcorpus.task_from_export(bare / "_training.json"))

    def test_ingest_then_library_loads_it_exactly_once(self) -> None:
        first = appcorpus.ingest()
        self.assertEqual(first["tasks"], 1)
        self.assertEqual(first["by_language"], {"typescript": 1})
        # Re-ingesting the same export must not duplicate it in the library.
        appcorpus.ingest()
        ids = [t["id"] for t in library.load_tasks()]
        self.assertEqual(ids.count(ids[0]), 1)
        loaded = [t for t in library.load_tasks() if t["origin"] == "vaca-export"]
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["target"], "src/types.ts")
        self.assertEqual(len(loaded[0]["files"]), 2)


if __name__ == "__main__":
    unittest.main()
