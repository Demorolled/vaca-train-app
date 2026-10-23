"""Scaffold SFT rows: verified sets only, siblings in the prompt, honest split."""
from __future__ import annotations

import hashlib
import unittest
from unittest import mock

from trainapp import battery, library, scaffoldsft


def bucket(task_id: str) -> int:
    return int(hashlib.sha256(task_id.encode()).hexdigest()[:8], 16) % 100


def sett(tid: str, status: str = "verified", target: str = "util.py",
         code: str | None = None) -> dict:
    body = code if code is not None else f"def total():\n    return {len(tid)}\n"
    return {
        "id": tid, "language": "python", "runnable": True, "title": "demo",
        "description": f"print the total ({tid})", "target": target,
        "code": body,
        "files": [
            {"path": "main.py", "content": f"from util import total\nprint(total())\n# {tid}\n"},
            {"path": "util.py", "content": body},
        ],
    }


class ScaffoldSftTests(unittest.TestCase):
    def rows_for(self, tasks: list[dict], statuses: dict[str, str],
                 share: int = 100) -> list[dict]:
        with mock.patch.object(library, "load_tasks", return_value=tasks), \
             mock.patch.object(library, "load_validation",
                               return_value={t["id"]: {"status": statuses.get(t["id"], "verified")}
                                             for t in tasks}):
            return scaffoldsft.rows(share=share)

    def test_verified_set_becomes_one_row_with_siblings(self) -> None:
        rows = self.rows_for([sett("set/a")], {"set/a": "verified"})
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("`util.py`", row["instruction"])
        self.assertIn("--- main.py ---", row["input"])
        self.assertIn("from util import total", row["input"])
        self.assertNotIn("--- util.py ---", row["input"])  # the target is the answer
        self.assertEqual(row["output"], sett("set/a")["code"].strip())
        self.assertEqual(row["meta"]["task_id"], "set/a")
        self.assertEqual(row["meta"]["siblings"], 1)

    def test_the_row_rebuilds_the_battery_prompt(self) -> None:
        task = sett("set/a")
        rows = self.rows_for([task], {"set/a": "verified"})
        from trainapp import preferences
        expected = preferences.PROMPT_TEMPLATE.format(
            instruction=rows[0]["instruction"], task=rows[0]["input"],
            language=task["language"], title=task["title"])
        self.assertEqual(expected, battery.scaffold_prompt(task))

    def test_unverified_or_single_file_tasks_are_skipped(self) -> None:
        single = {"id": "lone", "language": "python", "code": "print(1)\n",
                  "title": "lone", "description": "print"}
        rows = self.rows_for([sett("set/failed"), sett("set/ok"), single],
                             {"set/failed": "failed", "set/ok": "verified",
                              "lone": "verified"})
        self.assertEqual([r["meta"]["task_id"] for r in rows], ["set/ok"])

    def test_target_must_be_one_of_the_files(self) -> None:
        rows = self.rows_for([sett("set/missing", target="nope.py")],
                             {"set/missing": "verified"})
        self.assertEqual(rows, [])

    def test_split_is_hash_stable_and_keeps_a_holdout(self) -> None:
        ids = [f"vaca-export/app-{i}" for i in range(40)]
        tasks = [sett(tid, code=f"def total():\n    return {i}\n") for i, tid in enumerate(ids)]
        statuses = {tid: "verified" for tid in ids}
        kept = {row["meta"]["task_id"] for row in self.rows_for(tasks, statuses, share=75)}
        held = {tid for tid in ids if bucket(tid) >= 75}
        self.assertEqual(kept, {tid for tid in ids if bucket(tid) < 75})
        self.assertTrue(held, "the holdout must not be empty")
        # Deterministic: the same sheet exports the same rows twice.
        again = {row["meta"]["task_id"] for row in self.rows_for(tasks, statuses, share=75)}
        self.assertEqual(kept, again)

    def test_no_share_means_every_set_is_held_out(self) -> None:
        self.assertEqual(self.rows_for([sett("set/a")], {"set/a": "verified"}, share=0), [])

    def test_duplicate_instruction_and_code_are_deduped(self) -> None:
        code = "def total():\n    return 3\n"
        first, second = sett("set/a", code=code), sett("set/b", code=code)
        second["description"] = first["description"]
        second["title"] = first["title"]
        second["files"][0]["content"] = first["files"][0]["content"]
        rows = self.rows_for([first, second],
                             {"set/a": "verified", "set/b": "verified"})
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
