"""Judge: deterministic gate first, then a strict JSON verdict."""
from __future__ import annotations

import unittest
from unittest import mock

from trainapp import judge

TASK = {"title": "word count", "language": "python", "description": "count words"}


def candidate(style: str, code: str, valid: bool = True, bytes_: int = 10,
              ms: int = 5, match: bool = True) -> dict:
    return {"style": style, "code": code, "valid": valid, "bytes": bytes_,
            "runtime_ms": ms, "stdout_match": match}


class ParseTests(unittest.TestCase):
    def test_fenced_json(self) -> None:
        raw = 'Here:\n```json\n{"winner":"B","smaller":"B","reason":"shorter"}\n```'
        self.assertEqual(judge.parse_verdict(raw)["winner"], "B")

    def test_chatty_json(self) -> None:
        raw = 'I compared them. {"winner":"tie","reason":"same"} That is all.'
        self.assertEqual(judge.parse_verdict(raw)["winner"], "tie")

    def test_bare_winner_line(self) -> None:
        self.assertEqual(judge.parse_verdict("WINNER: A")["winner"], "A")

    def test_garbage_is_none(self) -> None:
        self.assertIsNone(judge.parse_verdict("I think they are both fine."))
        self.assertIsNone(judge.parse_verdict(""))


class DeterministicGateTests(unittest.TestCase):
    def test_invalid_loses_without_calling_the_model(self) -> None:
        with mock.patch.object(judge, "_chat") as chat:
            verdict = judge.compare(TASK, "ref",
                                    candidate("terse", "x", valid=False),
                                    candidate("readable", "y", valid=True))
        chat.assert_not_called()
        self.assertEqual(verdict["winner"], "B")
        self.assertEqual(verdict["source"], "deterministic")

    def test_both_invalid_is_a_tie(self) -> None:
        verdict = judge.compare(TASK, "ref",
                                candidate("a", "x", valid=False),
                                candidate("b", "y", valid=False))
        self.assertEqual(verdict["winner"], "tie")

    def test_identical_code_is_a_tie(self) -> None:
        verdict = judge.compare(TASK, "ref",
                                candidate("a", "same"),
                                candidate("b", "same"))
        self.assertEqual(verdict["winner"], "tie")
        self.assertIn("identical", verdict["reason"])

    def test_llm_verdict_is_parsed_with_dimensions(self) -> None:
        reply = ('{"winner":"B","correctness":"tie","smaller":"B","faster":"A",'
                 '"versatility":"B","reason":"B is half the size"}')
        with mock.patch.object(judge, "_chat", return_value=reply):
            verdict = judge.compare(TASK, "ref",
                                    candidate("terse", "a" * 50, bytes_=50),
                                    candidate("readable", "b" * 20, bytes_=20))
        self.assertEqual(verdict["winner"], "B")
        self.assertEqual(verdict["dimensions"]["smaller"], "B")
        self.assertEqual(verdict["source"], "llm")

    def test_judge_unreachable_is_reported_not_invented(self) -> None:
        with mock.patch.object(judge, "_chat", side_effect=OSError("connection refused")):
            verdict = judge.compare(TASK, "ref",
                                    candidate("a", "one"),
                                    candidate("b", "two"))
        self.assertEqual(verdict["winner"], "")
        self.assertIn("unreachable", verdict["error"])

    def test_unparseable_reply_is_not_a_winner(self) -> None:
        with mock.patch.object(judge, "_chat", return_value="both look nice"):
            verdict = judge.compare(TASK, "ref",
                                    candidate("a", "one"),
                                    candidate("b", "two"))
        self.assertEqual(verdict["winner"], "")
        self.assertIn("unparseable", verdict["reason"])


if __name__ == "__main__":
    unittest.main()
