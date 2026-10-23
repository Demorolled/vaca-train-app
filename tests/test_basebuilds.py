"""Base builds: 100 unique, runnable, non-interactive programs per language."""
from __future__ import annotations

import unittest

from trainapp import basebuilds

# Constructs that would make a "base build" depend on input the harness cannot
# provide; every one of these has bitten a corpus before.
STDIN_MARKERS = ("input(", "sys.stdin", "raw_input(", "scanf(", "fgets(",
                 "getchar(", "readline(", "readLine(", "readln(", "Scanner(",
                 "gets(", "STDIN", "prompt(")
NETWORK_MARKERS = ("http://", "https://", "socket", "requests.", "fetch(")


class BaseBuildTests(unittest.TestCase):
    def test_every_language_has_a_hundred_unique_programs(self) -> None:
        for language in basebuilds.languages():
            programs = basebuilds.programs_for(language)
            self.assertGreaterEqual(len(programs), 100, language)
            codes = [p["code"] for p in programs]
            self.assertEqual(len(set(codes)), len(codes),
                             f"{language} has duplicate programs after dedupe")

    def test_programs_are_non_trivial_and_print_something(self) -> None:
        for language in basebuilds.languages():
            for program in basebuilds.programs_for(language)[:20]:
                self.assertGreater(len(program["code"]), 40, (language, program["title"]))
                self.assertRegex(program["code"],
                                 r"(?i)print|echo|puts|console|system\.out|cout|write",
                                 f"{language} {program['title']} prints nothing")

    def test_programs_do_not_wait_for_input_or_the_network(self) -> None:
        for language in basebuilds.languages():
            for program in basebuilds.programs_for(language):
                code = program["code"]
                for marker in STDIN_MARKERS:
                    self.assertNotIn(marker, code, f"{language}: {program['title']} reads stdin")
                for marker in NETWORK_MARKERS:
                    self.assertNotIn(marker, code, f"{language}: {program['title']} uses the network")

    def test_tasks_carry_the_library_shape(self) -> None:
        tasks = basebuilds.build(["python"], per_language=3)
        self.assertEqual(len(tasks), 3)
        task = tasks[0]
        self.assertEqual(task["origin"], "base-build")
        self.assertEqual(task["category"], "basics")
        self.assertTrue(task["runnable"])
        self.assertEqual(task["language"], "python")
        self.assertTrue(task["code"].strip())

    def test_counts_cover_every_known_language(self) -> None:
        counts = basebuilds.counts()
        self.assertEqual(sorted(counts), sorted(basebuilds.MODULES))
        self.assertTrue(all(v >= 100 for v in counts.values()), counts)


if __name__ == "__main__":
    unittest.main()
