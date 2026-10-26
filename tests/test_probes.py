"""The contract gate: the checks that keep a round from being declared a win."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import probes

GOOD_GO = "package main\n\nimport \"fmt\"\n\nfunc main() {\n\tfmt.Println(\"hi\")\n}\n"
FILLED_GO = ("package main\n\nimport \"fmt\"\n\nfunc main() {\n"
             "\tfmt.Println(\"hello\")\n}\n")
FENCED_GO = "```go\n" + GOOD_GO + "```\n"


class CheckTests(unittest.TestCase):
    def assertFails(self, pid: str, text: str, needle: str = "") -> None:
        verdict = probes.check(pid, text)
        self.assertTrue(verdict["scored"], pid)
        self.assertFalse(verdict["ok"], text)
        if needle:
            self.assertIn(needle, verdict["reason"])

    def test_write_lanes_reject_fences(self) -> None:
        self.assertFails("write-go", FENCED_GO, "fence")
        self.assertTrue(probes.check("write-go", GOOD_GO)["ok"])

    def test_duplicate_block_is_a_failure(self) -> None:
        self.assertFails("scaffold-fill", FILLED_GO + "\n" + FILLED_GO, "duplicate")

    def test_scaffold_fill_must_replace_the_body(self) -> None:
        kept = ("package main\n\nimport \"fmt\"\n\nfunc main() {\n"
                "\t// TODO: implement\n\tfmt.Println()\n}\n")
        self.assertFails("scaffold-fill", kept, "TODO")
        echoed = "// generated from template for Go CLI\n" + FILLED_GO
        self.assertFails("scaffold-fill", echoed, "scaffold text")
        self.assertTrue(probes.check("scaffold-fill", FILLED_GO)["ok"])

    def test_scaffold_invent_must_not_create_files(self) -> None:
        self.assertFails("scaffold-invent", GOOD_GO + "\nFILE: config.go\n", "FILE:")
        self.assertTrue(probes.check("scaffold-invent", GOOD_GO)["ok"])

    def test_plan_must_keep_the_requested_shape(self) -> None:
        good = "src/main.rs (Rust) — word counting CLI\n"
        self.assertTrue(probes.check("plan-rust", good)["ok"])
        self.assertFails("plan-rust", "Cargo.toml (1)\n", "shape")
        self.assertFails("plan-rust", "".join(
            f"src/m{i}.rs (Rust) — module {i}\n" for i in range(10)), "over-planned")
        self.assertFails("plan-node", "```\napi.js (JavaScript) — api\n```", "fence")

    def test_reasoning_probes_keep_their_lane(self) -> None:
        self.assertFails("reason-prime", "def is_prime(n):\n    return True\n", "code")
        self.assertTrue(probes.check("reason-prime", "Yes — 17 is prime.")["ok"])
        # The champion answered in prose and was failed by a literal string test.
        self.assertTrue(probes.check(
            "reason-prime",
            "True. It is a prime number because it has no divisors other than 1 "
            "and itself (17).")["ok"])
        self.assertFails("reason-prime", "I would need to think about it.", "never answered")
        self.assertTrue(probes.check("reason-silent", "1081")["ok"])
        self.assertFails("reason-silent", "23 * 47 = 1081", "number")

    def test_repair_must_delete_the_dead_variable(self) -> None:
        dead = "package main\n\nimport \"fmt\"\n\nfunc main() {\n\tx := 1\n\tfmt.Println(\"hi\")\n}\n"
        self.assertFails("repair-go", dead, "dead variable")
        self.assertTrue(probes.check("repair-go", GOOD_GO)["ok"])

    def test_lane_probes_are_recorded_but_not_graded(self) -> None:
        for pid in ("role-what", "scaffold-who", "meta-reason"):
            verdict = probes.check(pid, "VACA is an app builder.")
            self.assertFalse(verdict["scored"], pid)
            self.assertTrue(verdict["ok"], pid)


class GateTests(unittest.TestCase):
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

    def test_lane_stats_say_which_contract_moved(self) -> None:
        passed = [pid for pid in probes.SCORED
                  if not pid.startswith(("write-", "scaffold-", "repair-"))]
        lanes = probes.lane_stats({"passed_ids": passed})
        self.assertEqual(lanes["write"], {"passed": 0, "total": 3})
        self.assertEqual(lanes["plan"], {"passed": 2, "total": 2})
        self.assertEqual(lanes["scaffold"], {"passed": 0, "total": 2})
        self.assertEqual(lanes["reason"], {"passed": 2, "total": 2})
        self.assertEqual(sum(s["total"] for s in lanes.values()), 10)

    def test_regressions_reports_only_lost_probes(self) -> None:
        baseline = {"passed_ids": ["write-go", "reason-prime", "plan-rust"]}
        current = {"passed_ids": ["plan-rust"],
                   "failures": [{"id": "write-go", "reason": "2 fence marker(s)"},
                                {"id": "reason-prime", "reason": "answered with code"}]}
        broke = probes.regressions(baseline, current)
        self.assertEqual([b["id"] for b in broke], ["reason-prime", "write-go"])
        self.assertEqual(broke[1]["reason"], "2 fence marker(s)")
        self.assertEqual(probes.regressions(baseline, baseline), [])

    def test_evaluate_scores_a_coder_and_records_it(self) -> None:
        class Coder:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def complete(self, prompt: str) -> str:
                if "Is 17 prime" in prompt:
                    return "Yes — 17 is prime."
                if "23 * 47" in prompt:
                    return "1081"
                return FENCED_GO

            def close(self) -> None:
                pass

        with mock.patch("trainapp.localcoder.LocalCoder", Coder):
            result = probes.evaluate("fake/model", "data/models/clean1/adapter")
        self.assertEqual(result["total"], 10)
        self.assertIn("reason-prime", result["passed_ids"])
        self.assertIn("reason-silent", result["passed_ids"])
        self.assertIn("write-go", [f["id"] for f in result["failures"]])
        self.assertTrue(probes.summary(result)["passed"] <= result["total"])
        rows = [json.loads(line) for line in
                (Path(self.tmp.name) / "probes" / "probes.jsonl").read_text().splitlines()]
        self.assertEqual(rows[-1]["arm"], "fake/model+clean1")

    def test_a_probe_is_graded_by_the_majority_of_its_runs(self) -> None:
        """A lane is not lost to one unlucky answer at temperature."""
        answers = {"count": 0}

        class FlakyCoder:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def complete(self, prompt: str) -> str:
                if "Is 17 prime" in prompt:
                    answers["count"] += 1
                    # first run drifts into code, the other two answer
                    return ("def is_prime(n):\n    return True\n"
                            if answers["count"] % 3 == 1 else "Yes — 17 is prime.")
                if "23 * 47" in prompt:
                    return "23 * 47 = 1081"          # fails every run
                return GOOD_GO

            def close(self) -> None:
                pass

        with mock.patch("trainapp.localcoder.LocalCoder", FlakyCoder):
            result = probes.evaluate("fake/model", samples=3)
        self.assertIn("reason-prime", result["passed_ids"])
        failed = {f["id"]: f["reason"] for f in result["failures"]}
        self.assertIn("reason-silent", failed)
        self.assertIn("0/3 runs passed", failed["reason-silent"])
        self.assertNotIn("write-go", failed)

        rows = [json.loads(line) for line in
                (Path(self.tmp.name) / "probes" / "probes.jsonl").read_text().splitlines()]
        by_id = {row["id"]: row for row in rows[-1]["rows"]}
        self.assertEqual((by_id["reason-prime"]["passed_runs"], by_id["reason-prime"]["runs"]),
                         (2, 3))

    def test_a_split_probe_is_rechecked_before_it_counts(self) -> None:
        """2/3 is not a verdict: a second batch decides the pooled majority."""
        calls = {"prime": 0}

        class Split:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def complete(self, prompt: str) -> str:
                if "Is 17 prime" in prompt:
                    calls["prime"] += 1
                    # two of the first three pass, all three of the recheck fail
                    return ("Yes — 17 is prime." if calls["prime"] in (2, 3)
                            else "def is_prime(n):\n    return True\n")
                if "23 * 47" in prompt:
                    return "1081"
                return GOOD_GO

            def close(self) -> None:
                pass

        with mock.patch("trainapp.localcoder.LocalCoder", Split):
            result = probes.evaluate("fake/model", samples=3, confirm=3,
                                     temperature=0.7)
        failed = {f["id"]: f["reason"] for f in result["failures"]}
        self.assertIn("reason-prime", failed)
        self.assertIn("2/6 runs passed", failed["reason-prime"])
        self.assertEqual(result["rechecked"], ["reason-prime"])
        rows = [json.loads(line) for line in
                (Path(self.tmp.name) / "probes" / "probes.jsonl").read_text().splitlines()]
        row = {r["id"]: r for r in rows[-1]["rows"]}["reason-prime"]
        self.assertEqual((row["passed_runs"], row["runs"], row["rechecked"]),
                         (2, 6, True))

    def test_a_contested_probe_that_survives_the_recheck_keeps_its_point(self) -> None:
        calls = {"plan": 0}
        good = "src/main.rs (Rust) — word counting CLI\n"
        bad = "".join(f"src/m{i}.rs (Rust) — module {i}\n" for i in range(10))

        class Recovers:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def complete(self, prompt: str) -> str:
                if "Rust CLI that counts words" in prompt:
                    calls["plan"] += 1
                    # 2/3 first, 2/3 again: 4/6 pooled, a pass
                    return bad if calls["plan"] in (1, 6) else good
                if "Is 17 prime" in prompt:
                    return "Yes — 17 is prime."
                if "23 * 47" in prompt:
                    return "1081"
                return GOOD_GO

            def close(self) -> None:
                pass

        with mock.patch("trainapp.localcoder.LocalCoder", Recovers):
            result = probes.evaluate("fake/model", samples=3, confirm=3,
                                     temperature=0.7)
        self.assertIn("plan-rust", result["passed_ids"])
        self.assertEqual(result["rechecked"], ["plan-rust"])
        self.assertEqual(calls["plan"], 6)

    def test_an_unanimous_probe_is_not_asked_again(self) -> None:
        calls = {"prime": 0}

        class Steady:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def complete(self, prompt: str) -> str:
                if "Is 17 prime" in prompt:
                    calls["prime"] += 1
                    return "Yes — 17 is prime."
                if "23 * 47" in prompt:
                    return "1081"
                return GOOD_GO

            def close(self) -> None:
                pass

        with mock.patch("trainapp.localcoder.LocalCoder", Steady):
            result = probes.evaluate("fake/model", samples=3, confirm=3,
                                     temperature=0.7)
        self.assertEqual(calls["prime"], 3)
        self.assertEqual(result["rechecked"], [])

    def test_the_gate_asks_the_coder_for_the_app_sampling(self) -> None:
        """Greedy decodes are one answer printed three times, not three samples."""
        seen: dict = {}

        class Coder:
            def __init__(self, *args, **kwargs) -> None:
                seen.update(kwargs)

            def complete(self, prompt: str) -> str:
                return GOOD_GO

            def close(self) -> None:
                pass

        with mock.patch("trainapp.localcoder.LocalCoder", Coder):
            probes.evaluate("fake/model", samples=3, confirm=3,
                            temperature=0.7, top_p=0.9)
        self.assertEqual((seen["temperature"], seen["top_p"]), (0.7, 0.9))

    def test_a_greedy_gate_says_its_samples_are_not_independent(self) -> None:
        notes: list[str] = []

        class Coder:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def complete(self, prompt: str) -> str:
                return GOOD_GO

            def close(self) -> None:
                pass

        with mock.patch("trainapp.localcoder.LocalCoder", Coder):
            probes.evaluate("fake/model", samples=3, log=notes.append)
        self.assertTrue(any("repeat one decode" in line for line in notes))


if __name__ == "__main__":
    unittest.main()
