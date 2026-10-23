"""The function-level probe: extraction, splicing, and the trainer's prompt shape."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trainapp import functionprobe


def python_set() -> dict:
    return {
        "id": "probe/set-1",
        "language": "python",
        "target": "main.py",
        "title": "print twice a number",
        "files": [
            {"path": "main.py",
             "content": ("from util import double\n\n\n"
                         "def greet(name):\n"
                         "    return 'hi ' + name\n\n\n"
                         "def main():\n"
                         "    print(greet('bob'), double(21))\n\n\n"
                         "if __name__ == '__main__':\n"
                         "    main()\n")},
            {"path": "util.py", "content": "def double(n):\n    return n * 2\n"},
        ],
    }


class FakeClient:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else ""


class ExtractionTests(unittest.TestCase):
    def test_python_functions_use_indent_blocks(self) -> None:
        found = functionprobe.find_functions("python", python_set()["files"][0]["content"])
        names = [f["signature"] for f in found]
        self.assertIn("def greet(name):", names)
        self.assertIn("def main():", names)
        main = next(f for f in found if f["signature"] == "def main():")
        self.assertEqual(main["block"], "def main():\n    print(greet('bob'), double(21))")

    def test_indented_brace_languages_are_found(self) -> None:
        csharp = ("class Program {\n"
                  "    static void Main(string[] args) {\n"
                  "        Console.WriteLine(1);\n"
                  "    }\n"
                  "}\n")
        found = functionprobe.find_functions("csharp", csharp)
        self.assertEqual([f["signature"] for f in found],
                         ["static void Main(string[] args) {"])
        self.assertEqual(found[0]["lines"], 3)

    def test_java_and_kotlin_are_found(self) -> None:
        java = ("public class A {\n"
                "    public static void main(String[] args) {\n"
                "        System.out.println(1);\n"
                "    }\n"
                "}\n")
        self.assertEqual(len(functionprobe.find_functions("java", java)), 1)
        kotlin = "fun main() {\n    println(1)\n}\n"
        self.assertEqual(len(functionprobe.find_functions("kotlin", kotlin)), 1)

    def test_typescript_arrow_functions_count(self) -> None:
        code = ("export const draw = (ctx: CanvasRenderingContext2D) => {\n"
                "  ctx.fillRect(0, 0, 1, 1);\n"
                "};\n")
        found = functionprobe.find_functions("typescript", code)
        self.assertEqual(len(found), 1)
        self.assertIn("draw", found[0]["signature"])

    def test_ruby_matches_nested_end(self) -> None:
        code = ("def render(items)\n"
                "  items.each do |item|\n"
                "    puts item\n"
                "  end\n"
                "end\n")
        found = functionprobe.find_functions("ruby", code)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["lines"], 5)

    def test_control_flow_is_not_a_function(self) -> None:
        code = "if (x) {\n  y();\n}\n"
        self.assertEqual(functionprobe.find_functions("csharp", code), [])

    def test_the_largest_function_is_the_one_asked_for(self) -> None:
        fn = functionprobe.largest_function("python", python_set()["files"][0]["content"])
        self.assertEqual(fn["signature"], "def greet(name):")


class SpliceTests(unittest.TestCase):
    def test_splice_replaces_only_the_span(self) -> None:
        code = python_set()["files"][0]["content"]
        fn = functionprobe.largest_function("python", code)
        out = functionprobe.splice(code, fn, "def greet(name):\n    return 'yo'")
        self.assertIn("def greet(name):\n    return 'yo'", out)
        self.assertNotIn("'hi ' + name", out)
        self.assertIn("def main():", out)
        self.assertIn("from util import double", out)


class ExtractBlockTests(unittest.TestCase):
    def test_imports_and_headers_are_dropped(self) -> None:
        reply = ("<?php\n\ndeclare(strict_types=1);\n\n"
                 "function formatCurrency(float $amount): string {\n"
                 "    return number_format($amount, 2, '.', ',');\n}\n")
        block = functionprobe.extract_block("php", reply, "function formatCurrency(float $amount): string {")
        self.assertNotIn("<?php", block)
        self.assertTrue(block.startswith("function formatCurrency"))

    def test_a_whole_program_is_narrowed_to_the_asked_for_function(self) -> None:
        reply = ("#include <iostream>\n\n"
                 "int fibonacci(int n) {\n    return n;\n}\n\n"
                 "int main() {\n    return fibonacci(3);\n}\n")
        block = functionprobe.extract_block("cpp", reply, "int fibonacci(int n) {")
        self.assertNotIn("#include", block)
        self.assertNotIn("main", block)
        self.assertIn("fibonacci", block)

    def test_a_receiver_is_not_mistaken_for_the_name(self) -> None:
        self.assertEqual(functionprobe.function_name("func (r *Repo) Save(x int) {"), "Save")
        self.assertEqual(functionprobe.function_name("public static void main(String[] a) {"),
                         "main")

    def test_an_unrecognisable_reply_is_left_alone(self) -> None:
        self.assertEqual(functionprobe.extract_block("python", "not code\n", "def f():"),
                         "not code\n")


class PromptTests(unittest.TestCase):
    def test_prompt_uses_the_trainers_template(self) -> None:
        task = python_set()
        fn = functionprobe.largest_function("python", task["files"][0]["content"])
        prompt = functionprobe.prompt_for(task, fn)
        self.assertTrue(prompt.startswith("### Instruction\n"))
        self.assertIn("\n\n### Input\n", prompt)
        self.assertTrue(prompt.endswith("### Response\n"))
        self.assertIn("### Sibling files (authoritative)", prompt)
        self.assertIn("def double(n):", prompt)
        self.assertIn(fn["signature"], prompt)

    def test_instruction_and_input_are_what_sft_trains(self) -> None:
        task = python_set()
        fn = functionprobe.largest_function("python", task["files"][0]["content"])
        instruction, given = functionprobe.prompt_parts(task, fn)
        self.assertIn("`main.py`", instruction)
        self.assertIn("do not invent members", instruction)
        self.assertIn("def double(n):", given)


class ProbeTests(unittest.TestCase):
    def test_reinserting_the_original_function_matches(self) -> None:
        task = python_set()
        fn = functionprobe.largest_function("python", task["files"][0]["content"])
        client = FakeClient([fn["block"]])
        row = functionprobe.probe(task, client, timeout_s=25)
        self.assertTrue(row["compile"], row["error"])
        self.assertTrue(row["match"], row)
        self.assertEqual(row["function_lines"], fn["lines"])
        self.assertEqual(row["task_id"], "probe/set-1")

    def test_a_wrong_function_is_a_failure_with_its_error(self) -> None:
        task = python_set()
        client = FakeClient(["def greet(name):\n    return 'wrong'\n"])
        row = functionprobe.probe(task, client, timeout_s=25)
        self.assertTrue(row["compile"])
        self.assertFalse(row["match"])

    def test_a_broken_function_does_not_compile(self) -> None:
        task = python_set()
        client = FakeClient(["def greet(name)\n    return 1\n"])
        row = functionprobe.probe(task, client, timeout_s=25)
        self.assertFalse(row["compile"])
        self.assertTrue(row["error"])

    def test_a_silent_reference_is_judged_on_compiling_and_staying_silent(self) -> None:
        task = {"id": "probe/silent", "language": "python", "target": "main.py",
                "files": [{"path": "main.py",
                           "content": ("def render():\n    return 'x'\n\n\n"
                                       "if __name__ == '__main__':\n    render()\n")}]}
        quiet = functionprobe.probe(task, FakeClient(["def render():\n    return 'y'\n"]),
                                    timeout_s=25)
        self.assertTrue(quiet["reference_ok"])
        self.assertTrue(quiet["match"], quiet)
        noisy = functionprobe.probe(task, FakeClient(["def render():\n    print('x')\n"]),
                                    timeout_s=25)
        self.assertFalse(noisy["match"])

    def test_a_set_whose_own_run_fails_is_a_skip_not_a_model_failure(self) -> None:
        task = {"id": "probe/broken", "language": "python", "target": "main.py",
                "files": [{"path": "main.py",
                           "content": ("def helper():\n    return 1\n\n\n"
                                       "raise SystemExit('boom')\n")}]}
        row = functionprobe.probe(task, FakeClient(["def helper():\n    return 2\n"]),
                                  timeout_s=25)
        self.assertEqual(row["skipped"], "reference failed")
        self.assertFalse(row.get("match"))

    def test_a_set_without_a_function_is_skipped_not_guessed(self) -> None:
        task = {"id": "probe/flat", "language": "python", "target": "main.py",
                "files": [{"path": "main.py", "content": "print(1)\n"}]}
        row = functionprobe.probe(task, FakeClient([]), timeout_s=25)
        self.assertEqual(row["skipped"], "no function")


class ExportTests(unittest.TestCase):
    def test_an_sft_row_carries_only_the_function(self) -> None:
        rows = [{"task_id": "a", "language": "python", "match": True,
                 "function": "def greet(name):",
                 "reply": "import os\n\ndef greet(name):\n    return 'hi'\n",
                 "instruction": "i", "input": "n", "prompt": "p"}]
        self.assertEqual(functionprobe.sft_rows(rows)[0]["output"],
                         "def greet(name):\n    return 'hi'\n")

    def test_only_passes_become_sft_rows(self) -> None:
        rows = [
            {"task_id": "a", "language": "python", "match": True, "reply": "def f():\n    return 1\n",
             "instruction": "i", "input": "n", "prompt": "p"},
            {"task_id": "b", "language": "python", "match": False, "reply": "def f():\n    return 2\n",
             "instruction": "i", "input": "n", "prompt": "p"},
        ]
        sft = functionprobe.sft_rows(rows)
        self.assertEqual(len(sft), 1)
        self.assertEqual(sft[0]["output"], "def f():\n    return 1\n")
        self.assertEqual(sft[0]["origin"], "function-probe")

    def test_a_row_says_whether_behaviour_or_only_compilation_was_proven(self) -> None:
        rows = [
            {"task_id": "a", "language": "python", "match": True, "reply": "x\n",
             "instruction": "i", "input": "n", "prompt": "p", "reference": "42"},
            {"task_id": "b", "language": "typescript", "match": True, "reply": "y\n",
             "instruction": "i", "input": "n", "prompt": "p", "reference": ""},
        ]
        self.assertEqual([r["verified"] for r in functionprobe.sft_rows(rows)],
                         ["behaviour", "compile"])

    def test_pairs_need_the_same_prompt(self) -> None:
        rows = [
            {"task_id": "a", "language": "python", "match": True, "reply": "good\n",
             "prompt": "P1"},
            {"task_id": "b", "language": "python", "match": False, "reply": "bad\n",
             "prompt": "P1"},
            {"task_id": "c", "language": "python", "match": False, "reply": "other\n",
             "prompt": "P2"},
        ]
        pairs = functionprobe.pair_rows(rows)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["chosen"], "good\n")
        self.assertEqual(pairs[0]["rejected"], "bad\n")


class CandidateTests(unittest.TestCase):
    def test_every_language_that_can_hold_a_function_is_probed(self) -> None:
        for language in ("csharp", "java", "kotlin", "swift", "php", "ruby",
                         "typescript", "javascript", "go", "rust", "python"):
            self.assertIn(language, functionprobe.LANGUAGES, language)


if __name__ == "__main__":
    unittest.main()
