"""Library builds become SFT rows only when a real toolchain verified them."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import capture, librarysft


def task(task_id: str, language: str, title: str, code: str,
         origin: str = "base-build", **extra) -> dict:
    row = {
        "id": task_id,
        "origin": origin,
        "language": language,
        "title": title,
        "code": code,
        "description": f"{title} report",
        "runnable": True,
        "category": "medium" if origin == "medium-build" else "basic",
        "tags": [],
    }
    row.update(extra)
    return row


class LibrarySftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.library = Path(self.tmp.name) / "library"
        self.library.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev
        self.tmp.cleanup()

    def write(self, name: str, rows: list[dict]) -> None:
        with (self.library / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def test_only_verified_single_file_builds_become_rows(self) -> None:
        self.write("base_builds.jsonl", [
            task("base-build/a", "python", "sum ten", "print(sum(range(10)))"),
            task("base-build/b", "go", "reverse", "package main\nfunc main() {}\n"),
        ])
        self.write("medium_builds.jsonl", [
            task("medium-build/a", "python", "inventory", "print('inventory')",
                 origin="medium-build"),
            task("medium-build/set", "typescript", "scaffold", "export const x = 1;",
                 origin="medium-build", files=[{"path": "a.ts", "content": "export {}"}],
                 target="a.ts"),
        ])
        self.write("validation.jsonl", [
            {"id": "base-build/a", "language": "python", "status": "verified"},
            {"id": "base-build/b", "language": "go", "status": "failed"},
            {"id": "medium-build/a", "language": "python", "status": "verified"},
            {"id": "medium-build/set", "language": "typescript", "status": "verified"},
        ])
        rows = librarysft.rows()
        self.assertEqual([r["meta"]["task_id"] for r in rows],
                         ["base-build/a", "medium-build/a"])
        self.assertEqual(rows[0]["output"], "print(sum(range(10)))")
        self.assertIn("python", rows[0]["instruction"])
        self.assertIn("sum ten", rows[0]["instruction"])
        self.assertEqual(rows[0]["source"], "library:verified-build")
        self.assertEqual(librarysft.stats()["by_origin"],
                         {"base-build": 1, "medium-build": 1})

    def test_one_demonstration_per_program_per_language(self) -> None:
        """`sum to 5` and `sum to 7` are one demonstration, not two."""
        self.write("base_builds.jsonl", [
            # Same ask, different constant in the code — the library's real shape.
            task("base-build/sum-5", "python", "sum in print result", "print(15)"),
            task("base-build/sum-7", "python", "sum in print result", "print(28)"),
            task("base-build/sum-9", "go", "sum in print result", "package main\n// 45\n"),
            task("base-build/wc", "python", "word count", "print(2)"),
        ])
        self.write("validation.jsonl", [
            {"id": f"base-build/{slug}", "status": "verified"}
            for slug in ("sum-5", "sum-7", "sum-9", "wc")
        ])
        every = librarysft.rows(per_language=0)
        self.assertEqual(len(every), 4)
        self.assertEqual(len({r["meta"]["family"] for r in every}), 2)

        one = librarysft.rows()
        self.assertEqual([r["meta"]["task_id"] for r in one],
                         ["base-build/sum-5", "base-build/sum-9", "base-build/wc"])
        self.assertEqual(len({r["meta"]["language"] for r in one}), 2)
        self.assertEqual([r["meta"]["task_id"] for r in librarysft.rows(per_language=2)],
                         ["base-build/sum-5", "base-build/sum-7",
                          "base-build/sum-9", "base-build/wc"])
        self.assertEqual(librarysft.stats()["families"], 2)
        self.assertEqual(librarysft.stats()["rows"], 3)

    def test_export_dataset_merges_builds_without_a_second_format(self) -> None:
        self.write("base_builds.jsonl", [
            task("base-build/a", "python", "sum ten", "print(sum(range(10)))"),
        ])
        self.write("validation.jsonl", [
            {"id": "base-build/a", "language": "python", "status": "verified"},
        ])
        (Path(self.tmp.name) / "dataset").mkdir()
        meta = capture.export_dataset(extra_rows=librarysft.rows())
        self.assertEqual(meta["total_examples"], 1)
        self.assertEqual(meta["sources"]["extra"], 1)
        exported = (Path(self.tmp.name) / "dataset" / "train.jsonl").read_text(
            encoding="utf-8").splitlines() + \
            (Path(self.tmp.name) / "dataset" / "val.jsonl").read_text(
                encoding="utf-8").splitlines()
        self.assertEqual(len(exported), 1)
        self.assertEqual(json.loads(exported[0])["output"], "print(sum(range(10)))")


if __name__ == "__main__":
    unittest.main()
