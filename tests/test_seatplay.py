"""seatplay: play a sheet against a player and bank only what it got wrong."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from trainapp import seatplay


def qa_row(status: str = "PASSED") -> dict:
    return {"system": "you are QA", "instruction": "Requirement:\nprint 5",
            "input": "", "output": json.dumps({"status": status, "errors": [],
                                               "scope": "code", "files": []}),
            "source": "band:qa",
            "meta": {"status": status, "run": "data/band/x/y", "agrees": True}}


def plan_row(answer: str = "B") -> dict:
    return {"system": "", "instruction": "Three plans ...", "input": "",
            "output": f"PLAN: {answer}", "source": "library:plan-pick",
            "meta": {"answer": answer, "task_id": "set/two"}}


class FakeChat:
    def __init__(self, replies: list) -> None:
        self.replies = list(replies)
        self.calls: list[tuple] = []

    def ask(self, system, user, json_object=False, temperature=None):
        self.calls.append((system, user, json_object))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"content": reply}


class ScoreTests(unittest.TestCase):
    def test_a_passing_verdict_matches_the_label(self) -> None:
        result = seatplay.score(qa_row("FAILED"), '{"status": "FAILED", "errors": ["x"]}')
        self.assertTrue(result["correct"])
        self.assertTrue(result["parsed"])

    def test_a_fenced_reply_is_still_read(self) -> None:
        result = seatplay.score(qa_row("PASSED"), '```json\n{"status": "PASSED"}\n```')
        self.assertTrue(result["correct"])

    def test_the_wrong_status_is_a_wrong_answer_not_an_unreadable_one(self) -> None:
        result = seatplay.score(qa_row("PASSED"), '{"status": "FAILED"}')
        self.assertFalse(result["correct"])
        self.assertTrue(result["parsed"])
        self.assertIn("FAILED", result["why"])

    def test_prose_is_unreadable_rather_than_wrong(self) -> None:
        result = seatplay.score(qa_row("PASSED"), "Looks fine to me.")
        self.assertFalse(result["correct"])
        self.assertFalse(result["parsed"])

    def test_a_plan_answer_is_read_from_the_letter(self) -> None:
        self.assertTrue(seatplay.score(plan_row("B"), "PLAN: B")["correct"])
        self.assertTrue(seatplay.score(plan_row("B"), "plan: b")["correct"])
        wrong = seatplay.score(plan_row("B"), "PLAN: C")
        self.assertFalse(wrong["correct"])
        self.assertTrue(wrong["parsed"])
        self.assertIn("picked C", wrong["why"])
        self.assertFalse(seatplay.score(plan_row("B"), "I like the second one")["parsed"])

    def test_the_kind_is_read_from_the_row_not_the_caller(self) -> None:
        self.assertEqual(seatplay.kind_of(qa_row()), "qa")
        self.assertEqual(seatplay.kind_of(plan_row()), "plan")


class PlayTests(unittest.TestCase):
    def test_a_miss_becomes_a_pair_with_the_label_as_chosen(self) -> None:
        chat = FakeChat(['{"status": "FAILED", "errors": ["invented"]}'])
        report = seatplay.play([qa_row("PASSED")], chat)
        self.assertEqual(report["played"], 1)
        self.assertEqual(report["wrong"], 1)
        self.assertEqual(report["correct"], 0)
        pair = report["pairs"][0]
        self.assertEqual(json.loads(pair["chosen"])["status"], "PASSED")
        self.assertIn("FAILED", pair["rejected"])
        self.assertEqual(pair["meta"]["seat"], "qa")
        self.assertEqual(pair["meta"]["kind"], "seat_miss")

    def test_a_correct_answer_writes_no_row(self) -> None:
        chat = FakeChat(['{"status": "PASSED"}'])
        report = seatplay.play([qa_row("PASSED")], chat)
        self.assertEqual(report["correct"], 1)
        self.assertEqual(report["pairs"], [])

    def test_an_unreadable_reply_is_counted_but_not_banked(self) -> None:
        chat = FakeChat(["no idea"])
        report = seatplay.play([qa_row("PASSED")], chat)
        self.assertEqual(report["unparsed"], 1)
        self.assertEqual(report["wrong"], 0)
        self.assertEqual(report["pairs"], [])

    def test_the_prompt_is_sent_with_the_seat_system_and_json_flag(self) -> None:
        chat = FakeChat(['{"status": "PASSED"}'])
        seatplay.play([qa_row("PASSED")], chat)
        system, user, json_object = chat.calls[0]
        self.assertEqual(system, "you are QA")
        self.assertIn("print 5", user)
        self.assertTrue(json_object)

    def test_a_plan_row_is_scored_by_letter(self) -> None:
        chat = FakeChat(["PLAN: A", "PLAN: B"])
        report = seatplay.play([plan_row("B"), plan_row("B")], chat)
        self.assertEqual(report["played"], 2)
        self.assertEqual(report["correct"], 1)
        self.assertEqual(len(report["pairs"]), 1)
        self.assertEqual(report["by_kind"]["plan"]["played"], 2)

    def test_a_dead_player_is_reported_not_raised(self) -> None:
        chat = FakeChat([RuntimeError("connection refused")])
        report = seatplay.play([qa_row()], chat)
        self.assertIn("connection refused", report["error"])
        self.assertEqual(report["played"], 0)

    def test_the_limit_stops_the_loop(self) -> None:
        chat = FakeChat(['{"status": "PASSED"}'])
        report = seatplay.play([qa_row(), qa_row(), qa_row()], chat, limit=1)
        self.assertEqual(report["played"], 1)
        self.assertEqual(len(chat.calls), 1)

    def test_pairs_are_written_to_the_dataset_dir(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = str(Path(tmp.name) / "data")
        self.addCleanup(lambda: os.environ.pop("TRAIN_APP_DATA", None)
                        if prev is None else os.environ.update({"TRAIN_APP_DATA": prev}))
        pair = {"prompt": "p", "chosen": "c", "rejected": "r", "meta": {}}
        path = seatplay.write_pairs([pair])
        self.assertTrue(path.is_file())
        self.assertEqual(json.loads(path.read_text(encoding="utf-8").splitlines()[0]),
                         pair)
        self.assertEqual(seatplay.load_sheet(path), [])


class InventoryTests(unittest.TestCase):
    def test_inventory_counts_kinds_and_labels(self) -> None:
        report = seatplay.inventory([qa_row(), plan_row(), {"instruction": "x"}])
        self.assertEqual(report["rows"], 3)
        self.assertEqual(report["by_kind"]["qa"], 2)
        self.assertEqual(report["by_kind"]["plan"], 1)
        self.assertEqual(report["answerable"], 2)


if __name__ == "__main__":
    unittest.main()
