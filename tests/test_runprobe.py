"""Observable runs: argv plumbing and a probe that never guesses."""
from __future__ import annotations

import unittest

from trainapp import execution, runprobe


def task(content: str, language: str = "python") -> dict:
    return {"id": "probe/set", "language": language, "target": "main.py",
            "files": [{"path": "main.py", "content": content}]}


class ArgvTests(unittest.TestCase):
    def test_arguments_reach_the_program(self) -> None:
        result = execution.run_files(
            [{"path": "main.py",
              "content": "import sys\nprint(' '.join(sys.argv[1:]))\n"}],
            "python", entry="main.py", timeout_s=20, args=["--help", "x"])
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.stdout.strip(), "--help x")

    def test_no_arguments_keeps_the_default_run(self) -> None:
        result = execution.run_files(
            [{"path": "main.py", "content": "print('plain')\n"}],
            "python", entry="main.py", timeout_s=20)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.stdout.strip(), "plain")


class DiscoverTests(unittest.TestCase):
    def test_a_usage_line_on_help_is_observable(self) -> None:
        got = runprobe.discover(task(
            "import sys\n"
            "if '--help' in sys.argv:\n"
            "    print('usage: report --help')\n"), timeout_s=20)
        self.assertIsNotNone(got)
        self.assertEqual(got["args"], ["--help"])
        self.assertIn("usage", got["stdout"])

    def test_a_silent_set_is_not_observable(self) -> None:
        self.assertIsNone(runprobe.discover(
            task("x = 1\n"), timeout_s=20))

    def test_output_that_changes_between_runs_is_rejected(self) -> None:
        self.assertIsNone(runprobe.discover(task(
            "import random, sys\n"
            "print(random.random())\n"
            "print('usage', file=sys.stderr)\n"), timeout_s=20))

    def test_a_stored_probe_is_found_by_task(self) -> None:
        probes = {"probe/set": {"task_id": "probe/set", "args": ["--help"],
                                "language": "python", "stdout": "usage"}}
        self.assertEqual(runprobe.for_task(task("x = 1\n"), probes)["args"], ["--help"])
        self.assertIsNone(runprobe.for_task({"id": "other"}, probes))


if __name__ == "__main__":
    unittest.main()
