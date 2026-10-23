"""Repair loop: run → error → prompt → fix → prove → capture."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from trainapp import capture, repair


class FakeLLM:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.replies:
            return "print('no more replies')\n"
        return self.replies.pop(0)


class BrokenLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        raise repair.LLMError("LLM unreachable at http://127.0.0.1:11434: refused")


class RepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.dir = Path(self.tmp.name) / "nodes"
        self.dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev
        self.tmp.cleanup()

    def node(self, name: str, code: str) -> Path:
        path = self.dir / name
        path.write_text(code, encoding="utf-8")
        return path

    def test_prompt_is_the_operator_brief_from_the_memo(self) -> None:
        prompt = repair.build_prompt(
            filename="app.py", language="python", command="/usr/bin/python3 app.py",
            exit_code=1, output="Traceback: ZeroDivisionError", code="print(1/0)\n",
            goal="divide", attempt=1, max_attempts=3,
        )
        self.assertIn("Here is the file", prompt)
        self.assertIn("Command: /usr/bin/python3 app.py", prompt)
        self.assertIn("Exit code: 1", prompt)
        self.assertIn("Traceback: ZeroDivisionError", prompt)
        self.assertIn("Platform: ", prompt)
        self.assertIn("print(1/0)", prompt)
        self.assertIn("Return", prompt)
        self.assertIn("only", prompt)

    def test_extract_code_prefers_the_largest_fence(self) -> None:
        reply = "Here you go:\n```python\nprint('a')\n```\nand also\n```\nprint('b')\nprint('c')\n```"
        self.assertEqual(repair.extract_code(reply), "print('b')\nprint('c')\n")

    def test_extract_code_handles_unfenced_reply(self) -> None:
        self.assertEqual(repair.extract_code("print('plain')\n"), "print('plain')\n")

    def test_extract_code_strips_a_single_stray_fence(self) -> None:
        self.assertEqual(repair.extract_code("```python\nprint('x')\n"), "print('x')\n")

    def test_fixed_node_is_captured(self) -> None:
        path = self.node("broken.py", "print(1 / 0)\n")
        llm = FakeLLM(["```python\nprint(1 // 1)\n```"])

        result = repair.fix_node(path, goal="divide by one", llm=llm, timeout_s=30)

        self.assertEqual(result["status"], "fixed", result)
        self.assertTrue(result["captured"], result["captured_reason"])
        self.assertEqual(path.read_text(encoding="utf-8").strip(), "print(1 // 1)")
        self.assertEqual(len(llm.prompts), 1)

        rows = capture.load_rows()
        self.assertEqual(len(rows), 1)
        self.assertIn("Goal: divide by one", rows[0]["input"])
        self.assertIn("ZeroDivisionError", rows[0]["input"])
        self.assertEqual(rows[0]["output"], "print(1 // 1)")
        self.assertEqual(rows[0]["meta"]["attempts"], 1)
        self.assertTrue(Path(result["log"]).exists())

    def test_second_attempt_can_succeed(self) -> None:
        path = self.node("broken.py", "print(1 / 0)\n")
        llm = FakeLLM(["print(1 / 0)\n", "```python\nprint(2)\n```"])

        result = repair.fix_node(path, llm=llm, max_attempts=3, timeout_s=30)

        self.assertEqual(result["status"], "fixed", result)
        self.assertEqual(len(result["attempts"]), 2)
        self.assertFalse(result["attempts"][0]["changed"])
        self.assertTrue(result["attempts"][1]["ok"])
        self.assertEqual(len(capture.load_rows()), 1)

    def test_unfixed_node_is_not_captured_and_file_is_restored(self) -> None:
        original = "print(1 / 0)\n"
        path = self.node("broken.py", original)
        llm = FakeLLM(["still broken((", "still broken(("])

        result = repair.fix_node(path, llm=llm, max_attempts=2, timeout_s=30)

        self.assertEqual(result["status"], "failed", result)
        self.assertFalse(result["captured"])
        self.assertEqual(capture.load_rows(), [])
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertEqual(len(result["attempts"]), 2)

    def test_llm_failure_is_reported_and_nothing_is_captured(self) -> None:
        path = self.node("broken.py", "print(1 / 0)\n")
        llm = BrokenLLM()

        result = repair.fix_node(path, llm=llm, timeout_s=30)

        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["attempts"][0]["phase"], "llm")
        self.assertIn("unreachable", result["captured_reason"])
        self.assertFalse(result["captured"])

    def test_already_passing_node_does_not_call_the_llm(self) -> None:
        path = self.node("fine.py", "print('ok')\n")
        llm = FakeLLM([])
        result = repair.fix_node(path, llm=llm, timeout_s=30)
        self.assertEqual(result["status"], "already_passing")
        self.assertEqual(llm.prompts, [])

    def test_unknown_language_is_refused_before_running(self) -> None:
        path = self.node("notes.txt", "hello\n")
        result = repair.fix_node(path, llm=FakeLLM([]))
        self.assertEqual(result["status"], "error")
        self.assertIn("no execution schema", result["error"])


if __name__ == "__main__":
    unittest.main()
