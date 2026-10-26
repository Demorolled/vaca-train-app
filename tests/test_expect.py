"""The expected output a requirement carries in its own words."""
from __future__ import annotations

import unittest

from trainapp import expect


class DeriveTests(unittest.TestCase):
    def test_a_quoted_output_is_the_literal(self) -> None:
        self.assertEqual(expect.derive('a CLI that prints "Hello, ada"')["expected"],
                         "Hello, ada")
        self.assertEqual(expect.derive("a script that prints 'ready'")["expected"],
                         "ready")
        self.assertEqual(expect.derive('prints the message "done"')["expected"], "done")

    def test_a_stated_number_is_the_output(self) -> None:
        self.assertEqual(expect.derive("a program that prints 42")["expected"], "42")
        self.assertEqual(expect.derive("prints the result 7")["expected"], "7")

    def test_a_sum_in_words_is_computed(self) -> None:
        derived = expect.derive("a program that prints the sum of 2 and 3")
        self.assertEqual(derived["expected"], "5")
        self.assertIn("sum of 2 and 3", derived["rule"])

    def test_the_other_worded_operations_are_computed(self) -> None:
        self.assertEqual(expect.derive("prints the product of 4 and 6")["expected"], "24")
        self.assertEqual(expect.derive("prints the difference of 10 and 3")["expected"], "7")
        self.assertEqual(expect.derive("prints the quotient of 8 and 2")["expected"], "4")

    def test_a_quotient_that_does_not_divide_exactly_is_not_derived(self) -> None:
        # 7/2 is 3 or 3.5 depending on the language: the sentence does not say.
        self.assertEqual(expect.derive("prints the quotient of 7 and 2")["expected"], "")
        self.assertEqual(expect.derive("prints the quotient of 1 and 0")["expected"], "")

    def test_a_signed_expression_is_computed(self) -> None:
        self.assertEqual(expect.derive("a script that prints 2 + 3")["expected"], "5")
        self.assertEqual(expect.derive("a script that prints 10 - 4")["expected"], "6")
        self.assertEqual(expect.derive("a script that prints 3 * 4")["expected"], "12")

    def test_an_output_that_needs_an_oracle_is_not_guessed(self) -> None:
        for requirement in ("a program that prints the first 12 primes",
                            "a CLI that counts the lines in a file",
                            "a script that prints the current date",
                            ""):
            self.assertEqual(expect.derive(requirement)["expected"], "", requirement)

    def test_a_year_or_a_version_is_not_read_as_an_output(self) -> None:
        self.assertEqual(expect.derive("a CLI that prints the year 2026-01-01")["expected"], "")


class WantsOutputTests(unittest.TestCase):
    def test_a_requirement_that_prints_is_recognised(self) -> None:
        for text in ("a program that prints the sum of 2 and 3",
                     "a CLI that outputs a table",
                     "a script that echoes its argument",
                     "writes a report to stdout"):
            self.assertTrue(expect.wants_output(text), text)

    def test_a_requirement_that_reads_nothing_back_is_not(self) -> None:
        for text in ("a program that validates a JSON file",
                     "a linter that exits 1 on a syntax error"):
            self.assertFalse(expect.wants_output(text), text)


if __name__ == "__main__":
    unittest.main()
