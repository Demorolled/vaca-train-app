"""Focus: the five lanes the project trains on, and what the cut leaves out."""
from __future__ import annotations

import unittest

from trainapp import focus


class LaneTests(unittest.TestCase):
    def test_five_lanes_and_ts_js_share_one(self) -> None:
        self.assertEqual(len(focus.LANES), 5)
        self.assertEqual(focus.lane("typescript"), focus.lane("javascript"))
        self.assertEqual(focus.lane("typescript"), "JavaScript/TypeScript")

    def test_the_five_named_languages_are_the_lanes(self) -> None:
        self.assertEqual(
            {focus.lane(language) for language in focus.LANGUAGES},
            {"JavaScript/TypeScript", "Python", "Java", "Go", "C"})

    def test_php_is_out_of_the_focus_and_named_as_dropped(self) -> None:
        self.assertFalse(focus.in_focus("php"))
        self.assertEqual(focus.lane("php"), "")
        self.assertIn("php", focus.DROPPED)

    def test_dropped_languages_keep_their_own_lanes(self) -> None:
        for language in focus.DROPPED:
            self.assertFalse(focus.in_focus(language), language)

    def test_aliases_and_case_resolve_to_the_corpus_spelling(self) -> None:
        self.assertEqual(focus.canonical("TS"), "typescript")
        self.assertEqual(focus.canonical("js"), "javascript")
        self.assertEqual(focus.canonical(" py "), "python")
        self.assertTrue(focus.in_focus("TypeScript"))

    def test_c_and_cpp_are_not_the_same_lane(self) -> None:
        self.assertTrue(focus.in_focus("c"))
        self.assertFalse(focus.in_focus("cpp"))

    def test_c_does_not_swallow_csharp_or_other_c_prefixed_names(self) -> None:
        for language in ("csharp", "cs", "clojure", "cobol"):
            self.assertFalse(focus.in_focus(language), language)

    def test_keep_preserves_order_and_drops_the_rest(self) -> None:
        tasks = [{"language": "ruby"}, {"language": "go"}, {"language": "php"},
                 {"language": "python"}, {"language": "cpp"}]
        self.assertEqual([t["language"] for t in focus.keep(tasks)], ["go", "python"])
        self.assertEqual([t["language"] for t in focus.dropped(tasks)],
                         ["ruby", "php", "cpp"])

    def test_a_row_without_a_language_is_outside_the_focus(self) -> None:
        self.assertEqual(focus.keep([{"id": "x"}]), [])

    def test_stats_counts_lanes_and_names_what_the_cut_costs(self) -> None:
        tasks = [{"language": language} for language in
                 ("go", "go", "python", "php", "php", "ruby")]
        stats = focus.stats(tasks)
        self.assertEqual(stats["lanes"]["Go"], 2)
        self.assertEqual(stats["lanes"]["Python"], 1)
        self.assertEqual(stats["kept"], 3)
        self.assertEqual(stats["total"], 6)
        self.assertEqual(stats["outside"], {"php": 2, "ruby": 1})

    def test_describe_names_every_lane(self) -> None:
        text = focus.describe()
        for name in ("JavaScript/TypeScript", "Python", "Java", "Go", "C"):
            self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
