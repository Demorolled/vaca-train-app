"""Capture gate: only verified, changed, real code reaches the dataset."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import capture


class CaptureTests(unittest.TestCase):
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

    def row(self, n: int = 1, **overrides) -> dict:
        row = capture.make_fix_row(
            language="python",
            filename=f"node{n}.py",
            platform="Linux",
            command="/usr/bin/python3 node.py",
            exit_code=1,
            error_output="Traceback: ZeroDivisionError",
            before=f"print({n} / 0)\n",
            after=f"print({n} // 1)\n",
            goal="divide safely",
        )
        row.update(overrides)
        return row

    def test_verified_row_is_appended(self) -> None:
        ok, reason = capture.append_row(self.row())
        self.assertTrue(ok, reason)
        rows = capture.load_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["output"], "print(1 // 1)")
        self.assertEqual(rows[0]["source"], capture.SOURCE)
        self.assertIn("sha256", rows[0]["meta"])
        self.assertEqual(rows[0]["meta"]["language"], "python")

    def test_duplicate_is_not_captured_twice(self) -> None:
        self.assertTrue(capture.append_row(self.row())[0])
        ok, reason = capture.append_row(self.row())
        self.assertFalse(ok)
        self.assertEqual(reason, "already captured")
        self.assertEqual(len(capture.load_rows()), 1)

    def test_identical_output_is_rejected(self) -> None:
        row = self.row()
        row["output"] = row["meta"]["before"]
        ok, reason = capture.append_row(row)
        self.assertFalse(ok)
        self.assertIn("identical", reason)

    def test_fenced_output_is_rejected(self) -> None:
        ok, reason = capture.append_row(self.row(output="```python\nprint(1)\n```"))
        self.assertFalse(ok)
        self.assertIn("fence", reason)

    def test_empty_output_is_rejected(self) -> None:
        self.assertFalse(capture.append_row(self.row(output="   \n"))[0])

    def test_fix_row_carries_the_harness_context(self) -> None:
        row = self.row()
        self.assertIn("Fix this python file", row["instruction"])
        self.assertIn("Command: /usr/bin/python3 node.py", row["input"])
        self.assertIn("Exit code: 1", row["input"])
        self.assertIn("ZeroDivisionError", row["input"])
        self.assertIn("Goal: divide safely", row["input"])
        self.assertIn("print(1 / 0)", row["input"])
        self.assertEqual(row["output"], "print(1 // 1)")

    def test_stats_counts_by_language(self) -> None:
        capture.append_row(self.row(1))
        capture.append_row(self.row(2))
        stats = capture.stats()
        self.assertEqual(stats["rows"], 2)
        self.assertEqual(stats["by_language"], {"python": 2})

    def test_export_is_deterministic_and_complete(self) -> None:
        for i in range(1, 31):
            self.assertTrue(capture.append_row(self.row(i))[0])

        first = capture.export_dataset()
        self.assertEqual(first["total_examples"], 30)
        self.assertEqual(first["train_examples"] + first["val_examples"], 30)
        self.assertGreaterEqual(first["val_examples"], 1)
        self.assertLess(first["val_examples"], 30)

        train_before = Path(first["train_path"]).read_text(encoding="utf-8")
        val_before = Path(first["val_path"]).read_text(encoding="utf-8")
        second = capture.export_dataset()
        self.assertEqual(train_before, Path(second["train_path"]).read_text(encoding="utf-8"))
        self.assertEqual(val_before, Path(second["val_path"]).read_text(encoding="utf-8"))

        for line in train_before.splitlines():
            self.assertIn("instruction", json.loads(line))

    def test_one_row_sheet_always_keeps_a_train_row(self) -> None:
        self.assertTrue(capture.append_row(self.row())[0])
        for _ in range(5):  # the split is hash-based; re-export must stay honest
            meta = capture.export_dataset()
            self.assertEqual(meta["total_examples"], 1)
            self.assertEqual(meta["train_examples"] + meta["val_examples"], 1)
            self.assertGreaterEqual(meta["train_examples"], 1,
                                    "a single-row dataset must not train on nothing")

    def test_truncated_sheet_line_does_not_break_loading(self) -> None:
        self.assertTrue(capture.append_row(self.row())[0])
        with capture.sheet_path().open("a", encoding="utf-8") as handle:
            handle.write('{"instruction": "half-written')
        self.assertEqual(len(capture.load_rows()), 1)

    # ── VACA's verified app rows ──────────────────────────────────────────

    def vaca_row(self, n: int) -> dict:
        return {
            "instruction": (
                f"Build the timer app. Generate the COMPLETE file 'src/module{n}.ts'"),
            "input": "Request: a pomodoro timer\nPlanned files: src/main.ts, "
                     f"src/module{n}.ts",
            "output": f"export function tick{n}(t: number): number {{\n  return t + {n};\n}}\n",
            "source": "captured-verified",
        }

    def vaca_file(self, rows: list[dict]) -> Path:
        path = Path(self.tmp.name) / "vaca-verified.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return path

    def test_import_vaca_rows_gates_and_dedupes(self) -> None:
        rows = [self.vaca_row(1), self.vaca_row(2),
                {"instruction": "fenced", "input": "",
                 "output": "```ts\nexport const x = 1;\n```"},
                self.vaca_row(1)]  # a repeat inside the same file
        result = capture.import_vaca_rows(self.vaca_file(rows))
        self.assertEqual(result["imported"], 2)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(result["missing"], 0)
        self.assertEqual(len(capture.load_app_rows()), 2)
        stored = capture.load_app_rows()[0]
        self.assertEqual(stored["source"], capture.VACA_SOURCE)
        self.assertEqual(stored["meta"]["origin"], "vaca-export")

        again = capture.import_vaca_rows(self.vaca_file(rows))
        self.assertEqual(again["imported"], 0)
        self.assertEqual(again["duplicates"], 3)
        self.assertEqual(len(capture.load_app_rows()), 2)

    def test_import_missing_vaca_file_is_not_an_error(self) -> None:
        result = capture.import_vaca_rows(Path(self.tmp.name) / "nope.jsonl")
        self.assertEqual(result["imported"], 0)
        self.assertEqual(result["missing"], 1)

    def test_export_merges_both_sheets_with_a_disjoint_split(self) -> None:
        for i in range(1, 4):
            self.assertTrue(capture.append_row(self.row(i))[0])
        capture.import_vaca_rows(self.vaca_file([self.vaca_row(i) for i in (10, 11, 12, 13)]))

        meta = capture.export_dataset()
        self.assertEqual(meta["total_examples"], 7)
        self.assertEqual(meta["sources"], {"corrections": 3, "vaca": 4})
        self.assertEqual(meta["train_examples"] + meta["val_examples"], 7)

        train = [json.loads(line) for line in
                 Path(meta["train_path"]).read_text(encoding="utf-8").splitlines() if line]
        val = [json.loads(line) for line in
               Path(meta["val_path"]).read_text(encoding="utf-8").splitlines() if line]
        train_keys = {capture.row_key(row) for row in train}
        val_keys = {capture.row_key(row) for row in val}
        self.assertFalse(train_keys & val_keys, "a val row leaked into train")
        self.assertEqual(len(train_keys | val_keys), 7)
        self.assertGreaterEqual(len(train), 1)

    def test_stats_reports_app_rows(self) -> None:
        capture.import_vaca_rows(self.vaca_file([self.vaca_row(1), self.vaca_row(2)]))
        stats = capture.stats()
        self.assertEqual(stats["rows"], 0)
        self.assertEqual(stats["app_rows"], 2)
        self.assertEqual(stats["total_rows"], 2)
        self.assertIn("app_captures.jsonl", stats["app_sheet"])


if __name__ == "__main__":
    unittest.main()
