"""Validation: statuses must be earned by the real toolchain."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from trainapp import execution, library, validate

TASK = {"id": "test/ok", "language": "python", "title": "ok",
        "code": "print('library')\n", "runnable": True, "origin": "test"}


class ValidationTests(unittest.TestCase):
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

    def test_working_program_is_verified(self) -> None:
        record = validate.validate_task(TASK)
        self.assertEqual(record["status"], "verified", record)
        self.assertEqual(record["exit_code"], 0)
        self.assertIn("library", record["stdout"])

    def test_broken_program_is_failed_with_evidence(self) -> None:
        record = validate.validate_task({**TASK, "code": "def broken(:\n"})
        self.assertEqual(record["status"], "failed")
        self.assertNotEqual(record["exit_code"], 0)
        self.assertIn("SyntaxError", record["stderr"])

    def test_program_that_never_exits_is_a_timeout(self) -> None:
        record = validate.validate_task({**TASK, "code": "import time\ntime.sleep(5)\n"},
                                        timeout_s=0.5)
        self.assertEqual(record["status"], "timeout")

    def test_missing_toolchain_says_so(self) -> None:
        fake = execution.Toolchain(
            language="python", extensions=(".py",), bins=("no-such-toolchain-xyz",),
            version_args=("--version",), check_steps=(), run_steps=(("{bin}", "{file}"),),
            install={"linux": "apt install python3", "windows": "winget install Python"},
        )
        original = execution.TOOLCHAINS["python"]
        execution.TOOLCHAINS["python"] = fake
        try:
            record = validate.validate_task(TASK)
        finally:
            execution.TOOLCHAINS["python"] = original
        self.assertEqual(record["status"], "toolchain_missing")
        self.assertIn("no-such-toolchain-xyz", record["error"])

    @unittest.skipUnless(execution.resolve_bin("csharp"), "dotnet not installed")
    def test_snippet_without_entry_point_is_a_component(self) -> None:
        record = validate.validate_task(
            {"id": "test/component", "language": "csharp", "origin": "test",
             "runnable": True, "title": "reverse",
             "code": "static string Reverse(string s) { return s; }\n"}, timeout_s=180)
        self.assertEqual(record["status"], "component", record)
        self.assertIn("no entry point", record.get("note", ""))

    @unittest.skipUnless(execution.resolve_bin("csharp"), "dotnet not installed")
    def test_csharp_program_with_main_is_verified(self) -> None:
        record = validate.validate_task(
            {"id": "test/cs-main", "language": "csharp", "origin": "test",
             "runnable": True, "title": "hello",
             "code": "class P { static void Main() { System.Console.WriteLine(7); } }"},
            timeout_s=180)
        self.assertEqual(record["status"], "verified", record)
        self.assertIn("7", record["stdout"])

    def test_unknown_language_is_unsupported(self) -> None:
        record = validate.validate_task({**TASK, "language": "cobol"})
        self.assertEqual(record["status"], "unsupported")

    def test_filtered_run_preserves_other_records(self) -> None:
        library.build()
        tasks = library.load_tasks()
        python_tasks = [t for t in tasks if t["language"] == "python"][:1]
        self.assertTrue(python_tasks)
        library.validation_path().write_text(
            json.dumps({"id": "keep/me", "language": "go", "status": "verified"}) + "\n",
            encoding="utf-8")
        validate.run(python_tasks, jobs=1, timeout_s=10, skip_typescript=True)
        kept = library.load_validation()
        self.assertIn("keep/me", kept)
        self.assertIn(python_tasks[0]["id"], kept)
        self.assertEqual(validate.status()["state"], "done")


class FileSetValidationTests(unittest.TestCase):
    """A multi-file task is proven as a set, with its adherence recorded."""

    def set_task(self, target_code: str) -> dict:
        return {
            "id": "vaca-export/demo-util", "language": "python", "runnable": True,
            "title": "demo — util.py", "description": "print the total",
            "files": [
                {"path": "main.py", "content": "from util import total\nprint(total())\n"},
                {"path": "util.py", "content": target_code},
            ],
            "target": "util.py", "code": target_code,
        }

    def test_a_set_that_builds_is_verified(self) -> None:
        record = validate.validate_task(
            self.set_task("def total():\n    return 3\n"))
        self.assertEqual(record["status"], "verified")
        self.assertEqual(record["file_count"], 2)
        self.assertEqual(record["adherence"], 1.0)
        self.assertEqual(record["target"], "util.py")

    def test_a_target_the_sibling_cannot_use_fails(self) -> None:
        record = validate.validate_task(
            self.set_task("def other():\n    return 3\n"))
        self.assertEqual(record["status"], "failed")
        self.assertIn("adherence", record)

    def test_a_syntax_error_in_the_target_is_failed_with_evidence(self) -> None:
        # The set's entry is main.py, so the broken module is discovered when the
        # program imports it — the build still fails, with the real traceback.
        record = validate.validate_task(self.set_task("def total(:\n"))
        self.assertEqual(record["status"], "failed")
        self.assertIn("SyntaxError", record["stderr"])


if __name__ == "__main__":
    unittest.main()
