"""Plan rows: the only training source whose output is a file plan, not code."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import plansft, probes


def task(task_id: str, files: list[tuple[str, str]], language: str,
         target: str = "", title: str = "a small project") -> dict:
    # `library.load_tasks` dedupes on (language, code), so each fixture needs
    # its own code or every task after the first disappears.
    return {"id": task_id, "origin": "vaca-export", "language": language,
            "title": title, "description": title, "target": target,
            "code": f"// {task_id}\n",
            "files": [{"path": path, "content": content} for path, content in files]}


class PlanRowTests(unittest.TestCase):
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

    def write(self, rows: list[dict]) -> None:
        with (self.library / "cli_sets.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def test_a_plan_row_is_a_plan_the_gate_accepts(self) -> None:
        self.write([task("plan/a", [("main.go", "package main"), ("store.go", "package main")],
                         "go", target="main.go", title="a key value store")])
        rows = plansft.rows()
        self.assertEqual(len(rows), 1)
        plan = rows[0]["output"]
        self.assertEqual(plan.splitlines(), [
            "main.go (Go) — entry point",
            "store.go (Go) — module",
        ])
        # The gate's own shape check is the contract; a row that fails it would
        # teach the answer it rejects.
        self.assertTrue(probes.check("plan-rust", plan)["ok"])
        self.assertEqual(rows[0]["source"], "library:plan")
        self.assertFalse(probes.FENCE.search(plan))

    def test_a_plan_longer_than_the_allowance_is_not_a_row(self) -> None:
        many = [(f"src/m{i}.ts", "export {}") for i in range(10)]
        self.write([task("plan/long", many, "typescript", target="src/m0.ts")])
        self.assertEqual(plansft.rows(), [])

    def test_the_same_plan_is_kept_once_multi_file_first(self) -> None:
        same = [("main.py", "print(1)"), ("cli.py", "def main(): pass")]
        self.write([
            task("plan/a", same, "python", target="main.py", title="one"),
            task("plan/b", same, "python", target="main.py", title="two"),
            task("plan/c", [("main.py", "print(1)")], "python", target="main.py",
                 title="three"),
        ])
        rows = plansft.rows(per_plan=1)
        self.assertEqual([r["meta"]["task_id"] for r in rows], ["plan/a", "plan/c"])
        self.assertEqual(plansft.stats()["distinct_plans"], 2)
        self.assertTrue(all(probes.check("plan-rust", r["output"])["ok"] for r in rows))

    def test_roles_come_from_the_path(self) -> None:
        self.assertEqual(plansft.role_of("main.go", "main.go"), "entry point")
        self.assertEqual(plansft.role_of("data/db.json"), "data file")
        self.assertEqual(plansft.role_of("styles/site.css"), "styles")
        self.assertEqual(plansft.role_of("README.md"), "documentation")
        self.assertEqual(plansft.role_of("tests/test_math.py"), "tests")
        self.assertEqual(plansft.role_of("src/util.py"), "helper module")
        self.assertEqual(plansft.language_of("src/game.ts", "typescript"), "TypeScript")


if __name__ == "__main__":
    unittest.main()
