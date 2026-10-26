"""The autoloop's policy: what counts as progress, and what it does without it."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import autoloop


def scored(family: int, task: int = 9, gate: int = 7) -> dict:
    return {"family": autoloop.metrics(family, 48), "task": autoloop.metrics(task, 24),
            "gate": {"passed": gate, "total": 10}, "adapter": "fake"}


def with_rows(flags: list[bool], task: int = 9, gate: int = 7) -> dict:
    """An arm that recorded which held-out sets it passed."""
    armed = scored(sum(flags), task=task, gate=gate)
    armed["rows"] = {"family": [{"task_id": f"held/{i}", "match": flag,
                                  "compile": flag} for i, flag in enumerate(flags)]}
    return armed


def flip(base: list[bool], gained: int, lost: int) -> list[bool]:
    """The same 52 sets with `gained` turned on and `lost` turned off."""
    out = list(base)
    off = [i for i, flag in enumerate(out) if not flag][:gained]
    on = [i for i, flag in enumerate(out) if flag][:lost]
    for i in off:
        out[i] = True
    for i in on:
        out[i] = False
    return out


class JudgeTests(unittest.TestCase):
    def test_a_paired_gain_that_survives_the_noise_is_a_win(self) -> None:
        base = [False] * 37 + [True] * 15
        accepted, reason = autoloop.judge(with_rows(base), with_rows(flip(base, 9, 2)))
        self.assertTrue(accepted)
        self.assertIn("p=0.065", reason)

    def test_a_gain_a_language_swap_could_carry_is_not(self) -> None:
        """The first champion's +3: +6/-3, p=0.51, two families moving both ways."""
        base = [False] * 37 + [True] * 15
        accepted, reason = autoloop.judge(with_rows(base), with_rows(flip(base, 6, 3)))
        self.assertFalse(accepted)
        self.assertIn("does not survive pairing", reason)
        self.assertIn("p=0.508", reason)

    def test_a_family_gain_is_a_win(self) -> None:
        accepted, reason = autoloop.judge(scored(14), scored(16))
        self.assertTrue(accepted)
        self.assertIn("+2", reason)

    def test_a_family_loss_is_not(self) -> None:
        accepted, reason = autoloop.judge(scored(16), scored(14))
        self.assertFalse(accepted)
        self.assertIn("not a gain", reason)

    def test_behaviour_bought_with_the_format_lane_is_refused(self) -> None:
        accepted, reason = autoloop.judge(scored(14, gate=7), scored(20, gate=3))
        self.assertFalse(accepted)
        self.assertIn("gate fell", reason)

    def test_a_gate_refusal_names_the_lanes_it_lost(self) -> None:
        best = scored(15, gate=7)
        best["gate"].update({"passed_ids": ["plan-rust", "plan-node",
                                           "reason-prime", "reason-silent"]})
        cand = scored(15, gate=5)
        cand["gate"].update({"passed_ids": ["plan-node", "reason-silent"]})
        accepted, reason = autoloop.judge(best, cand)
        self.assertFalse(accepted)
        self.assertIn("plan-rust (plan)", reason)
        self.assertIn("reason-prime (reason)", reason)

    def test_a_contract_repair_without_regression_is_kept(self) -> None:
        """Cycles 2 and 3: fences and scaffolds fixed, family inside noise."""
        base = [False] * 37 + [True] * 15
        best = with_rows(base, task=11, gate=4)
        cand = with_rows(flip(base, 5, 2), task=16, gate=8)
        accepted, reason = autoloop.judge(best, cand)
        self.assertTrue(accepted)
        self.assertIn("contract repaired 4 -> 8", reason)

    def test_a_pool_score_separates_build_failures_from_wrong_answers(self) -> None:
        """`undefined: sort` and a Python traceback are not the same problem."""
        score = autoloop.metrics(14, 70, build_failed=33)
        self.assertEqual(score["build_failed"], 33)
        self.assertEqual(score["built"], 37)
        self.assertEqual(score["wrong_output"], 37 - 14)
        plain = autoloop.metrics(14, 70)
        self.assertNotIn("build_failed", plain)

    def test_two_draws_are_paired_on_their_totals(self) -> None:
        """A set matched twice is not the same evidence as a set matched once."""
        best = {"rows": {"family": [
            {"task_id": f"held/{i}", "matches": 0 if i < 20 else 2, "draws": 2}
            for i in range(40)]}}
        same = {"rows": {"family": [
            {"task_id": f"held/{i}", "matches": 0 if i < 20 else 2, "draws": 2}
            for i in range(40)]}}
        better = {"rows": {"family": [
            {"task_id": f"held/{i}", "matches": 1 if i < 20 else 2, "draws": 2}
            for i in range(40)]}}
        self.assertEqual(autoloop.paired_gain(best, same)["gained"], 0)
        gain = autoloop.paired_gain(best, better)
        self.assertEqual(gain["gained"], 20)
        self.assertEqual(gain["lost"], 0)

    def test_rows_from_a_different_number_of_draws_are_not_paired(self) -> None:
        best = {"rows": {"family": [
            {"task_id": f"held/{i}", "match": i % 2 == 0} for i in range(40)]}}
        cand = {"rows": {"family": [
            {"task_id": f"held/{i}", "matches": 2, "draws": 2} for i in range(40)]}}
        self.assertIsNone(autoloop.paired_gain(best, cand))

    def test_a_contract_repair_that_regresses_task_behaviour_is_not_kept(self) -> None:
        base = [False] * 37 + [True] * 15
        best = with_rows(base, task=19, gate=4)
        cand = with_rows(flip(base, 5, 2), task=12, gate=8)
        accepted, reason = autoloop.judge(best, cand)
        self.assertFalse(accepted)
        self.assertNotIn("contract repaired", reason)

    def test_a_contract_repair_cannot_be_bought_with_a_family_regression(self) -> None:
        base = [False] * 37 + [True] * 15
        best = with_rows(base, task=11, gate=4)
        cand = with_rows(flip(base, 2, 8), task=19, gate=8)
        accepted, reason = autoloop.judge(best, cand)
        self.assertFalse(accepted)
        self.assertNotIn("contract repaired", reason)

    def test_a_gate_without_ids_still_gives_a_verdict(self) -> None:
        accepted, reason = autoloop.judge(scored(15, gate=7), scored(15, gate=4))
        self.assertFalse(accepted)
        self.assertIn("no ids recorded", reason)

    def test_one_lost_probe_is_tolerated(self) -> None:
        accepted, _ = autoloop.judge(scored(14, gate=7), scored(16, gate=6))
        self.assertTrue(accepted)

    def test_a_level_family_split_can_still_win_on_breadth(self) -> None:
        accepted, reason = autoloop.judge(scored(15, task=9), scored(15, task=12))
        self.assertTrue(accepted)
        self.assertIn("task-level", reason)

    def test_a_level_family_split_without_breadth_is_a_loss(self) -> None:
        accepted, _ = autoloop.judge(scored(15, task=9), scored(15, task=10))
        self.assertFalse(accepted)


class RecipeTests(unittest.TestCase):
    """The base recipe: compound on the champion, and do not over-update."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self.restore)
        autoloop.stop_path().unlink(missing_ok=True)

    def restore(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev

    def test_a_second_cycle_trains_on_the_champion_not_the_base(self) -> None:
        """Starting every round from the base is why the curve could not compound."""
        backend = autoloop.FakeBackend()
        autoloop.run(cycles=2, hours=0, backend=backend)
        self.assertEqual(backend.inits[0], "")
        self.assertEqual(backend.inits[1], "fake/auto1/orpo")

    def test_the_backend_can_train_on_the_uncut_corpus(self) -> None:
        """The A/B turns one switch; everything else stays the loop's recipe."""
        backend = autoloop.RealBackend(all_languages=True)
        prepared = {"night_rows": 0, "night_pairs": 0, "library_rows": 0,
                    "plan_rows": 0, "contract_rows": 0, "holdout": "family"}
        with mock.patch.object(autoloop.trainloop, "prepare_data",
                               return_value=prepared) as prep, \
                mock.patch.object(backend, "_train", return_value=0), \
                mock.patch.object(backend, "_ollama"):
            backend.train(1, autoloop.BASE, "", lambda line: None)
        prep.assert_called_with(by_family=True, all_languages=True, mix="all",
                                with_buildfix=False)

    def test_the_backend_can_train_on_whole_programs_only(self) -> None:
        """The mix A/B turns the other switch; nothing else moves."""
        backend = autoloop.RealBackend(mix="programs")
        prepared = {"night_rows": 0, "night_pairs": 0, "library_rows": 0,
                    "plan_rows": 0, "contract_rows": 0, "holdout": "family"}
        with mock.patch.object(autoloop.trainloop, "prepare_data",
                               return_value=prepared) as prep, \
                mock.patch.object(backend, "_train", return_value=0), \
                mock.patch.object(backend, "_ollama"):
            backend.train(1, autoloop.BASE, "", lambda line: None)
        prep.assert_called_with(by_family=True, all_languages=False,
                                mix="programs", with_buildfix=False)

    def test_the_default_cycle_trains_the_measured_dose(self) -> None:
        """40 preference steps and a rehearsal: the dose the wide pool scored."""
        self.assertEqual(autoloop.BASE.orpo_steps, 40)
        self.assertEqual(autoloop.BASE.rehearsal_steps, 15)

    def test_orpo_ends_with_a_contract_rehearsal(self) -> None:
        """Preference first, contract last: the lanes must not pay for pairs."""
        backend = autoloop.RealBackend()
        calls: list[list[str]] = []
        notes: list[str] = []
        with mock.patch.object(autoloop.trainloop, "rehearsal_sheet",
                               return_value=Path("/tmp/rehearsal.jsonl")), \
                mock.patch.object(backend, "_pairs_file",
                                  return_value=Path("/tmp/pairs.jsonl")), \
                mock.patch.object(backend, "_train",
                                  side_effect=lambda argv, log: calls.append(argv) or 0), \
                mock.patch.object(backend, "_ollama"), \
                mock.patch.object(backend, "_note", side_effect=notes.append):
            adapter = backend.orpo(1, autoloop.BASE, "clean1/adapter",
                                   lambda line: None)
        self.assertEqual(len(calls), 2)
        self.assertIn("orpo", calls[0])
        self.assertIn("sft", calls[1])
        self.assertEqual(calls[1][calls[1].index("--train") + 1],
                         "/tmp/rehearsal.jsonl")
        self.assertEqual(calls[1][calls[1].index("--max-steps") + 1],
                         str(autoloop.BASE.rehearsal_steps))
        self.assertTrue(calls[1][calls[1].index("--init-adapter") + 1].endswith("auto1/adapter"))
        self.assertTrue(calls[1][calls[1].index("--out") + 1].endswith("auto1/rehearsal"))
        self.assertTrue(adapter.endswith("rehearsal/adapter"))
        self.assertTrue(any("contract rehearsal" in note for note in notes))

    def test_the_rehearsal_can_be_turned_off(self) -> None:
        """0 steps is the switch the mixture A/B measures against."""
        backend = autoloop.RealBackend()
        calls: list[list[str]] = []
        with mock.patch.object(backend, "_pairs_file",
                               return_value=Path("/tmp/pairs.jsonl")), \
                mock.patch.object(backend, "_train",
                                  side_effect=lambda argv, log: calls.append(argv) or 0), \
                mock.patch.object(backend, "_ollama"):
            adapter = backend.orpo(1, autoloop.Levers(rehearsal_steps=0),
                                   "clean1/adapter", lambda line: None)
        self.assertEqual(len(calls), 1)
        self.assertTrue(adapter.endswith("auto1/adapter"))

    def test_the_backend_can_train_with_the_build_fix_rows(self) -> None:
        """The build-fix A/B turns its switch; the hold-out is unchanged."""
        backend = autoloop.RealBackend(with_buildfix=True)
        prepared = {"night_rows": 0, "night_pairs": 0, "library_rows": 0,
                    "plan_rows": 0, "contract_rows": 0, "holdout": "family",
                    "buildfix_rows": 12, "buildfix_pairs": 12}
        with mock.patch.object(autoloop.trainloop, "prepare_data",
                               return_value=prepared) as prep, \
                mock.patch.object(backend, "_train", return_value=0), \
                mock.patch.object(backend, "_ollama"):
            backend.train(1, autoloop.BASE, "", lambda line: None)
        prep.assert_called_with(by_family=True, all_languages=False,
                                mix="all", with_buildfix=True)

    def test_a_frozen_pool_is_resolved_outside_the_lane_cut(self) -> None:
        """The champion's 70 sets and a candidate's 51 were not one measurement."""
        called: list[str] = []

        def pool_candidates():
            called.append("pool")
            return []

        with mock.patch.object(autoloop.functionprobe, "pool_candidates",
                               side_effect=pool_candidates), \
                mock.patch.object(autoloop, "read_state",
                                  return_value={"pools": {"family": [],
                                                          "task": []},
                                                "pools_version": autoloop.POOLS_VERSION}), \
                mock.patch.object(autoloop, "save_state"), \
                mock.patch.object(autoloop, "publish"):
            autoloop.run(cycles=1, hours=0, backend=autoloop.FakeBackend())
        self.assertEqual(called, ["pool"])

    def test_compounding_is_the_base_not_a_ladder_rung(self) -> None:
        self.assertTrue(autoloop.BASE.continue_from_best)
        fields = [field for field, _value, _note in autoloop.LADDER]
        self.assertNotIn("continue_from_best", fields)

    def test_the_base_update_is_smaller_than_the_one_that_lost_the_lane(self) -> None:
        self.assertEqual(autoloop.BASE.sft_steps, 60)
        self.assertLessEqual(autoloop.TRAIN_LR, 1e-4)


class EscalateTests(unittest.TestCase):
    def test_the_ladder_is_walked_once_in_order(self) -> None:
        levers, note, key = autoloop.escalate(autoloop.BASE, [])
        self.assertEqual(levers.samples, 4)
        self.assertEqual(key, "samples=4")
        self.assertTrue(note)

        nxt, note, key = autoloop.escalate(levers, ["samples=4"])
        self.assertEqual(nxt.night_hours, 1.6)
        self.assertEqual(key, "night_hours=1.6")

    def test_no_rung_buys_more_pairs_per_family(self) -> None:
        """A pair teaches its own family; the primary metric holds families out."""
        fields = [field for field, _value, _note in autoloop.LADDER]
        self.assertNotIn("per_family", fields)
        self.assertNotIn("orpo_steps", fields)

    def test_a_spent_ladder_says_so(self) -> None:
        tried = [f"{field}={value}" for field, value, _ in autoloop.LADDER]
        levers, note, key = autoloop.escalate(autoloop.BASE, tried)
        self.assertEqual(note, "")
        self.assertEqual(key, "")
        self.assertEqual(levers, autoloop.BASE)


class RunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self.restore)
        autoloop.stop_path().unlink(missing_ok=True)

    def restore(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev

    def test_a_changed_scoring_rule_measures_the_champion_again(self) -> None:
        """A one-draw champion cannot be paired against a two-draw candidate."""
        autoloop.save_state({
            "pools": {"family": [], "task": []},
            "pools_version": autoloop.POOLS_VERSION,
            "gate_version": autoloop.GATE_VERSION,
            "eval_version": autoloop.EVAL_VERSION - 1,
            "best": "data/models/auto1/adapter",
            "best_metrics": {"family": {"match": 3, "attempts": 4},
                             "task": {"match": 1, "attempts": 2},
                             "gate": {"passed": 7, "total": 10}}})
        backend = autoloop.FakeBackend()
        autoloop.run(cycles=1, hours=0, backend=backend)
        # One re-measure of the champion before the cycle, then the cycle's own.
        self.assertEqual(backend.calls.count("evaluate"), 2)
        state = autoloop.read_state()
        self.assertEqual(state["eval_version"], autoloop.EVAL_VERSION)

    def test_a_set_matched_once_is_kept_as_a_count(self) -> None:
        first = [{"task_id": "held/a", "match": True, "compile": True},
                 {"task_id": "held/b", "match": False, "compile": True}]
        second = [{"task_id": "held/a", "match": False, "compile": False},
                  {"task_id": "held/b", "match": False, "skipped": "no function"}]
        rows, stats = autoloop.merge_draws([first, second])
        by_id = {row["task_id"]: row for row in rows}
        self.assertEqual(by_id["held/a"]["matches"], 1)
        self.assertTrue(by_id["held/a"]["match"])
        self.assertEqual(by_id["held/a"]["draws"], 2)
        # A set the toolchain could not judge was not a failed attempt.
        self.assertEqual(by_id["held/b"]["draws"], 1)
        self.assertEqual(stats, {"match": 1, "attempts": 2})

    def test_a_changed_split_rebuilds_the_frozen_pools(self) -> None:
        """The freeze kept scoring 56 old sets after the split moved on."""
        state = {"pools": {"family": ["old/set"], "task": []},
                 "pools_version": autoloop.POOLS_VERSION - 1,
                 "best_metrics": {"family": {"match": 18, "attempts": 52}},
                 "best": "data/models/auto1/adapter"}
        pools = autoloop._pools(state)
        self.assertNotIn("old/set", pools["family"])
        self.assertEqual(state["pools_version"], autoloop.POOLS_VERSION)
        # The champion's numbers belong to the old pool; they are not comparable.
        self.assertIsNone(state["best_metrics"])
        self.assertEqual(state["best"], "")

    def test_a_matching_version_keeps_the_frozen_pools(self) -> None:
        state = {"pools": {"family": ["kept/set"], "task": []},
                 "pools_version": autoloop.POOLS_VERSION}
        self.assertEqual(autoloop._pools(state)["family"], ["kept/set"])

    def test_the_first_cycle_takes_the_champion_and_a_second_must_earn_it(self) -> None:
        result = autoloop.run(cycles=2, hours=0, backend=autoloop.FakeBackend())
        self.assertEqual(result["state"], "done")
        rows = autoloop.history()
        self.assertEqual(rows[0]["cycle"], 0)  # the untouched model, measured once
        self.assertIn("baseline", rows[0])
        cycles = [row for row in rows if "accepted" in row]
        self.assertEqual(len(cycles), 2)
        self.assertTrue(cycles[0]["accepted"])
        self.assertTrue(cycles[1]["accepted"])  # fake improves by one family task
        self.assertEqual(result["best"], "fake/auto2/orpo")

    def test_a_plateau_escalates_a_lever_instead_of_repeating_itself(self) -> None:
        class Flat(autoloop.FakeBackend):
            def __init__(self) -> None:
                super().__init__(improve=False)
                self.cycle = 0

            def evaluate(self, adapter, log):
                self.calls.append("evaluate")
                if not adapter:  # the untouched model, measured once
                    return {"family": autoloop.metrics(14, 48),
                            "task": autoloop.metrics(9, 24)}
                return {"family": autoloop.metrics(16, 48),
                        "task": autoloop.metrics(9, 24)}

        result = autoloop.run(cycles=2, hours=0, backend=Flat(),
                              levers=autoloop.BASE)
        self.assertEqual(result["state"], "done")
        rows = [row for row in autoloop.history() if "accepted" in row]
        self.assertTrue(rows[0]["accepted"])
        self.assertFalse(rows[1]["accepted"])
        self.assertEqual(result["best"], "fake/auto1/orpo")
        # The rejected cycle is followed by the next rung, not the same cycle.
        state = json.loads(autoloop.state_path().read_text())
        self.assertEqual(state["levers"]["samples"], 4)
        self.assertEqual(state["tried"], ["samples=4"])

    def test_a_spent_ladder_ends_the_run_and_says_why(self) -> None:
        class Flat(autoloop.FakeBackend):
            def evaluate(self, adapter, log):
                return {"family": autoloop.metrics(14 if not adapter else 16, 48),
                        "task": autoloop.metrics(9, 24)}

        autoloop.run(cycles=1, hours=0, backend=Flat())
        for field, value, _ in autoloop.LADDER:
            autoloop.run(cycles=1, hours=0, backend=Flat())
        result = autoloop.run(cycles=1, hours=0, backend=Flat())
        self.assertEqual(result["state"], "done")
        self.assertIn(result.get("stage"), ("ladder-spent", "cycles-exhausted"))

    def test_a_cycle_records_what_each_stage_cost(self) -> None:
        """A round's price is per stage: the gate got dearer when it repeated."""
        autoloop.run(cycles=1, hours=0, backend=autoloop.FakeBackend())
        entry = [r for r in autoloop.history() if "accepted" in r][-1]
        took = entry["took"]
        self.assertEqual(list(took), ["night", "mine", "sft", "orpo",
                                      "evaluate", "gate", "total"])
        self.assertEqual(took["total"], sum(took[k] for k in took if k != "total"))
        status = json.loads(autoloop.status_path().read_text())
        self.assertIn("took", status)

    def test_the_journal_status_and_report_are_written(self) -> None:
        autoloop.run(cycles=1, hours=0, backend=autoloop.FakeBackend())
        self.assertTrue(autoloop.state_path().exists())
        self.assertTrue(autoloop.stop_path().parent.exists())
        report = (autoloop.loop_dir() / autoloop.REPORT_FILE).read_text()
        self.assertIn("| cycle |", report)
        self.assertIn("kept", report)
        status = json.loads(autoloop.status_path().read_text())
        self.assertIn(status["state"], ("done", "stopped"))

    def test_a_restart_resumes_the_cycle_number(self) -> None:
        autoloop.run(cycles=1, hours=0, backend=autoloop.FakeBackend())
        state = json.loads(autoloop.state_path().read_text())
        self.assertEqual(state["cycle"], 1)
        autoloop.run(cycles=1, hours=0, backend=autoloop.FakeBackend())
        self.assertEqual(json.loads(autoloop.state_path().read_text())["cycle"], 2)

    def test_the_stop_file_ends_the_next_cycle(self) -> None:
        autoloop.run(cycles=1, hours=0, backend=autoloop.FakeBackend())
        autoloop.request_stop()
        result = autoloop.run(cycles=3, hours=0, backend=autoloop.FakeBackend())
        self.assertEqual(result["state"], "stopped")
        # The baseline row plus the one finished cycle; nothing after the stop.
        self.assertEqual(len([r for r in autoloop.history() if "accepted" in r]), 1)

    def test_pairs_from_held_out_families_never_enter_training(self) -> None:
        night = [{"prompt": "p1", "chosen": "a\n", "rejected": "b\n", "task_id": "k/a"},
                 {"prompt": "p2", "chosen": "a\n", "rejected": "b\n", "task_id": "k/b"}]
        mined = [{"prompt": "p3", "chosen": "a\n", "rejected": "c\n", "task_id": "k/c"}]
        merged = autoloop.merge_pairs(night, mined, {"k/b"})
        self.assertEqual([row["task_id"] for row in merged], ["k/a", "k/c"])

    def test_duplicate_pairs_are_merged_once(self) -> None:
        row = {"prompt": "p", "chosen": "a\n", "rejected": "b\n", "task_id": "k/a"}
        merged = autoloop.merge_pairs([row], [dict(row)], set())
        self.assertEqual(len(merged), 1)


    def test_a_restart_resumes_the_levers_it_reached(self) -> None:
        """Resuming the cycle number on base levers undoes an escalation."""
        levers = autoloop._stored_levers({"levers": {"samples": 4,
                                                     "night_hours": 1.6,
                                                     "gone": 99}})
        self.assertEqual((levers.samples, levers.night_hours), (4, 1.6))
        self.assertEqual(autoloop._stored_levers({}), autoloop.BASE)
        self.assertEqual(autoloop._stored_levers({"levers": {"gone": 1}}),
                         autoloop.BASE)


class GateRuleTests(unittest.TestCase):
    """A stored gate is only comparable to a gate measured the same way."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self.restore)
        autoloop.stop_path().unlink(missing_ok=True)

    def restore(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev

    def test_a_changed_gate_rule_remeasures_the_champion_first(self) -> None:
        class Measured(autoloop.FakeBackend):
            def __init__(self) -> None:
                super().__init__()
                self.measured: list[str] = []

            def gate(self, adapter, log):
                self.measured.append(adapter)
                return super().gate(adapter, log)

        autoloop.run(cycles=1, hours=0, backend=Measured())
        state = json.loads(autoloop.state_path().read_text())
        self.assertEqual(state["gate_version"], autoloop.GATE_VERSION)
        champion = state["best"]
        self.assertTrue(champion)

        state["gate_version"] = autoloop.GATE_VERSION - 1
        autoloop.state_path().write_text(json.dumps(state), encoding="utf-8")
        again = Measured()
        autoloop.run(cycles=1, hours=0, backend=again)
        self.assertEqual(again.measured[0], champion)  # the bar, under the new rule
        self.assertEqual(len(again.measured), 2)       # then the candidate's own gate

    def test_a_current_gate_rule_does_not_pay_for_a_remeasure(self) -> None:
        class Measured(autoloop.FakeBackend):
            def __init__(self) -> None:
                super().__init__()
                self.measured: list[str] = []

            def gate(self, adapter, log):
                self.measured.append(adapter)
                return super().gate(adapter, log)

        autoloop.run(cycles=1, hours=0, backend=Measured())
        champion = json.loads(autoloop.state_path().read_text())["best"]
        again = Measured()
        autoloop.run(cycles=1, hours=0, backend=again)
        self.assertEqual(len(again.measured), 1)  # the candidate only
        self.assertNotIn(champion, again.measured)


if __name__ == "__main__":
    unittest.main()
