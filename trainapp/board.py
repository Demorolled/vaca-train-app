"""board — the one place the four seats agree on, and who may write where.

A prompt chain passes chat history from agent to agent: the fourth model sees
the third's raw reasoning, the second's tangents, and everything the first was
told, whether or not it needs any of it. This module is the alternative — a
single shared message board with four sections, one owner each, and a view per
seat that contains only what that seat may read.

    project_manifest   architect   path -> the functional requirement of the file
    design_ledger      tech lead   path -> pseudocode, steps, edge cases
    code_repository    developer   path -> the source
    bug_tracker        QA          structured failures, per file, per pass

The rules are enforced here rather than in a prompt, because a prompt is a
request and this is a guarantee:

* a seat that writes a section it does not own raises `BoardPermission`;
* a seat that reads a section it has no claim on raises too;
* `view(seat, only=...)` is the only thing an agent is given, so the developer's
  repair pass sees the failing file and its bugs — never the healthy files.

`user_requirement` is the one immutable input every seat may read: it is not a
section, it is the job.

No Pydantic: this project is standard library only, so the "typed dictionary"
is a dataclass-like class with the same field names as the brief, and `to_dict`
is what lands in the run copy.
"""
from __future__ import annotations

from datetime import datetime, timezone

SECTIONS = ("project_manifest", "design_ledger", "code_repository", "bug_tracker")

# One owner per section. This mapping IS the write policy.
WRITERS = {
    "project_manifest": "architect",
    "design_ledger": "tech_lead",
    "code_repository": "developer",
    "bug_tracker": "qa",
}
READERS = {
    "architect": {"project_manifest"},
    "tech_lead": {"project_manifest"},
    # The coder writes the code, so it also reads it: a repair pass has to see
    # the file it is fixing. Everything else it reads stays read-only.
    "developer": {"project_manifest", "design_ledger", "code_repository",
                  "bug_tracker"},
    "qa": {"code_repository", "project_manifest"},
}
SEATS = tuple(READERS)


class BoardPermission(PermissionError):
    """A seat tried to touch a section that is not its own."""


class BoardShape(ValueError):
    """A write had the wrong shape for its section."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AppMessageBoard:
    """The shared state. Seats mutate it only through the guarded methods."""

    def __init__(self, requirement: str, language: str = "python",
                 max_loops: int = 3, run_cmd: str = "",
                 inputs: dict[str, str] | None = None,
                 expected_stdout: str = "") -> None:
        self.user_requirement = requirement or ""
        self.language = language or ""
        self.project_manifest: dict[str, str] = {}
        self.design_ledger: dict[str, str] = {}
        self.code_repository: dict[str, str] = {}
        self.bug_tracker: list[dict] = []
        self.loop_count = 0
        self.max_loops = int(max_loops)
        # The manifest's non-per-file half, kept beside the paths so a reader
        # gets the whole blueprint in one place.
        self.tree = ""
        self.entry = ""
        self.dependencies: dict = {}
        # How the program is exercised. `run_cmd` is the invocation, arguments
        # included: without it a CLI that needs argv is run with none and fails
        # a gate it never broke. `inputs` are files it is run against but does
        # not ship (`notes.txt` for a line counter), written to the scratch
        # directory for the run and never to the app. `expected_stdout` is what
        # a correct run prints — without it the gate only sees an exit code,
        # and a program that prints the wrong answer passes.
        self.run_cmd = str(run_cmd or "").strip()
        self.inputs = {str(k): str(v) for k, v in (inputs or {}).items()
                       if str(k).strip() and not isinstance(v, (dict, list))}
        self.expected_stdout = str(expected_stdout or "")
        # Who said so. The request outranks the blueprint: a model that writes
        # both the code and the data it is run against can agree with itself,
        # so once the caller states the invocation the architect cannot revise
        # it away. Empty means the seat still supplies it.
        self.run_from = "request" if self.run_cmd else ""
        self.inputs_from = "request" if self.inputs else ""
        self.stdout_from = "request" if self.expected_stdout else ""
        # How a derived expectation was read off the requirement. Provenance the
        # copy needs: the sentence is weaker evidence than the caller's word.
        self.stdout_note = ""

    # ── reads ──────────────────────────────────────────────────────────────

    def read(self, seat: str, section: str):
        """The section's value, if this seat may read it at all."""
        if section not in SECTIONS:
            raise BoardShape(f"no section {section!r}; the board has "
                             + ", ".join(SECTIONS))
        if section not in READERS.get(seat, set()):
            raise BoardPermission(
                f"the {seat} may not read {section}; it may read "
                + (", ".join(sorted(READERS.get(seat, set()))) or "nothing"))
        value = getattr(self, section)
        return dict(value) if isinstance(value, dict) else list(value)

    def write(self, seat: str, section: str, value):
        """Replace a whole section. Only its owner may do this."""
        if section not in SECTIONS:
            raise BoardShape(f"no section {section!r}")
        owner = WRITERS[section]
        if owner != seat:
            raise BoardPermission(
                f"only the {owner} writes {section}; the {seat} tried to")
        if section == "bug_tracker":
            if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
                raise BoardShape("bug_tracker is a list of objects")
        elif not isinstance(value, dict):
            raise BoardShape(f"{section} is a mapping of path -> text")
        setattr(self, section, value)
        return value

    # ── the four commitments ───────────────────────────────────────────────

    def commit_manifest(self, seat: str, files: dict[str, str], *,
                        tree: str = "", entry: str = "", run_cmd: str = "",
                        inputs: dict[str, str] | None = None,
                        expected_stdout: str = "",
                        dependencies: dict | None = None) -> dict[str, str]:
        """The architect's blueprint: one entry per file, purpose as the value.

        The invocation, the fixtures and the expected output are only filled in
        here when the request did not state them itself — `_offer` is the whole
        rule, one call per field.
        """
        if not isinstance(files, dict) or not files:
            raise BoardShape("a manifest needs at least one path")
        for path, purpose in files.items():
            if not str(path).strip():
                raise BoardShape("a manifest path cannot be empty")
            if not isinstance(purpose, str):
                raise BoardShape(f"{path}: the purpose must be text")
        self.write(seat, "project_manifest", {str(k).strip(): v for k, v in files.items()})
        self.tree, self.entry = str(tree or ""), str(entry or "")
        self.run_cmd = self._offer("run_cmd", "run_from", str(run_cmd or "").strip())
        self.inputs = self._offer("inputs", "inputs_from",
                                  {str(k): str(v) for k, v in (inputs or {}).items()
                                   if str(k).strip() and not isinstance(v, (dict, list))})
        self.expected_stdout = self._offer("expected_stdout", "stdout_from",
                                           str(expected_stdout or ""))
        self.dependencies = dependencies or {}
        return self.project_manifest

    # The request and a value read off the requirement both outrank a seat: a
    # model that writes the code should not also get to say what it must print.
    FIXED = ("request", "derived")

    def _offer(self, field: str, source: str, value):
        """Take the seat's value for a field nothing firmer has already fixed."""
        if getattr(self, source) in self.FIXED:
            return getattr(self, field)
        setattr(self, source, "architect" if value else "")
        return value

    def derive_stdout(self, expected: str, rule: str = "") -> bool:
        """The runner, not a seat: read an expectation off the requirement.

        Only when nobody has stated one — the caller's word and the architect's
        both outrank a sentence. Returns whether it took, so the run can log it.
        """
        if self.stdout_from or not str(expected or "").strip():
            return False
        self.expected_stdout = str(expected)
        self.stdout_note = str(rule or "required output")
        self.stdout_from = "derived"
        return True

    def commit_design(self, seat: str, per_file: dict[str, str]) -> dict[str, str]:
        """The tech lead's ledger, one entry per file it designed."""
        if not isinstance(per_file, dict):
            raise BoardShape("the ledger is a mapping of path -> logic")
        return self.write(seat, "design_ledger", {str(k): str(v) for k, v in per_file.items()})

    def commit_code(self, seat: str, files: dict[str, str], *,
                    only: set[str] | None = None) -> dict[str, str]:
        """The developer's files, merged into the repository.

        `only` is the guard rather than a filter: any path in it that the
        manifest never named raises `BoardShape`, which is how "the developer
        cannot invent a file" stops being a prompt instruction.
        """
        if not isinstance(files, dict):
            raise BoardShape("code is a mapping of path -> source")
        for path, code in files.items():
            if not str(path).strip():
                raise BoardShape("a code path cannot be empty")
            if not isinstance(code, str):
                raise BoardShape(f"{path}: the source must be text")
        if only is not None:
            unknown = {p for p in only if p not in self.project_manifest}
            if unknown:
                raise BoardShape("not in the manifest: " + ", ".join(sorted(unknown)))
        self.write(seat, "code_repository",
                   {**self.code_repository, **{str(k): v for k, v in files.items()}})
        return self.code_repository

    def record_bug(self, seat: str, error: str, *, path: str = "",
                   scope: str = "code", attempt: int = 0,
                   toolchain: bool = False) -> dict:
        """One structured failure. QA is the only seat allowed to add one."""
        if WRITERS["bug_tracker"] != seat:
            raise BoardPermission(
                f"only the {WRITERS['bug_tracker']} writes bug_tracker; the {seat} tried to")
        bug = {"path": str(path or ""), "error": str(error or "").strip(),
               "scope": scope if scope in ("code", "design") else "code",
               "attempt": int(attempt), "toolchain": bool(toolchain),
               "resolved": False, "at": _now()}
        self.bug_tracker.append(bug)
        return bug

    def resolve(self, seat: str, paths: set[str] | None = None, *,
                everything: bool = False) -> int:
        """Mark bugs fixed once the code they blamed passes."""
        if WRITERS["bug_tracker"] != seat:
            raise BoardPermission(
                f"only the {WRITERS['bug_tracker']} resolves bugs; the {seat} tried to")
        resolved = 0
        for bug in self.bug_tracker:
            if bug.get("resolved"):
                continue
            if everything or (paths is not None and bug.get("path") in paths):
                bug["resolved"] = True
                resolved += 1
        return resolved

    def resolve_stale(self, seat: str, keep: set[str] | None = None) -> int:
        """A new verdict supersedes the per-file bugs it did not repeat.

        QA reviews the whole set every pass, so a file it does not blame this
        time is not still broken. Leaving those bugs open made the repair view
        grow back to the whole project by the third pass — the opposite of what
        the filter is for. Project-wide bugs (no path) are not touched: only a
        passing pass or the toolchain can settle those.
        """
        if WRITERS["bug_tracker"] != seat:
            raise BoardPermission(
                f"only the {WRITERS['bug_tracker']} resolves bugs; the {seat} tried to")
        keep = keep or set()
        resolved = 0
        for bug in self.bug_tracker:
            if bug.get("resolved") or not bug.get("path"):
                continue
            if bug["path"] not in keep:
                bug["resolved"] = True
                bug["resolved_at"] = _now()
                resolved += 1
        return resolved

    # ── the runner's own bookkeeping ───────────────────────────────────────

    def start_pass(self) -> int:
        """The orchestrator, not a seat: a new pass, a new loop number."""
        self.loop_count += 1
        return self.loop_count

    def reset_code(self) -> None:
        """A new blueprint invalidates code written for the old one.

        Called by the runner after the architect commits, never by a seat: the
        architect has no write access to `code_repository` and gains none here.
        """
        self.code_repository = {}

    # ── what an agent is actually given ────────────────────────────────────

    def active_bugs(self, paths: set[str] | None = None) -> list[dict]:
        out = [b for b in self.bug_tracker if not b.get("resolved")]
        if paths is not None:
            out = [b for b in out if b.get("path") in paths]
        return out

    def failing(self) -> list[str]:
        """The paths the open bugs blame, in order of first appearance."""
        seen: list[str] = []
        for bug in self.active_bugs():
            path = bug.get("path") or ""
            if path and path not in seen:
                seen.append(path)
        return seen

    def view(self, seat: str, only: set[str] | None = None) -> dict:
        """The filtered context for one seat: sections it may read, nothing else.

        `only` truncates the two large sections (`design_ledger`,
        `code_repository`) and the bug tracker to the paths named — which is how
        a repair pass carries one broken file instead of the project.
        """
        out: dict = {"user_requirement": self.user_requirement,
                     "language": self.language}
        readable = READERS.get(seat, set())
        if "project_manifest" in readable:
            out["project_manifest"] = dict(self.project_manifest)
            out["tree"] = self.tree
            out["entry"] = self.entry
            out["run_cmd"] = self.run_cmd
            out["run_from"] = self.run_from
            out["inputs"] = dict(self.inputs)
            out["expected_stdout"] = self.expected_stdout
        if "design_ledger" in readable:
            design = dict(self.design_ledger)
            out["design_ledger"] = ({k: v for k, v in design.items() if k in only}
                                    if only is not None else design)
        if "code_repository" in readable:
            code = dict(self.code_repository)
            out["code_repository"] = ({k: v for k, v in code.items() if k in only}
                                      if only is not None else code)
        if "bug_tracker" in readable:
            out["bug_tracker"] = self.active_bugs(only)
        return out

    # ── serialisation ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"user_requirement": self.user_requirement, "language": self.language,
                "project_manifest": dict(self.project_manifest),
                "design_ledger": dict(self.design_ledger),
                "code_repository": dict(self.code_repository),
                "bug_tracker": [dict(b) for b in self.bug_tracker],
                "loop_count": self.loop_count, "max_loops": self.max_loops,
                "tree": self.tree, "entry": self.entry,
                "run_cmd": self.run_cmd, "run_from": self.run_from,
                "inputs": dict(self.inputs), "inputs_from": self.inputs_from,
                "expected_stdout": self.expected_stdout,
                "stdout_from": self.stdout_from,
                "stdout_note": self.stdout_note,
                "dependencies": dict(self.dependencies or {})}

    @classmethod
    def from_dict(cls, data: dict) -> "AppMessageBoard":
        board = cls(str(data.get("user_requirement") or ""),
                    str(data.get("language") or "python"),
                    int(data.get("max_loops") or 3),
                    run_cmd=str(data.get("run_cmd") or ""),
                    inputs=dict(data.get("inputs") or {}),
                    expected_stdout=str(data.get("expected_stdout") or ""))
        for field, source in (("run_cmd", "run_from"), ("inputs", "inputs_from"),
                              ("expected_stdout", "stdout_from")):
            setattr(board, source, str(data.get(source) or ""))
        board.stdout_note = str(data.get("stdout_note") or "")
        board.project_manifest = dict(data.get("project_manifest") or {})
        board.design_ledger = dict(data.get("design_ledger") or {})
        board.code_repository = dict(data.get("code_repository") or {})
        board.bug_tracker = [dict(b) for b in (data.get("bug_tracker") or [])]
        board.loop_count = int(data.get("loop_count") or 0)
        board.tree = str(data.get("tree") or "")
        board.entry = str(data.get("entry") or "")

        board.dependencies = dict(data.get("dependencies") or {})
        return board
