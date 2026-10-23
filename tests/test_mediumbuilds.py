"""Medium builds: multi-function programs, 100 per implemented language."""
from __future__ import annotations

import re
import unittest

from trainapp import mediumbuilds

# Regexes, because `sscanf` parses a buffer the program already holds and is not
# stdin: a plain `"scanf(" in code` marker would reject it.
STDIN_PATTERNS = (r"\binput\(", r"\bsys\.stdin\b", r"(?<![A-Za-z_])scanf\(",
                  r"\bfgets\(", r"\bgetchar\(", r"\breadLine\(", r"\breadln\(",
                  r"\bScanner\(", r"\bgets\(", r"\bSTDIN\b")
NETWORK_MARKERS = ("http://", "https://", "socket", "requests.", "fetch(")
# A medium program must have a data structure in it, not just a loop.
DATA_MARKERS = ("{", "[", "Map", "map", "Dictionary", "dict", "HashMap",
                "struct", "class", "List", "vector", "Vec")

# Each language's declaration keyword, used to prove there are several functions
# rather than one long main().
DECLARATIONS = {
    "python": ("def ", 2),
    "cpp": ("(", 2),
    "java": ("static ", 2),
    "csharp": ("static ", 2),
    "go": ("func ", 2),
}


class MediumBuildTests(unittest.TestCase):
    def test_implemented_languages_have_a_hundred_unique_programs(self) -> None:
        self.assertTrue(mediumbuilds.languages(), "no medium generator is implemented")
        for language in mediumbuilds.languages():
            programs = mediumbuilds.programs_for(language)
            self.assertGreaterEqual(len(programs), 100, language)
            codes = [p["code"] for p in programs]
            self.assertEqual(len(set(codes)), len(codes),
                             f"{language} has duplicate programs after dedupe")

    def test_programs_are_multi_function_and_carry_a_data_structure(self) -> None:
        for language in mediumbuilds.languages():
            marker, minimum = DECLARATIONS.get(language, ("(", 2))
            for program in mediumbuilds.programs_for(language):
                code = program["code"]
                # Python and Ruby need no type declarations or braces, so
                # their programs run 330-500 bytes while compiled ones are
                # 600-1600. 300 still separates a medium program from a base
                # build, which is a handful of lines.
                self.assertGreater(len(code), 300, (language, program["title"]))
                self.assertGreaterEqual(code.count(marker), minimum,
                                        f"{language} {program['title']} is not multi-function")
                self.assertTrue(any(token in code for token in DATA_MARKERS),
                                f"{language} {program['title']} has no data structure")

    def test_programs_do_not_wait_for_input_or_the_network(self) -> None:
        for language in mediumbuilds.languages():
            for program in mediumbuilds.programs_for(language):
                code = program["code"]
                for pattern in STDIN_PATTERNS:
                    self.assertIsNone(re.search(pattern, code),
                                      f"{language}: {program['title']} reads stdin")
                for marker in NETWORK_MARKERS:
                    self.assertNotIn(marker, code, f"{language}: {program['title']}")

    def test_tasks_carry_the_library_shape(self) -> None:
        tasks = mediumbuilds.build(["python"], per_language=3)
        self.assertEqual(len(tasks), 3)
        task = tasks[0]
        self.assertEqual(task["origin"], "medium-build")
        self.assertEqual(task["category"], "medium")
        self.assertTrue(task["runnable"])
        self.assertEqual(task["language"], "python")

    def test_unimplemented_languages_are_named_rather_than_crashing(self) -> None:
        known = set(mediumbuilds.MODULES)
        implemented = set(mediumbuilds.languages())
        missing = set(mediumbuilds.missing())
        self.assertEqual(implemented | missing, known)
        self.assertFalse(implemented & missing)
        for language in missing:
            with self.assertRaises(KeyError):
                mediumbuilds.programs_for(language)


if __name__ == "__main__":
    unittest.main()
