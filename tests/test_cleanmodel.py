"""Clean model: the manifest records provable data, the registry records status."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import cleanmodel


class CleanModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"TRAIN_APP_DATA": self.tmp.name})
        self.env.start()
        dataset = self.data / "dataset"
        dataset.mkdir(parents=True, exist_ok=True)
        (dataset / "train.jsonl").write_text('{"instruction":"a","output":"b"}\n',
                                             encoding="utf-8")
        (dataset / "val.jsonl").write_text('{"instruction":"c","output":"d"}\n',
                                           encoding="utf-8")

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_manifest_counts_rows_and_digests_each_sheet(self) -> None:
        payload = cleanmodel.manifest(self.data / "clean1")
        self.assertEqual(payload["sources"]["train"]["rows"], 1)
        self.assertTrue(payload["sources"]["train"]["sha256_16"])
        self.assertEqual(payload["sources"]["corrections"]["rows"], 0)
        self.assertTrue((self.data / "clean1" / "data_manifest.json").is_file())
        self.assertTrue(any("App-knowledge" in note for note in payload["notes"]))

    def test_manifest_is_stable_for_the_same_data(self) -> None:
        first = cleanmodel.manifest(self.data / "clean1")
        second = cleanmodel.manifest(self.data / "clean1")
        self.assertEqual(first["sources"]["train"]["sha256_16"],
                         second["sources"]["train"]["sha256_16"])

    def test_register_and_deprecate_roundtrip(self) -> None:
        cleanmodel.register("clean1", "data/models/clean1", status="clean",
                            notes="first clean round")
        cleanmodel.register("orpo2", "data/models/orpo2", status="candidate")
        cleanmodel.deprecate("orpo2", "no provenance record")
        registry = cleanmodel.load_registry()["models"]
        self.assertEqual(registry["clean1"]["status"], "clean")
        self.assertEqual(registry["orpo2"]["status"], "deprecated")
        self.assertIn("provenance", registry["orpo2"]["notes"])
        self.assertEqual([row["name"] for row in cleanmodel.clean_models()], ["clean1"])

    def test_unknown_status_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            cleanmodel.register("x", "y", status="probably-fine")

    def test_commands_start_with_the_exports_and_end_with_the_battery(self) -> None:
        lines = [line for line in cleanmodel.commands("data/models/clean1") if line]
        self.assertIn("--export", lines[0])
        self.assertIn("--mode sft", lines[2])
        self.assertIn("--mode orpo", lines[3])
        self.assertIn("trainapp.battery", lines[-1])
        self.assertIn("data/models/clean1", lines[2])


if __name__ == "__main__":
    unittest.main()
