"""The orchestra: four seats in order, a bounded QA loop, and the toolchain last."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import orchestra


BLUEPRINT = json.dumps({
    "tree": "main.py\nutil.py",
    "files": [{"path": "main.py", "purpose": "entry"},
              {"path": "util.py", "purpose": "helper"}],
    "entry": "main.py",
    "dependencies": {"main.py": ["util"]},
})
TWO_FILES = (
    "FILE: main.py\n```python\nfrom util import answer\n\nprint(answer())\n```\n\n"
    "FILE: util.py\n```python\ndef answer():\n    return 42\n```\n")
FIXED_MAIN = "FILE: main.py\n```python\nfrom util import answer\n\nprint(answer())\n```\n"
BROKEN = "FILE: main.py\n```python\nprint(\n```\n"
QA_PASS = json.dumps({"status": "PASSED", "errors": [], "scope": "code", "files": []})
QA_FAIL = json.dumps({"status": "FAILED", "errors": ["prints the wrong number"],
                      "scope": "code", "files": ["main.py"]})
QA_DESIGN = json.dumps({"status": "FAILED", "errors": ["the split is wrong"],
                        "scope": "design", "files": ["main.py"]})


class Scripted:
    """A chat that answers as whichever seat is asking, from a script."""

    model = "scripted-14b"
    url = "http://example/v1"

    def __init__(self, architect=None, lead=None, developer=None, qa=None):
        self.scripts = {
            "architect": list(architect or [BLUEPRINT]),
            "tech lead": list(lead or ["step 1: print the answer"]),
            "developer": list(developer or [TWO_FILES]),
            "qa": list(qa or [QA_PASS]),
        }
        self.calls: list[dict] = []

    def seat(self, system: str) -> str:
        # Each persona names the others too, so match the opening line.
        for name in ("architect", "tech lead", "developer"):
            if f"You are the {name}" in system:
                return name
        return "qa"

    def ask(self, system: str, user: str, json_object: bool = False,
            temperature: float | None = None) -> dict:
        seat = self.seat(system)
        self.calls.append({"seat": seat, "system": system, "user": user,
                           "json": json_object, "temperature": temperature})
        reply = self.scripts[seat].pop(0) if len(self.scripts[seat]) > 1 \
            else self.scripts[seat][0]
        return {"content": reply, "reasoning": "", "model": self.model,
                "usage": {}, "seconds": 0.0}

    def seats(self) -> list[str]:
        return [call["seat"] for call in self.calls]

    def prompt(self, index: int) -> str:
        return self.calls[index]["user"]


class RunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "runs"

    def test_the_seats_run_in_order_and_the_toolchain_has_the_last_word(self) -> None:
        chat = Scripted()
        result = orchestra.run("print the answer", "python", chat, out_root=self.out)
        self.assertTrue(result["passed"])
        self.assertEqual(chat.seats(), ["architect", "tech lead", "developer", "qa"])
        self.assertEqual(result["attempts"], 1)
        target = Path(result["path"])
        self.assertEqual((target / "files" / "main.py").read_text(),
                         "from util import answer\n\nprint(answer())\n")
        self.assertEqual((target / "files" / "util.py").read_text(),
                         "def answer():\n    return 42\n")
        for name in ("blueprint.json", "reasoning.md", "qa.jsonl", "build.txt",
                     "state.json", "notes.txt"):
            self.assertTrue((target / name).is_file(), name)
        self.assertIn("ok: True", (target / "build.txt").read_text())

    def test_the_reviewer_is_shown_the_blueprint_it_checks_against(self) -> None:
        # QA without the manifest invents requirements the other seats were
        # never given, and fails a build for doing what the blueprint said.
        chat = Scripted()
        orchestra.run("print the answer", "python", chat, out_root=self.out)
        review = chat.calls[3]["user"]
        self.assertIn("main.py — entry", review)
        self.assertIn("util.py — helper", review)
        self.assertIn("not a defect", review)

    def test_the_architect_and_the_reviewer_are_asked_for_json(self) -> None:
        chat = Scripted()
        orchestra.run("print the answer", "python", chat, out_root=self.out)
        self.assertTrue(chat.calls[0]["json"])
        self.assertTrue(chat.calls[3]["json"])
        self.assertFalse(chat.calls[2]["json"])

    def test_a_failed_review_sends_only_the_file_it_blamed(self) -> None:
        chat = Scripted(developer=[TWO_FILES, FIXED_MAIN], qa=[QA_FAIL, QA_PASS])
        result = orchestra.run("print the answer", "python", chat, out_root=self.out)
        self.assertTrue(result["passed"])
        self.assertEqual(result["attempts"], 2)
        repair = chat.prompt(4)  # architect, lead, code, qa, repair
        self.assertIn("prints the wrong number", repair)
        self.assertIn("FILE: main.py", repair)
        self.assertNotIn("util.py", repair)

    def test_three_failed_passes_stop_the_loop(self) -> None:
        chat = Scripted(qa=[QA_FAIL])
        result = orchestra.run("print the answer", "python", chat, out_root=self.out)
        self.assertFalse(result["passed"])
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(chat.seats().count("developer"), 3)
        self.assertEqual(chat.seats().count("qa"), 3)
        self.assertEqual(len(result["state"]["history"]), 3)

    def test_a_design_failure_goes_back_to_the_tech_lead(self) -> None:
        chat = Scripted(qa=[QA_DESIGN, QA_PASS])
        result = orchestra.run("print the answer", "python", chat, out_root=self.out)
        self.assertTrue(result["passed"])
        self.assertEqual(chat.seats().count("tech lead"), 2)
        second_lead = [c for c in chat.calls if c["seat"] == "tech lead"][1]
        self.assertIn("A first design was rejected", second_lead["user"])
        self.assertIn("the split is wrong", second_lead["user"])

    def test_the_toolchain_overrules_a_review_that_passed(self) -> None:
        # QA says PASSED, but `print(` does not compile: the gate is the compiler.
        chat = Scripted(developer=[BROKEN], qa=[json.dumps(
            {"status": "PASSED", "errors": [], "scope": "code", "files": []})])
        result = orchestra.run("print the answer", "python", chat, out_root=self.out,
                               max_attempts=2)
        self.assertFalse(result["passed"])
        self.assertEqual(result["attempts"], 2)
        self.assertTrue(any("toolchain" in e for e in result["errors"]))
        saved = json.loads((Path(result["path"]) / "state.json").read_text())
        self.assertFalse(saved["build"]["ok"])

    def test_a_requested_file_goes_back_to_the_architect(self) -> None:
        ask = "REQUEST_FILE: util.py — the helper\n"
        second = json.dumps({"tree": "main.py\nutil.py",
                             "files": [{"path": "main.py", "purpose": "entry"},
                                       {"path": "util.py", "purpose": "helper"}],
                             "entry": "main.py", "dependencies": {}})
        chat = Scripted(architect=[BLUEPRINT, second], developer=[ask, TWO_FILES])
        result = orchestra.run("print the answer", "python", chat, out_root=self.out)
        self.assertTrue(result["passed"])
        self.assertEqual(chat.seats().count("architect"), 2)
        revision = chat.calls[3]["user"]  # the architect, asked to revise
        self.assertIn("The developer needs these files as well", revision)
        self.assertIn("util.py", revision)
        self.assertEqual(result["attempts"], 2)

    def test_a_blueprint_with_no_files_is_an_error_not_a_crash(self) -> None:
        chat = Scripted(architect=["{}"])
        result = orchestra.run("print the answer", "python", chat, out_root=self.out)
        self.assertFalse(result["passed"])
        self.assertEqual(result["attempts"], 0)
        self.assertIn("architect", result["errors"][0])

    def test_the_copy_keeps_every_attempt_that_was_written(self) -> None:
        chat = Scripted(developer=[BROKEN, TWO_FILES], qa=[QA_FAIL, QA_PASS])
        result = orchestra.run("print the answer", "python", chat, out_root=self.out)
        target = Path(result["path"])
        self.assertTrue((target / "attempt-1" / "files" / "main.py").is_file())
        self.assertTrue((target / "attempt-2" / "files" / "main.py").is_file())
        self.assertIn("print(", (target / "attempt-1" / "files" / "main.py").read_text())
        verdicts = (target / "qa.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(verdicts), 2)
        self.assertEqual(json.loads(verdicts[0])["status"], "FAILED")


QA_FAIL_UTIL = json.dumps({"status": "FAILED", "errors": ["answer() returns 41"],
                          "scope": "code", "files": ["util.py"]})
FIXED_UTIL = "FILE: util.py\n```python\ndef answer():\n    return 42\n```\n"


class RepairLoopTests(unittest.TestCase):
    """Three passes over a two-file project: the bugs, and what the coder sees."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "runs"

    def test_each_repair_sees_only_the_file_that_failed(self) -> None:
        chat = Scripted(developer=[TWO_FILES, FIXED_MAIN, FIXED_UTIL],
                        qa=[QA_FAIL, QA_FAIL_UTIL, QA_PASS])
        result = orchestra.run("print the answer", "python", chat,
                               out_root=self.out, max_attempts=3)
        self.assertTrue(result["passed"])
        self.assertEqual(result["attempts"], 3)
        developers = [c["user"] for c in chat.calls if c["seat"] == "developer"]
        self.assertEqual(len(developers), 3)
        for prompt in developers[1:]:
            self.assertIn("Only these files are yours to change", prompt)
        self.assertIn("FILE: main.py", developers[1])
        self.assertNotIn("util.py", developers[1])     # the healthy sibling
        self.assertIn("FILE: util.py", developers[2])
        self.assertNotIn("main.py", developers[2])

    def test_each_pass_is_handed_to_a_watcher_as_it_lands(self) -> None:
        # A copy on disk shows the tracker only at the end; a failing run has to
        # be legible while it is still failing.
        seen: list[dict] = []
        chat = Scripted(developer=[TWO_FILES, FIXED_MAIN], qa=[QA_FAIL, QA_PASS])
        orchestra.run("print the answer", "python", chat, out_root=self.out,
                      max_attempts=2, on_pass=seen.append)
        self.assertEqual([record["pass"] for record in seen], [1, 2])
        self.assertFalse(seen[0]["passed"])
        self.assertEqual(seen[0]["failing"], ["main.py"])
        self.assertEqual([bug["path"] for bug in seen[0]["bugs"]], ["main.py"])
        self.assertTrue(seen[1]["passed"])
        self.assertEqual(seen[1]["bugs"], [])

    def test_a_review_cannot_veto_a_build_the_gate_verified(self) -> None:
        # The expectation is met, the compiler is happy, and QA still says no —
        # on requirements the brief never made. Advice, not a veto.
        code = "FILE: cli.py\n```python\nprint(5)\n```\n"
        picky = json.dumps({"status": "FAILED",
                            "errors": ["should also handle an empty file"],
                            "scope": "code", "files": ["cli.py"]})
        chat = Scripted(architect=[CLI_BLUEPRINT], developer=[code], qa=[picky])
        result = orchestra.run("a program that prints the sum of 2 and 3", "python",
                               chat, out_root=self.out, max_attempts=2)
        self.assertTrue(result["passed"])
        self.assertEqual(result["attempts"], 1)      # no wasted repair pass
        self.assertEqual(result["errors"], [])
        verdict = json.loads((Path(result["path"]) / "qa.jsonl").read_text()
                             .splitlines()[0])
        self.assertTrue(verdict["advisory"])
        self.assertEqual(result["state"]["build"]["matches"], True)

    def test_a_review_still_vetoes_when_the_output_was_never_compared(self) -> None:
        # No expectation to meet, so the review is the only check there is.
        chat = Scripted(developer=[TWO_FILES, FIXED_MAIN], qa=[QA_FAIL, QA_PASS])
        result = orchestra.run("print the answer", "python", chat,
                               out_root=self.out, max_attempts=2)
        self.assertEqual(result["attempts"], 2)

    def test_a_watcher_that_raises_does_not_fail_the_build(self) -> None:
        def broken(record: dict) -> None:
            raise RuntimeError("the panel went away")
        chat = Scripted()
        result = orchestra.run("print the answer", "python", chat,
                               out_root=self.out, on_pass=broken)
        self.assertTrue(result["passed"])

    def test_the_bug_tracker_accumulates_one_entry_per_failed_pass(self) -> None:
        chat = Scripted(developer=[TWO_FILES, FIXED_MAIN, FIXED_UTIL],
                        qa=[QA_FAIL, QA_FAIL_UTIL, QA_PASS])
        result = orchestra.run("print the answer", "python", chat,
                               out_root=self.out, max_attempts=3)
        bugs = [json.loads(line) for line in
                (Path(result["path"]) / "bugs.jsonl").read_text().splitlines()]
        self.assertEqual([b["path"] for b in bugs], ["main.py", "util.py"])
        self.assertEqual([b["attempt"] for b in bugs], [1, 2])
        self.assertEqual([b["resolved"] for b in bugs], [True, True])
        self.assertEqual(len(result["state"]["history"]), 3)
        self.assertEqual(result["state"]["board"].loop_count, 3)
        for attempt in (1, 2, 3):
            self.assertTrue((Path(result["path"]) / f"attempt-{attempt}"
                             / "files" / "main.py").is_file())

    def test_a_toolchain_error_is_attributed_to_the_file_it_names(self) -> None:
        # With no path on the bug, `failing()` is empty and the repair view
        # falls back to the whole project — the compiler knows better.
        chat = Scripted(developer=[TWO_FILES, FIXED_MAIN])
        broken = orchestra.execution.RunResult(
            ok=False, language="python", command="python3 main.py", exit_code=1,
            error="main.py:3: SyntaxError: invalid syntax")
        real = orchestra.execution.run_files
        seen = {"n": 0}

        def flaky(files, language, **kwargs):
            seen["n"] += 1
            if seen["n"] == 1:
                return broken
            return real(files, language, **kwargs)

        with mock.patch.object(orchestra.execution, "run_files", side_effect=flaky):
            result = orchestra.run("print the answer", "python", chat,
                                   out_root=self.out, max_attempts=2)
        bugs = [json.loads(line) for line in
                (Path(result["path"]) / "bugs.jsonl").read_text().splitlines()]
        self.assertEqual(bugs[0]["path"], "main.py")
        developers = [c["user"] for c in chat.calls if c["seat"] == "developer"]
        self.assertNotIn("util.py", developers[1])

    def test_a_repeated_toolchain_failure_is_not_closed_by_a_silent_review(self) -> None:
        # QA passing with no files named, while the compiler repeats the same
        # complaint, must not resolve the bug the last pass already recorded.
        chat = Scripted(developer=[TWO_FILES])
        broken = orchestra.execution.RunResult(
            ok=False, language="python", command="python3 main.py", exit_code=1,
            error="main.py:1: the compiler rejected the file")
        with mock.patch.object(orchestra.execution, "run_files",
                               side_effect=lambda *a, **k: broken):
            result = orchestra.run("print the answer", "python", chat,
                                   out_root=self.out, max_attempts=2)
        bugs = [json.loads(line) for line in
                (Path(result["path"]) / "bugs.jsonl").read_text().splitlines()]
        self.assertEqual([bug["path"] for bug in bugs], ["main.py", "main.py"])
        self.assertTrue(all(not bug["resolved"] for bug in bugs))
        self.assertEqual(result["state"]["board"].failing(), ["main.py"])

    def test_the_loop_stops_at_the_cap_and_leaves_the_bugs_open(self) -> None:
        chat = Scripted(developer=[TWO_FILES], qa=[QA_FAIL_UTIL])
        result = orchestra.run("print the answer", "python", chat,
                               out_root=self.out, max_attempts=3)
        self.assertFalse(result["passed"])
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(chat.seats().count("developer"), 3)
        self.assertEqual(chat.seats().count("qa"), 3)
        bugs = [json.loads(line) for line in
                (Path(result["path"]) / "bugs.jsonl").read_text().splitlines()]
        self.assertEqual([b["attempt"] for b in bugs], [1, 2, 3])
        self.assertTrue(all(not b["resolved"] for b in bugs))


class SeatTests(unittest.TestCase):
    """A band is more than one player: each seat can be a different model."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "runs"

    def player(self, model: str, **kwargs) -> Scripted:
        chat = Scripted(**kwargs)
        chat.model = model
        return chat

    def test_each_seat_can_be_its_own_player(self) -> None:
        architect = self.player("arch-14b")
        lead = self.player("lead-14b")
        developer = self.player("dev-14b")
        qa = self.player("qa-14b")
        result = orchestra.run(
            "print the answer", "python", architect, out_root=self.out,
            chats={"architect": architect, "tech_lead": lead,
                   "developer": developer, "qa": qa})
        self.assertTrue(result["passed"])
        self.assertEqual(architect.seats(), ["architect"])
        self.assertEqual(lead.seats(), ["tech lead"])
        self.assertEqual(developer.seats(), ["developer"])
        self.assertEqual(qa.seats(), ["qa"])
        self.assertEqual(result["state"]["seats"], {
            "architect": "arch-14b", "tech_lead": "lead-14b",
            "developer": "dev-14b", "qa": "qa-14b"})

    def test_the_repair_pass_returns_to_the_developers_own_player(self) -> None:
        developer = self.player("dev-14b", developer=[TWO_FILES, FIXED_MAIN],
                                qa=[QA_FAIL, QA_PASS])
        qa = self.player("qa-14b", qa=[QA_FAIL, QA_PASS])
        result = orchestra.run("print the answer", "python", developer,
                               out_root=self.out,
                               chats={"developer": developer, "qa": qa})
        self.assertTrue(result["passed"])
        self.assertEqual(developer.seats().count("developer"), 2)
        self.assertEqual(qa.seats(), ["qa", "qa"])

    def test_a_seat_that_does_not_exist_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            orchestra.run("print the answer", "python", Scripted(),
                          out_root=self.out, chats={"critic": Scripted()})


class JobTests(unittest.TestCase):
    """The run as a job the app starts and watches."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        orchestra.JOB.update({"state": "idle", "error": "", "log": [], "passed": False,
                              "path": "", "files": [], "errors": [], "attempts": 0,
                              "requirement": "", "model": "", "player": ""})
        self.addCleanup(self.restore)

    def restore(self) -> None:
        orchestra.JOB.update({"state": "idle", "error": "", "log": [], "passed": False})
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev

    def test_an_empty_requirement_is_refused(self) -> None:
        self.assertIn("say what to build", orchestra.start("   ")["error"])

    def test_a_second_run_is_refused_while_one_is_going(self) -> None:
        orchestra.JOB["state"] = "running"
        self.assertIn("already going", orchestra.start("print 42")["error"])

    def test_an_unknown_player_is_refused_before_a_thread_starts(self) -> None:
        with mock.patch.object(orchestra.builder, "chat_for",
                               side_effect=KeyError("no connection named 'ghost'")):
            result = orchestra.start("print 42", player="ghost")
        self.assertIn("no connection named", result["error"])
        self.assertNotEqual(orchestra.JOB["state"], "running")

    def test_a_finished_run_publishes_its_outcome(self) -> None:
        done = {"passed": True, "attempts": 2, "path": "/tmp/copy",
                "files": ["main.py"], "errors": [], "state": {}}
        with mock.patch.object(orchestra, "run", return_value=done):
            started = orchestra.start("print 42", "python", "", 2)
            # The thread may already have finished by the time start returns.
            self.assertEqual(started["requirement"], "print 42")
            self.assertTrue(started["model"])
            orchestra._THREAD.join(timeout=5)
        final = orchestra.status()
        self.assertEqual(final["state"], "done")
        self.assertTrue(final["passed"])
        self.assertEqual(final["path"], "/tmp/copy")
        self.assertEqual(final["attempts"], 2)
        self.assertTrue(orchestra.status_path().exists())

    def test_a_run_that_raises_fails_the_job_with_its_words(self) -> None:
        with mock.patch.object(orchestra, "run", side_effect=RuntimeError("player went away")):
            orchestra.start("print 42")
            orchestra._THREAD.join(timeout=5)
        final = orchestra.status()
        self.assertEqual(final["state"], "failed")
        self.assertIn("player went away", final["error"])

    def test_the_job_publishes_the_tracker_of_each_pass(self) -> None:
        def fake(requirement, language, chat, attempts, log=None, smoke="",
                 inputs=None, expect="", on_pass=None):
            on_pass({"pass": 1, "passed": False, "failing": ["main.py"],
                     "bugs": [{"path": "main.py", "error": "boom", "attempt": 1,
                               "resolved": False, "toolchain": True}], "note": ""})
            board = orchestra.AppMessageBoard("print 42")
            board.record_bug("qa", "boom", path="main.py", attempt=1,
                             toolchain=True)
            return {"passed": False, "attempts": 1, "path": "/tmp/copy",
                    "files": ["main.py"], "errors": ["boom"],
                    "state": {"board": board}}

        with mock.patch.object(orchestra, "run", side_effect=fake):
            orchestra.start("print 42")
            orchestra._THREAD.join(timeout=5)
        final = orchestra.status()
        self.assertEqual([record["pass"] for record in final["passes"]], [1])
        self.assertEqual(final["passes"][0]["failing"], ["main.py"])
        self.assertEqual(final["bugs"][0]["path"], "main.py")
        self.assertTrue(final["bugs"][0]["toolchain"])

    def test_the_last_run_survives_a_restart(self) -> None:
        orchestra._publish(state="done", passed=True, path="/tmp/copy", log=["x"])
        orchestra.JOB.update({"state": "idle", "path": ""})
        restored = orchestra.status()
        self.assertEqual(restored["state"], "done")
        self.assertEqual(restored["path"], "/tmp/copy")


CLI_BLUEPRINT = json.dumps({
    "tree": "cli.py",
    "files": [{"path": "cli.py", "purpose": "entry"}],
    "entry": "cli.py",
    "run": "python cli.py notes.txt",
    "dependencies": {},
})
CLI_CODE = ("FILE: cli.py\n```python\nimport sys\n\n"
            "if len(sys.argv) != 2:\n"
            "    print(\"Usage: cli.py <path>\", file=sys.stderr)\n"
            "    sys.exit(1)\n\n"
            "print(sys.argv[1])\n```\n")


class RunCommandTests(unittest.TestCase):
    """A CLI is judged on the invocation the architect declared, not a bare run."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "runs"

    def test_the_architects_run_command_is_what_runs_the_program(self) -> None:
        chat = Scripted(architect=[CLI_BLUEPRINT], developer=[CLI_CODE])
        result = orchestra.run("print the path it is given", "python", chat,
                               out_root=self.out)
        self.assertTrue(result["passed"])
        target = Path(result["path"])
        self.assertIn("notes.txt", (target / "build.txt").read_text())
        self.assertEqual(json.loads((target / "blueprint.json").read_text())["run"],
                         "python cli.py notes.txt")

    def test_with_no_run_command_the_program_is_still_run_bare(self) -> None:
        # The same code without a declared invocation fails, and the failure
        # says how it was run — otherwise "Usage: ..." reads like broken code.
        bare = json.dumps({**json.loads(CLI_BLUEPRINT), "run": ""})
        chat = Scripted(architect=[bare], developer=[CLI_CODE])
        result = orchestra.run("print the path it is given", "python", chat,
                               out_root=self.out, max_attempts=1)
        self.assertFalse(result["passed"])
        self.assertIn("run as:", result["errors"][-1])
        bugs = (Path(result["path"]) / "bugs.jsonl").read_text()
        self.assertIn("run as:", bugs)
        self.assertIn("cli.py", bugs)

    def test_a_declared_input_file_is_there_when_the_program_reads_it(self) -> None:
        # The program reads a file that ships with the project. The scratch
        # directory does not have it unless the blueprint says what it holds.
        counted = ("FILE: cli.py\n```python\nimport sys\n\n"
                   "with open(sys.argv[1], encoding='utf-8') as handle:\n"
                   "    print(sum(1 for _ in handle))\n```\n")
        with_input = json.dumps({**json.loads(CLI_BLUEPRINT),
                                 "inputs": {"notes.txt": "a\nb\nc\n"}})
        chat = Scripted(architect=[with_input], developer=[counted])
        result = orchestra.run("count the lines in a file", "python", chat,
                               out_root=self.out, max_attempts=1)
        self.assertTrue(result["passed"])
        target = Path(result["path"])
        self.assertEqual(json.loads((target / "blueprint.json").read_text())["inputs"],
                         {"notes.txt": "a\nb\nc\n"})
        # A fixture is not shipped: the copy holds the app, not the test data.
        self.assertFalse((target / "files" / "notes.txt").exists())
        self.assertTrue((target / "files" / "cli.py").is_file())

    def test_the_requests_smoke_command_is_what_runs(self) -> None:
        # The architect proposes `python cli.py alpha`; the caller said
        # `python cli.py notes.txt`. The caller's word is the one that runs, and
        # the architect is not even asked for one.
        chat = Scripted(architect=[CLI_BLUEPRINT], developer=[CLI_CODE])
        result = orchestra.run("print the path it is given", "python", chat,
                               out_root=self.out, max_attempts=1,
                               smoke="python cli.py notes.txt",
                               inputs={"notes.txt": "hello"},
                               expect="notes.txt")
        self.assertTrue(result["passed"])
        target = Path(result["path"])
        build = (target / "build.txt").read_text()
        self.assertIn("cli.py notes.txt", build)
        self.assertIn("matches: True", build)
        saved = json.loads((target / "blueprint.json").read_text())
        self.assertEqual(saved["run"], "python cli.py notes.txt")
        self.assertEqual(saved["run_from"], "request")
        self.assertNotIn('"run"', chat.prompt(0))

    def test_a_wrong_answer_that_exits_zero_is_caught_by_the_expected_output(self) -> None:
        # The hole fixture data opens: the program ignores its input and prints a
        # constant, so it exits 0 and every earlier gate passes. Only the
        # expected output catches it — and it must be the caller's, not one the
        # model wrote to match its own bug.
        liar = ("FILE: cli.py\n```python\nimport sys\n\n"
                "# ignores sys.argv[1] entirely\nprint(3)\n```\n")
        chat = Scripted(architect=[CLI_BLUEPRINT], developer=[liar])
        result = orchestra.run("count the lines in a file", "python", chat,
                               out_root=self.out, max_attempts=1,
                               smoke="python cli.py notes.txt",
                               inputs={"notes.txt": "a\nb\n"}, expect="2")
        self.assertFalse(result["passed"])
        self.assertIn("a correct run prints", result["errors"][-1])
        self.assertIn("printed '3'", result["errors"][-1])
        saved = json.loads((Path(result["path"]) / "bugs.jsonl").read_text().splitlines()[0])
        self.assertTrue(saved["toolchain"])

    def test_the_architect_may_declare_what_a_correct_run_prints(self) -> None:
        wanting = json.dumps({**json.loads(CLI_BLUEPRINT), "expected_stdout": "notes.txt"})
        chat = Scripted(architect=[wanting], developer=[CLI_CODE])
        result = orchestra.run("print the path it is given", "python", chat,
                               out_root=self.out, max_attempts=1)
        self.assertTrue(result["passed"])
        saved = json.loads((Path(result["path"]) / "blueprint.json").read_text())
        self.assertEqual(saved["stdout_from"], "architect")

    def test_the_seats_that_write_the_code_are_told_what_the_gate_expects(self) -> None:
        # A gate nobody was told about punishes punctuation instead of testing
        # the job, so the contract is in the prompt that writes the code.
        chat = Scripted(architect=[CLI_BLUEPRINT], developer=[CLI_CODE])
        orchestra.run("print the path it is given", "python", chat,
                      out_root=self.out, max_attempts=1,
                      smoke="python cli.py notes.txt",
                      inputs={"notes.txt": "x"}, expect="notes.txt")
        prompts = {call["seat"]: call["user"] for call in chat.calls}
        for seat in ("tech lead", "developer", "qa"):
            self.assertIn("a correct run prints exactly: 'notes.txt'", prompts[seat])
            self.assertIn("python cli.py notes.txt", prompts[seat])

    def test_a_requirement_that_reads_nothing_is_not_offered_an_input(self) -> None:
        # The field was an invitation: asked for `inputs` on "print the sum of
        # 2 and 3", a chatty model designed a file-reading CLI and failed the
        # requirement it was given.
        self.assertFalse(orchestra.needs_input("a program that prints the sum of 2 and 3"))
        self.assertTrue(orchestra.needs_input("a CLI that counts the lines in a file"))
        self.assertTrue(orchestra.needs_input("reads a path from stdin"))
        self.assertFalse(orchestra.needs_input("prints the first 12 primes"))

    def test_the_architect_is_not_asked_for_an_invocation_it_does_not_need(self) -> None:
        chat = Scripted()
        orchestra.run("print the answer", "python", chat, out_root=self.out)
        self.assertNotIn('"run"', chat.prompt(0))
        self.assertNotIn('"inputs"', chat.prompt(0))
        self.assertIn("takes no arguments and reads no files", chat.prompt(0))

    def test_a_requirement_that_reads_a_file_is_asked_for_its_invocation(self) -> None:
        chat = Scripted()
        orchestra.run("count the lines in a file given as an argument", "python",
                      chat, out_root=self.out)
        self.assertIn('"run"', chat.prompt(0))
        self.assertIn('"inputs"', chat.prompt(0))

    def test_an_input_flag_that_is_not_path_equals_content_is_refused(self) -> None:
        self.assertEqual(orchestra.parse_inputs(["notes.txt=a\nb"]),
                         {"notes.txt": "a\nb"})
        with self.assertRaises(ValueError):
            orchestra.parse_inputs(["notes.txt"])

    def test_a_run_command_naming_another_file_is_not_taken_as_arguments(self) -> None:
        # `args_from_run` only takes what follows the entry: anything else is
        # a command for a different file and would be a guess.
        self.assertEqual(orchestra.builder.args_from_run("python other.py -x", "cli.py"),
                         [])
        self.assertEqual(orchestra.builder.args_from_run("python cli.py -x 1", "cli.py"),
                         ["-x", "1"])


class DerivationTests(unittest.TestCase):
    """No pass rests on an exit code alone when the requirement states the answer."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "runs"

    def test_the_answer_in_the_requirement_is_the_expectation(self) -> None:
        # The architect declares nothing and the caller says nothing; the
        # sentence does, so the gate compares against it.
        blueprint = json.dumps({**json.loads(CLI_BLUEPRINT), "run": "", "inputs": {}})
        code = "FILE: cli.py\n```python\nprint(4)\n```\n"
        chat = Scripted(architect=[blueprint], developer=[code])
        result = orchestra.run("a program that prints the sum of 2 and 3", "python",
                               chat, out_root=self.out, max_attempts=1)
        self.assertFalse(result["passed"])
        self.assertIn("a correct run prints '5'", result["errors"][-1])
        saved = json.loads((Path(result["path"]) / "blueprint.json").read_text())
        self.assertEqual(saved["stdout_from"], "derived")
        self.assertIn("sum of 2 and 3", saved["expected_rule"])

    def test_a_derived_expectation_is_shown_to_the_seats_that_must_meet_it(self) -> None:
        blueprint = json.dumps({**json.loads(CLI_BLUEPRINT), "run": "", "inputs": {}})
        code = "FILE: cli.py\n```python\nprint(5)\n```\n"
        chat = Scripted(architect=[blueprint], developer=[code])
        result = orchestra.run("a program that prints the sum of 2 and 3", "python",
                               chat, out_root=self.out, max_attempts=1)
        self.assertTrue(result["passed"])
        prompts = {call["seat"]: call["user"] for call in chat.calls}
        self.assertIn("a correct run prints exactly: '5'", prompts["developer"])

    def test_the_requirements_own_answer_beats_the_architects_guess(self) -> None:
        # A model that writes the code should not also get to say what it must
        # print: the sentence says 5, and the blueprint claiming 99 is ignored.
        blueprint = json.dumps({**json.loads(CLI_BLUEPRINT), "run": "",
                                "inputs": {}, "expected_stdout": "99"})
        code = "FILE: cli.py\n```python\nprint(5)\n```\n"
        chat = Scripted(architect=[blueprint], developer=[code])
        result = orchestra.run("a program that prints the sum of 2 and 3", "python",
                               chat, out_root=self.out, max_attempts=1)
        self.assertTrue(result["passed"])
        saved = json.loads((Path(result["path"]) / "blueprint.json").read_text())
        self.assertEqual(saved["expected_stdout"], "5")
        self.assertEqual(saved["stdout_from"], "derived")

    def test_the_callers_expectation_is_not_replaced_by_a_derived_one(self) -> None:
        chat = Scripted()
        result = orchestra.run("a program that prints the sum of 2 and 3", "python",
                               chat, out_root=self.out, max_attempts=1, expect="42")
        saved = json.loads((Path(result["path"]) / "blueprint.json").read_text())
        self.assertEqual(saved["expected_stdout"], "42")
        self.assertEqual(saved["stdout_from"], "request")

    def test_a_program_that_prints_nothing_fails_a_printing_requirement(self) -> None:
        # Nothing derivable, nothing declared: the fallback is that a job the
        # sentence says prints, prints. Exit 0 with empty stdout is not a pass.
        quiet = "FILE: cli.py\n```python\npass\n```\n"
        chat = Scripted(architect=[CLI_BLUEPRINT], developer=[quiet])
        result = orchestra.run("print the answer", "python", chat,
                               out_root=self.out, max_attempts=1)
        self.assertFalse(result["passed"])
        self.assertIn("printed nothing", result["errors"][-1])
        self.assertIsNone(result["state"]["build"]["matches"])

    def test_a_requirement_that_returns_nothing_may_still_pass_on_its_exit_code(self) -> None:
        quiet = "FILE: cli.py\n```python\npass\n```\n"
        chat = Scripted(architect=[CLI_BLUEPRINT], developer=[quiet])
        result = orchestra.run("a linter that exits 1 on a syntax error", "python",
                               chat, out_root=self.out, max_attempts=1)
        self.assertTrue(result["passed"])
        self.assertIsNone(result["state"]["build"]["matches"])


class ParseTests(unittest.TestCase):
    def test_a_fenced_verdict_is_read(self) -> None:
        self.assertEqual(orchestra.parse_json('```json\n{"status": "PASSED"}\n```'),
                         {"status": "PASSED"})

    def test_a_chatty_reply_is_read(self) -> None:
        self.assertEqual(orchestra.parse_json('Sure:\n{"status": "FAILED"} thanks'),
                         {"status": "FAILED"})

    def test_a_reply_with_no_json_is_empty_not_a_crash(self) -> None:
        self.assertEqual(orchestra.parse_json("I cannot help with that."), {})
        self.assertEqual(orchestra.parse_json(""), {})

    def test_a_reply_that_is_not_an_object_is_empty(self) -> None:
        self.assertEqual(orchestra.parse_json("[1, 2, 3]"), {})


if __name__ == "__main__":
    unittest.main()
