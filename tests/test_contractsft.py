"""Contract rows: the two probes the battery still fails get their own examples."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import contractsft, probes

GOOD_GO = ("package main\n\nimport \"fmt\"\n\nfunc main() {\n"
           "\tfmt.Println(\"hi\")\n}\n")


def multi_set(task_id: str, target: str = "router.go") -> dict:
    files = [
        {"path": "main.go", "content": "package main\n\nfunc main() { run() }\n"},
        {"path": target, "content": GOOD_GO},
    ]
    return {"id": task_id, "origin": "vaca-export", "language": "go",
            "title": "a small json api", "description": "a small json api",
            "target": target, "code": GOOD_GO, "files": files}


def single(task_id: str, code: str = GOOD_GO) -> dict:
    return {"id": task_id, "origin": "base-build", "language": "go",
            "title": f"prints hi {task_id}", "description": "prints hi",
            "code": code}


class ContractRowTests(unittest.TestCase):
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

    def write(self, name: str, rows: list[dict], valid: list[str]) -> None:
        with (self.library / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        with (self.library / "validation.jsonl").open("a", encoding="utf-8") as handle:
            for task_id in valid:
                handle.write(json.dumps({"id": task_id, "status": "verified",
                                         "language": "go"}) + "\n")

    def test_an_invent_row_answers_with_one_file_and_no_FILE_blocks(self) -> None:
        self.write("cli_sets.jsonl", [multi_set("set/a")], ["set/a"])
        # share=100 keeps the fixture independent of the hash that decides which
        # sets the battery may be taught; the default is exercised elsewhere.
        rows = contractsft.rows(share=100)
        invent = [r for r in rows if r["source"] == "library:one-file"]
        self.assertEqual(len(invent), 1)
        self.assertIn("FILE: <path>", invent[0]["instruction"])   # the invitation
        self.assertNotIn("FILE: ", invent[0]["output"])           # the refusal
        self.assertTrue(probes.check("scaffold-invent", invent[0]["output"])["ok"])

    def test_a_repair_row_is_broken_by_a_dead_variable(self) -> None:
        self.write("base_builds.jsonl", [single("base/p")], ["base/p"])
        repair = [r for r in contractsft.rows() if r["source"] == "library:dead-variable"]
        self.assertEqual(len(repair), 1)
        row = repair[0]
        self.assertIn("declared and not used: x", row["instruction"])
        self.assertIn("\tx := 1\n", row["instruction"])     # the input is broken
        self.assertNotIn("x := 1", row["output"])           # the answer is not
        self.assertTrue(probes.check("repair-go", row["output"])["ok"])
        self.assertTrue(probes.check("repair-go", row["instruction"].split("---\n")[1])
                        ["ok"] is False)

    def test_a_file_without_main_is_not_a_repair_row(self) -> None:
        helper = "package main\n\nfunc add(a int, b int) int {\n\treturn a + b\n}\n"
        self.write("base_builds.jsonl", [single("base/h", helper)], ["base/h"])
        repair = [r for r in contractsft.rows() if r["source"] == "library:dead-variable"]
        self.assertEqual(repair, [])

    def test_an_unverified_set_teaches_nothing(self) -> None:
        self.write("cli_sets.jsonl", [multi_set("set/b")], [])
        invent = [r for r in contractsft.rows(share=100) if r["source"] == "library:one-file"]
        self.assertEqual(invent, [])


if __name__ == "__main__":
    unittest.main()
