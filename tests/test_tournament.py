"""Tournament: styles generated, variants executed, winners and pairs produced."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from trainapp import capture, library, tournament

TASK = {
    "id": "test/count",
    "origin": "test",
    "language": "python",
    "title": "count words",
    "description": "print the number of words in the built-in text",
    "code": "print(len('a b c'.split()))\n",
    "runnable": True,
    "tags": [],
}


SET_TASK = {
    "id": "test/two-file",
    "origin": "distiller-build",
    "language": "python",
    "title": "two-file counter",
    "description": "main.py imports lib.py and prints the number of words",
    "files": [
        {"path": "lib.py", "content": "def words(text):\n    return text.split()\n"},
        {"path": "main.py",
         "content": "from lib import words\n\nprint(len(words('a b c')))\n"},
    ],
    "target": "main.py",
    "code": "from lib import words\n\nprint(len(words('a b c')))\n",
    "runnable": True,
    "tags": [],
}


class FakeCoder:
    def __init__(self, replies: dict[str, str]) -> None:
        self.replies = replies
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        for style, reply in self.replies.items():
            if f"**{style}**" in prompt:
                return reply
        return "print(3)\n"


def fake_judge(task, reference, a, b):
    """Shorter valid code wins; ties only when bytes are equal."""
    if not a.get("valid") and not b.get("valid"):
        return {"winner": "tie", "source": "fake", "reason": "both invalid"}
    if a.get("valid") and not b.get("valid"):
        return {"winner": "A", "source": "fake", "reason": "b invalid"}
    if b.get("valid") and not a.get("valid"):
        return {"winner": "B", "source": "fake", "reason": "a invalid"}
    if a["bytes"] == b["bytes"]:
        return {"winner": "tie", "source": "fake", "reason": "same size"}
    return {"winner": "A" if a["bytes"] < b["bytes"] else "B",
            "source": "fake", "reason": "smaller wins",
            "dimensions": {"smaller": "A" if a["bytes"] < b["bytes"] else "B"}}


class TournamentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.prev_root = os.environ.get("VACA_ROOT")
        os.environ["VACA_ROOT"] = str(self.tmp.name)  # keep tests off the real repo
        library.build()  # empty sheet; individual tests seed tasks

    def tearDown(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev
        if self.prev_root is None:
            os.environ.pop("VACA_ROOT", None)
        else:
            os.environ["VACA_ROOT"] = self.prev_root
        self.tmp.cleanup()

    def seed(self, task: dict, status: str = "verified") -> None:
        import json
        with library.tasks_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(task) + "\n")
        with library.validation_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"id": task["id"], "status": status}) + "\n")

    def test_style_variants_are_prompted_and_validated(self) -> None:
        coder = FakeCoder({
            "terse": "print(3)\n",                       # valid, small
            "idiomatic": "words = 'a b c'.split()\nprint(len(words))\n",  # valid, bigger
            "functional": "print(1/0)\n",                # invalid
        })
        result = tournament.run_task(
            TASK, styles=["terse", "idiomatic", "functional"],
            run_timeout_s=15, repeats=1, coder=coder, judge_fn=fake_judge)

        self.assertEqual(len(result["variants"]), 3)
        statuses = {v["style"]: v["valid"] for v in result["variants"]}
        self.assertTrue(statuses["terse"])
        self.assertTrue(statuses["idiomatic"])
        self.assertFalse(statuses["functional"])
        self.assertEqual(result["winner"]["style"], "terse")
        self.assertTrue(result["pairs"])
        self.assertLessEqual(result["winner"]["bytes"], result["reference"]["bytes"] + 2)
        self.assertIn("**terse**", coder.prompts[0])

    def test_invalid_variants_never_win(self) -> None:
        coder = FakeCoder({"terse": "def broken(:\n", "idiomatic": "print(3)\n"})
        result = tournament.run_task(
            TASK, styles=["terse", "idiomatic"], run_timeout_s=15, repeats=1,
            coder=coder, judge_fn=fake_judge)
        self.assertEqual(result["winner"]["style"], "idiomatic")

    @unittest.skipUnless(shutil.which("javac") and shutil.which("java"),
                         "javac/java not installed")
    def test_java_program_with_a_named_public_class_runs(self) -> None:
        code = ("public class Hello {\n"
                "    public static void main(String[] args) { System.out.println(\"hi\"); }\n"
                "}\n")
        result = tournament._run_code({"language": "java"}, code, timeout_s=60)
        self.assertTrue(result["valid"], result.get("stderr"))
        self.assertIn("hi", result["stdout"])

    def test_choose_tasks_only_takes_confirmed_runnable_ones(self) -> None:
        self.seed(TASK)
        self.seed({**TASK, "id": "test/not-runnable", "runnable": False,
                   "code": "x\n", "title": "component"}, status="verified")
        self.seed({**TASK, "id": "test/unverified", "code": "print(4)\n",
                   "title": "other"}, status="failed")
        chosen = tournament.choose_tasks(library.confirmed(), 10)
        self.assertEqual([t["id"] for t in chosen], [TASK["id"]])

    def test_choose_tasks_can_skip_already_covered_seeds(self) -> None:
        self.seed(TASK)
        fresh = {**TASK, "id": "test/fresh", "code": "print(5)\n", "title": "fresh"}
        self.seed(fresh)
        chosen = tournament.choose_tasks(library.confirmed(), 10, exclude={TASK["id"]})
        self.assertEqual([t["id"] for t in chosen], [fresh["id"]])

    def test_summary_measures_shrinkage_and_pairs(self) -> None:
        result = {
            "reference": {"bytes": 40},
            "variants": [{"style": "terse", "bytes": 20, "valid": True, "runtime_ms": 5},
                         {"style": "readable", "bytes": 60, "valid": True, "runtime_ms": 7},
                         {"style": "oop", "bytes": 0, "valid": False}],
            "winner": {"style": "terse", "bytes": 20},
            "pairs": [{"a": 1}, {"b": 2}],
        }
        summary = tournament.summarize([result])
        self.assertEqual(summary["tasks"], 1)
        self.assertEqual(summary["variants"], 3)
        self.assertEqual(summary["verified_variants"], 2)
        self.assertEqual(summary["style_wins"], {"terse": 1})
        self.assertEqual(summary["avg_reference_bytes"], 40)
        self.assertEqual(summary["avg_winner_bytes"], 20)
        self.assertEqual(summary["pairs"], 2)

    def test_a_cli_started_run_is_visible_in_status(self) -> None:
        # `python3 -m trainapp.tournament` writes the status file from another
        # process; the UI must not report idle while it is working.
        tournament.JOB.update(state="idle")
        path = tournament._status_file()
        path.write_text(json.dumps({"state": "running", "tasks": 214, "done": 3,
                                    "current": "go: sum"}) + "\n", encoding="utf-8")
        try:
            status = tournament.status()
            self.assertEqual(status["state"], "running")
            self.assertEqual(status["done"], 3)
        finally:
            path.unlink()

    def test_a_stale_running_file_does_not_fake_a_live_job(self) -> None:
        tournament.JOB.update(state="idle")
        path = tournament._status_file()
        path.write_text(json.dumps({"state": "running", "tasks": 214, "done": 3}) + "\n",
                        encoding="utf-8")
        old = path.stat().st_mtime - 3600
        os.utime(path, (old, old))
        try:
            self.assertEqual(tournament.status()["state"], "idle")
        finally:
            path.unlink()

    def test_a_file_set_is_restyled_one_target_file_at_a_time(self) -> None:
        coder = FakeCoder({
            "terse": "from lib import words\nprint(len(words('a b c')))\n",
            "readable": ("from lib import words\n\ntext = 'a b c'\n"
                         "print(len(words(text)))\n"),
            "functional": "from lib import missing\nprint(1)\n",  # breaks the set
        })
        result = tournament.run_task(
            SET_TASK, styles=["terse", "readable", "functional"],
            run_timeout_s=15, repeats=1, coder=coder, judge_fn=fake_judge)

        self.assertIn("TARGET FILE: main.py", coder.prompts[0])
        statuses = {v["style"]: v["valid"] for v in result["variants"]}
        self.assertTrue(statuses["terse"])
        self.assertTrue(statuses["readable"])
        self.assertFalse(statuses["functional"])
        self.assertEqual(result["winner"]["style"], "terse")
        self.assertTrue(result["pairs"])
        for pair in result["pairs"]:
            self.assertEqual(pair["kind"], "scaffold")
            self.assertEqual(pair["target"], "main.py")
            self.assertIn("### Response", pair["prompt"])
        row = result["capture_row"]
        self.assertTrue(row["meta"]["scaffold"])
        self.assertIn("TARGET FILE: main.py", row["input"])

    def test_a_set_without_a_target_cannot_be_restyled(self) -> None:
        with self.assertRaises(ValueError):
            tournament.run_task({**SET_TASK, "target": "nope.py"},
                                styles=["terse"], run_timeout_s=15, repeats=1,
                                coder=FakeCoder({}), judge_fn=fake_judge)

    def test_choose_tasks_can_take_sets_from_one_origin(self) -> None:
        self.seed(TASK)
        self.seed(SET_TASK)
        self.seed({**SET_TASK, "id": "test/other-set", "origin": "vaca-export"})
        chosen = tournament.choose_tasks(library.confirmed(), 10, sets=True,
                                         origin="distiller-build")
        self.assertEqual([t["id"] for t in chosen], [SET_TASK["id"]])
        self.assertEqual([t["id"] for t in tournament.choose_tasks(
            library.confirmed(), 10)], [TASK["id"]])

    def test_winner_is_captured_as_a_training_row(self) -> None:
        self.seed(TASK)
        coder = FakeCoder({"terse": "print(3)\n"})
        with mock.patch.object(tournament, "choose_tasks", return_value=[TASK]):
            status = tournament.execute(1, ["terse"], run_timeout_s=15, repeats=1,
                                        coder=coder, judge_fn=fake_judge)
        self.assertEqual(status["state"], "done")
        rows = capture.load_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "tournament:winner")
        self.assertEqual(rows[0]["output"], "print(3)")


if __name__ == "__main__":
    unittest.main()
