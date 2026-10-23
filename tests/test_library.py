"""Library ingestion: real VACA artifacts, real counts, no invented tasks."""
from __future__ import annotations

import os
import tempfile
import unittest

from trainapp import focus, library

HAS_VACA = (library.vaca_root() / "backend" / "src" / "knowledge" / "rosettaCorpus.json").exists()


class LibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name

    def tearDown(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev
        self.tmp.cleanup()

    @unittest.skipUnless(HAS_VACA, "VACA repo not present")
    def test_rosetta_ingests_every_program(self) -> None:
        tasks = library.ingest_rosetta()
        self.assertEqual(len(tasks), 313)
        languages = {t["language"] for t in tasks}
        for expected in ("go", "rust", "c", "cpp", "java", "csharp", "swift",
                         "kotlin", "php", "ruby", "python"):
            self.assertIn(expected, languages)
        self.assertTrue(all(t["runnable"] for t in tasks))
        self.assertTrue(all(t["code"].strip() for t in tasks))
        self.assertTrue(all(t["origin"] == "rosetta" for t in tasks))

    @unittest.skipUnless(HAS_VACA, "VACA repo not present")
    def test_code_bible_ingests_chunks(self) -> None:
        tasks = library.ingest_code_bible()
        self.assertGreaterEqual(len(tasks), 900)
        self.assertEqual({t["language"] for t in tasks}, {"typescript"})
        self.assertTrue(all(not t["runnable"] for t in tasks),
                        "React components are compile-checked, not executed")

    @unittest.skipUnless(HAS_VACA, "VACA repo not present")
    def test_curated_patterns_are_imported_not_regexed(self) -> None:
        tasks = library.ingest_curated()
        self.assertEqual(len(tasks), 6)
        self.assertEqual({t["language"] for t in tasks},
                         {"rust", "cpp", "go", "java"})
        self.assertTrue(all(len(t["code"]) > 80 for t in tasks))
        self.assertTrue(all(t["runnable"] for t in tasks))

    @unittest.skipUnless(HAS_VACA, "VACA repo not present")
    def test_build_dedupes_and_writes_an_index(self) -> None:
        index = library.build()
        tasks = library.load_tasks()
        self.assertEqual(index["total"], len(tasks))
        self.assertEqual(len({t["id"] for t in tasks}), len(tasks))
        # The sheet is scoped to the five lanes, so the total is smaller than a
        # corpus that keeps every language — but nothing may be lost from it.
        self.assertGreaterEqual(index["total"], 1000)
        self.assertGreater(index["all_languages"], index["total"])
        self.assertEqual(len(library.load_tasks(all_languages=True)),
                         index["all_languages"])
        self.assertTrue(set(index["by_language"]) <= set(focus.LANGUAGES),
                        index["by_language"])
        self.assertIn("typescript", index["by_language"])
        self.assertIn("rosetta", index["by_origin"])
        self.assertGreater(index["runnable"], 100)

    def test_stats_without_validation_reports_unvalidated(self) -> None:
        library.build()
        stats = library.stats()
        self.assertEqual(stats["confirmed"], 0)
        self.assertEqual(stats["by_status"].get("unvalidated"), stats["tasks"])

    def test_confirmed_only_returns_verified(self) -> None:
        library.build()
        task = library.load_tasks()[0]
        library.validation_path().write_text(
            '{"id": "%s", "status": "failed"}\n' % task["id"], encoding="utf-8")
        self.assertEqual(library.confirmed(), [])
        library.validation_path().write_text(
            '{"id": "%s", "status": "verified"}\n' % task["id"], encoding="utf-8")
        self.assertEqual([t["id"] for t in library.confirmed()], [task["id"]])


if __name__ == "__main__":
    unittest.main()
