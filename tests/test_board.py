"""The blackboard: four sections, one owner each, and a view per seat."""
from __future__ import annotations

import unittest

from trainapp.board import AppMessageBoard, BoardPermission, BoardShape, READERS, WRITERS


def filled() -> AppMessageBoard:
    board = AppMessageBoard("print the answer", "python")
    board.commit_manifest("architect", {"main.py": "entry point",
                                        "util.py": "helper"},
                          tree="main.py\nutil.py", entry="main.py")
    board.commit_design("tech_lead", {"main.py": "call util then print",
                                      "util.py": "return 42"})
    board.commit_code("developer", {"main.py": "from util import answer\nprint(answer())\n",
                                    "util.py": "def answer():\n    return 42\n"})
    return board


class WriteTests(unittest.TestCase):
    def test_each_seat_writes_its_own_section(self) -> None:
        board = AppMessageBoard("x")
        board.commit_manifest("architect", {"a.py": "entry"})
        board.commit_design("tech_lead", {"a.py": "print 1"})
        board.commit_code("developer", {"a.py": "print(1)\n"})
        board.record_bug("qa", "prints the wrong number", path="a.py", attempt=1)
        self.assertEqual(board.project_manifest, {"a.py": "entry"})
        self.assertEqual(board.design_ledger, {"a.py": "print 1"})
        self.assertEqual(board.code_repository, {"a.py": "print(1)\n"})
        self.assertEqual(len(board.bug_tracker), 1)

    def test_the_architect_cannot_write_code(self) -> None:
        board = filled()
        with self.assertRaises(BoardPermission):
            board.commit_code("architect", {"main.py": "print(1)\n"})
        with self.assertRaises(BoardPermission):
            board.write("architect", "code_repository", {"main.py": "x"})

    def test_the_developer_cannot_rewrite_the_manifest_or_the_design(self) -> None:
        board = filled()
        with self.assertRaises(BoardPermission):
            board.write("developer", "project_manifest", {"main.py": "something else"})
        with self.assertRaises(BoardPermission):
            board.write("developer", "design_ledger", {"main.py": "print 2"})

    def test_only_qa_adds_or_resolves_bugs(self) -> None:
        board = filled()
        for seat in ("architect", "tech_lead", "developer"):
            with self.assertRaises(BoardPermission):
                board.record_bug(seat, "fix me", path="main.py")
            with self.assertRaises(BoardPermission):
                board.resolve(seat, everything=True)

    def test_the_tech_lead_cannot_write_code_or_bugs(self) -> None:
        board = filled()
        with self.assertRaises(BoardPermission):
            board.write("tech_lead", "code_repository", {"main.py": "x"})
        with self.assertRaises(BoardPermission):
            board.record_bug("tech_lead", "nope")

    def test_a_manifest_needs_at_least_one_path(self) -> None:
        board = AppMessageBoard("x")
        with self.assertRaises(BoardShape):
            board.commit_manifest("architect", {})

    def test_a_path_the_manifest_never_named_is_refused(self) -> None:
        board = filled()
        with self.assertRaises(BoardShape) as caught:
            board.commit_code("developer", {"stray.py": "print(1)\n"},
                              only={"stray.py"})
        self.assertIn("stray.py", str(caught.exception))
        self.assertNotIn("stray.py", board.code_repository)

    def test_code_is_merged_not_replaced(self) -> None:
        board = filled()
        board.commit_code("developer", {"main.py": "print(2)\n"})
        self.assertEqual(board.code_repository["main.py"], "print(2)\n")
        self.assertIn("util.py", board.code_repository)

    def test_the_manifest_carries_how_the_program_is_invoked(self) -> None:
        board = AppMessageBoard("x")
        board.commit_manifest("architect", {"cli.py": "entry"},
                              entry="cli.py", run_cmd="python cli.py notes.txt",
                              inputs={"notes.txt": "a\nb\n"})
        self.assertEqual(board.run_cmd, "python cli.py notes.txt")
        # Every seat that may read the manifest gets the invocation with it.
        for seat in ("tech_lead", "developer", "qa"):
            self.assertEqual(board.view(seat)["run_cmd"], "python cli.py notes.txt")
            self.assertEqual(board.view(seat)["inputs"], {"notes.txt": "a\nb\n"})
        restored = AppMessageBoard.from_dict(board.to_dict())
        self.assertEqual(restored.run_cmd, "python cli.py notes.txt")
        self.assertEqual(restored.inputs, {"notes.txt": "a\nb\n"})
        self.assertEqual(restored.expected_stdout, "")
        self.assertEqual(restored.run_from, "architect")

    def test_the_requests_invocation_outranks_the_blueprints(self) -> None:
        # A model that writes the code and the data it runs against can agree
        # with itself, so once the caller says how the program is exercised the
        # architect cannot revise it away.
        board = AppMessageBoard("count lines", "python",
                                run_cmd="python cli.py notes.txt",
                                inputs={"notes.txt": "a\nb\n"},
                                expected_stdout="2")
        board.commit_manifest("architect", {"cli.py": "entry"},
                              run_cmd="python cli.py other.txt",
                              inputs={"other.txt": "x"}, expected_stdout="9")
        self.assertEqual(board.run_cmd, "python cli.py notes.txt")
        self.assertEqual(board.inputs, {"notes.txt": "a\nb\n"})
        self.assertEqual(board.expected_stdout, "2")
        self.assertEqual((board.run_from, board.inputs_from, board.stdout_from),
                         ("request", "request", "request"))

    def test_the_architect_still_fills_what_the_request_left_open(self) -> None:
        board = AppMessageBoard("count lines", "python",
                                run_cmd="python cli.py notes.txt")
        board.commit_manifest("architect", {"cli.py": "entry"},
                              inputs={"notes.txt": "a\n"}, expected_stdout="1")
        self.assertEqual(board.run_cmd, "python cli.py notes.txt")
        self.assertEqual(board.inputs, {"notes.txt": "a\n"})
        self.assertEqual(board.expected_stdout, "1")
        self.assertEqual(board.run_from, "request")
        self.assertEqual((board.inputs_from, board.stdout_from),
                         ("architect", "architect"))

    def test_a_replan_can_take_its_own_fields_back(self) -> None:
        board = AppMessageBoard("x")
        board.commit_manifest("architect", {"a.py": "entry"}, run_cmd="python a.py 1")
        board.commit_manifest("architect", {"a.py": "entry"})
        self.assertEqual(board.run_cmd, "")
        self.assertEqual(board.run_from, "")

    def test_a_new_blueprint_clears_code_but_only_from_the_runner(self) -> None:
        board = filled()
        board.reset_code()
        self.assertEqual(board.code_repository, {})
        # The architect still has no standing to do it itself.
        with self.assertRaises(BoardPermission):
            board.write("architect", "code_repository", {})


class ReadTests(unittest.TestCase):
    def test_a_seat_reads_only_its_own_sections(self) -> None:
        board = filled()
        self.assertEqual(board.read("tech_lead", "project_manifest")["main.py"],
                         "entry point")
        with self.assertRaises(BoardPermission):
            board.read("tech_lead", "code_repository")
        with self.assertRaises(BoardPermission):
            board.read("architect", "design_ledger")
        with self.assertRaises(BoardPermission):
            board.read("qa", "design_ledger")

    def test_the_qa_reads_the_code_and_the_manifest(self) -> None:
        board = filled()
        self.assertIn("main.py", board.read("qa", "code_repository"))
        self.assertIn("main.py", board.read("qa", "project_manifest"))
        with self.assertRaises(BoardPermission):
            board.read("qa", "bug_tracker")

    def test_a_read_returns_a_copy_not_the_live_section(self) -> None:
        board = filled()
        got = board.read("developer", "code_repository")
        got["main.py"] = "tampered"
        self.assertNotEqual(board.code_repository["main.py"], "tampered")


class ViewTests(unittest.TestCase):
    def test_the_developers_view_carries_everything_it_may_read(self) -> None:
        view = filled().view("developer")
        self.assertEqual(set(view) - {"user_requirement", "language"}, {
            "project_manifest", "tree", "entry", "run_cmd", "run_from",
            "inputs", "expected_stdout", "design_ledger", "code_repository",
            "bug_tracker"})

    def test_a_repair_view_carries_only_the_failing_file(self) -> None:
        board = filled()
        board.record_bug("qa", "prints 41", path="main.py", attempt=1)
        view = board.view("developer", only={"main.py"})
        self.assertEqual(list(view["code_repository"]), ["main.py"])
        self.assertEqual(list(view["design_ledger"]), ["main.py"])
        self.assertEqual([b["error"] for b in view["bug_tracker"]], ["prints 41"])
        self.assertNotIn("util.py", str(view["code_repository"]))

    def test_the_qa_view_has_no_design_and_no_other_seat_state(self) -> None:
        board = filled()
        board.record_bug("qa", "x", path="main.py")
        view = board.view("qa")
        self.assertNotIn("design_ledger", view)
        self.assertNotIn("bug_tracker", view)
        self.assertIn("code_repository", view)

    def test_the_architect_view_has_no_code(self) -> None:
        view = filled().view("architect")
        for section in ("code_repository", "design_ledger", "bug_tracker"):
            self.assertNotIn(section, view)


class BugTests(unittest.TestCase):
    def test_a_bug_records_what_the_next_pass_needs(self) -> None:
        board = filled()
        board.start_pass()
        bug = board.record_bug("qa", "imports the wrong module", path="main.py",
                               scope="code", attempt=board.loop_count,
                               toolchain=True)
        self.assertEqual(bug["path"], "main.py")
        self.assertEqual(bug["attempt"], 1)
        self.assertTrue(bug["toolchain"])
        self.assertFalse(bug["resolved"])
        self.assertTrue(bug["at"])

    def test_open_bugs_are_what_the_developer_is_shown(self) -> None:
        board = filled()
        board.record_bug("qa", "fix a", path="main.py")
        board.record_bug("qa", "fix b", path="util.py")
        self.assertEqual(len(board.active_bugs()), 2)
        self.assertEqual(board.failing(), ["main.py", "util.py"])
        board.resolve("qa", {"main.py"})
        self.assertEqual([b["error"] for b in board.active_bugs()], ["fix b"])
        self.assertEqual(board.failing(), ["util.py"])

    def test_a_pass_that_clears_everything_resolves_everything(self) -> None:
        board = filled()
        board.record_bug("qa", "fix a", path="main.py", attempt=1)
        board.record_bug("qa", "fix b", path="util.py", attempt=1)
        self.assertEqual(board.resolve("qa", everything=True), 2)
        self.assertEqual(board.active_bugs(), [])
        # The history is still there: nothing is deleted, only resolved.
        self.assertEqual(len(board.bug_tracker), 2)

    def test_the_loop_count_is_the_runners_not_a_seats(self) -> None:
        board = filled()
        self.assertEqual(board.start_pass(), 1)
        self.assertEqual(board.start_pass(), 2)
        self.assertEqual(board.loop_count, 2)
        self.assertEqual(board.max_loops, 3)


class PersistenceTests(unittest.TestCase):
    def test_the_board_round_trips_through_json(self) -> None:
        board = filled()
        board.record_bug("qa", "fix a", path="main.py", attempt=1)
        restored = AppMessageBoard.from_dict(board.to_dict())
        self.assertEqual(restored.project_manifest, board.project_manifest)
        self.assertEqual(restored.design_ledger, board.design_ledger)
        self.assertEqual(restored.code_repository, board.code_repository)
        self.assertEqual(restored.bug_tracker, board.bug_tracker)
        self.assertEqual(restored.entry, "main.py")

    def test_every_section_has_exactly_one_writer(self) -> None:
        self.assertEqual(set(WRITERS.values()), set(READERS))
        self.assertEqual(len(set(WRITERS.values())), len(WRITERS))


if __name__ == "__main__":
    unittest.main()
