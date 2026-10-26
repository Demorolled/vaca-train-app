"""orchestra — four players write one application, in order.

    requirement → architect → tech lead → developer → QA
                                              ↑          |
                                              +— fail ———+   (max 3 passes)

Each seat has one job and one output shape, and the boundaries between them are
enforced by what each node is allowed to read:

* the **architect** never sees code and is never asked to fix it — it decides
  the files, their purpose, the entry point and the dependencies;
* the **tech lead** writes logic, not code: the algorithm, the state a file
  keeps, and the edge cases that would otherwise be missed;
* the **developer** writes the literal code but cannot invent paths. A file it
  genuinely needs is *requested*, and the state goes back to the architect,
  because a new file is a design change, not a style choice;
* **QA** returns JSON and is not the last word. The real toolchain runs the set
  afterwards, and both must pass. A model that says `PASSED` over code that
  does not compile has failed; the compiler's words are what the developer
  gets on the next pass.

That last rule is the point of running this inside VACA rather than as a prompt
chain: the deterministic boundary is `execution.run_files`, which is the same
gate the battery and the library already trust.

Nothing is passed between seats. They share one `AppMessageBoard` (see
`trainapp/board.py`) and each node reads it through `board.view(seat)`, which
gives back only the sections that seat owns a read claim on — the architect
never sees code, the developer's repair pass sees only the file QA blamed. A
write from the wrong seat raises `BoardPermission`, so the boundaries above are
checked, not merely asked for. `BandState` is the run's log — seats, notes,
history, build — and `save_run` writes the whole thing: blueprint, reasoning,
every attempt's code, every verdict, the bug tracker, the build output.

    python3 -m trainapp.orchestra --require "a python CLI that prints the first \
12 primes" --language python

It talks to whichever band player is named, or the leader when none is.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from . import builder, config, execution
from .board import AppMessageBoard
from .expect import derive as derive_expectation, wants_output

MAX_ATTEMPTS = 3
# The four seats, in the order a run visits them.
SEATS = ("architect", "tech_lead", "developer", "qa")
REQUEST_RE = re.compile(r"^\s*REQUEST_FILE:\s*`?([^\s`]+)`?\s*(?:[—-]\s*(.*))?$", re.M)
JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class BandState(TypedDict, total=False):
    """The run's own metadata. The project itself lives on the board.

    Nothing here is passed between seats: the board is the single source of
    truth, and each node reads it through `AppMessageBoard.view(seat)`. This
    dict is the log — who played, what happened, what the toolchain said.
    """

    user_requirement: str
    language: str
    model: str                 # who each seat actually was, for the copy
    seats: dict                # seat -> model, when the band is more than one
    board: Any                 # AppMessageBoard: manifest, ledger, code, bugs
    errors: list               # the last verdict in words, for logs
    scope: str                 # "code" (rewrite) or "design" (re-plan)
    loop_count: int
    passed: bool
    failing: list              # the paths the open bugs blame
    requested: list            # files the developer asked the architect for
    qa: list                   # every verdict, newest last
    build: dict                # the toolchain's own answer
    history: list              # attempt -> code, errors, verdict
    notes: list                # what each seat actually did


# ── personas ───────────────────────────────────────────────────────────────

ARCHITECT_SYSTEM = (
    "You are the architect in a four-piece band that writes software. You do "
    "not write code and you are never asked to fix it: you decide the shape of "
    "the project — the files, their jobs, the entry point and the dependencies.")
ARCHITECT_ASK = """Project requirement:
{requirement}

Language: {language}
{revision}{gate}
Reply with JSON only — no prose, no fence:
{{"tree": "one path per line, two spaces of indent per level",
  "files": [{{"path": "relative/path", "purpose": "one line"}}],
  "entry": "the file that starts the program, or an empty string",
{run_fields}  "dependencies": {{"relative/path": ["the standard-library imports it needs"]}}}}"""

# What the architect may say about how the program is exercised. Each field is
# only asked for when the request left it open, and the prose only explains the
# ones still in the JSON: the caller's word outranks the model's, because a
# model that writes both the code and the data it runs on can agree with itself.
ARCHITECT_RUN_NOTE = """
`run` is how the program is exercised: if it takes an argument, the command must
include one (`python cli.py sample.txt`). `inputs` is the file that argument
names, so the gate has something to read. `expected_stdout` is what a correct
run prints and the gate compares it — an exit code of 0 is not enough, since a
program that prints the wrong answer exits 0 too. A program run with no
arguments, or against a file that is not there, looks broken to the gate even
when it is correct.

These describe the program the requirement asks for; they do not change it. When
it takes no arguments and reads nothing, leave all three empty — do not invent a
file for it to read just to have something to test."""

# A requirement that names no input gets no input fields. Asking a chatty model
# for `run`/`inputs` on "print the sum of 2 and 3" is enough for it to design a
# file-reading CLI and then fail the requirement it was given: the field is an
# invitation, so it is only offered when the job implies one.
INPUT_WORDS = re.compile(
    r"\b(argument|arguments|argv|args|file|files|path|paths|stdin|input|inputs|"
    r"reads?|reading|line|lines|csv|json|directory|dir|folder|command-line|"
    r"cmdline|flags?)\b", re.I)

TECH_LEAD_SYSTEM = (
    "You are the tech lead in a four-piece band that writes software. You "
    "design the logic; you do not write the code. Be concrete enough that a "
    "developer who has never seen the problem can implement it without guessing.")
TECH_LEAD_ASK = """Requirement:
{requirement}

Blueprint:
{blueprint}

For every file in the blueprint: the algorithm in ordered steps, the state it
keeps, its inputs and outputs, and the edge cases that would otherwise be
missed. Markdown, one section per file, in blueprint order. No code blocks.
{revision}{gate}"""

DEVELOPER_SYSTEM = (
    "You are the developer in a four-piece band that writes software. You "
    "write the literal, production-ready code for the files the architect "
    "named, following the tech lead's logic exactly. You never invent a path.")
DEVELOPER_ASK = """Requirement:
{requirement}

Language: {language}

Blueprint — these paths and no others:
{blueprint}

Logic to implement:
{reasoning}

Write every file in full. Format exactly:

FILE: path/to/file
```{language}
<complete contents>
```

Nothing else. Standard library only unless the blueprint names a dependency.
If the blueprint is missing a file you genuinely need, do not create it: write
`REQUEST_FILE: path — purpose` on its own line and stop.
{gate}"""

DEVELOPER_REPAIR = """The QA pass rejected the code. Fix it.

Requirement:
{requirement}

What failed:
{errors}

Only these files are yours to change:
{code}

Return the complete file(s) above in the same FILE: format, and nothing else.
Do not restate, rename or reformat any other file in the project.
{gate}"""

QA_SYSTEM = (
    "You are the QA engineer in a four-piece band that writes software. You "
    "review code against the requirement: syntax, missing imports, logic gaps, "
    "security flaws. The harness compiles and runs the code after you, so "
    "report what a successful run would still not catch.")
QA_ASK = """Requirement:
{requirement}

Language: {language}

Blueprint — what this code is supposed to do, one line per file:
{blueprint}

Code under review:
{code}

Judge the code against the blueprint and the requirement. A behaviour the
blueprint asks for is not a defect: do not invent requirements neither one
states.

Reply with JSON only:
{{"status": "PASSED" or "FAILED",
  "errors": ["one concrete, actionable fix per line"],
  "scope": "code" or "design",
  "files": ["the paths the errors belong to"]}}

`scope` is "design" only when no rewrite of these files can be correct — the
blueprint itself is wrong and the tech lead has to re-plan.
{gate}"""


# ── state and parsing ──────────────────────────────────────────────────────

def new_state(requirement: str, language: str = "python",
              max_loops: int = MAX_ATTEMPTS, smoke: str = "",
              inputs: dict | None = None, expect: str = "") -> BandState:
    """A fresh board. `smoke`/`inputs`/`expect` are the request's own word on
    how the program is exercised, and they outrank the architect's."""
    return BandState(user_requirement=requirement.strip(), language=language,
                     model="", seats={},
                     board=AppMessageBoard(requirement.strip(), language, max_loops,
                                           run_cmd=smoke, inputs=inputs,
                                           expected_stdout=expect),
                     errors=[], scope="code", loop_count=0, passed=False,
                     failing=[], requested=[], qa=[], build={}, history=[],
                     notes=[])


def parse_json(reply: str) -> dict:
    """The first JSON object in a reply, however the model dressed it up.

    A structured-output server returns bare JSON; a local one may still fence
    it or say "here you go" first. Parsing is tolerant, validation is not:
    every node checks the keys it needs before using them.
    """
    text = (reply or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
    match = JSON_RE.search(text)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _board(state: BandState) -> AppMessageBoard:
    return state["board"]


def _files(state: BandState) -> list[dict]:
    code = _board(state).code_repository
    return [{"path": path, "content": code[path]} for path in sorted(code)]


def _blueprint_files(state: BandState) -> list[dict]:
    return [{"path": path, "purpose": purpose}
            for path, purpose in _board(state).project_manifest.items()]


def _entry(state: BandState) -> str:
    board = _board(state)
    return board.entry if board.entry in board.code_repository else ""


def _ledger_for(text: str, paths: list[str]) -> dict[str, str]:
    """Split the tech lead's markdown into one entry per file it names.

    The ledger is keyed by path so the developer can be given the logic of the
    file it is writing and nothing else. A reply that never names a file is
    kept under the first path: the design still belongs somewhere, and dropping
    it would be worse than filing it loosely.
    """
    text = (text or "").strip()
    if not text:
        return {}
    sections: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        stripped = line.strip()
        named = next((p for p in paths
                      if p in line and (stripped.startswith("#")
                                        or stripped.startswith("`")
                                        or stripped.startswith("**")
                                        or stripped.startswith("-"))), "")
        if named:
            current = named
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    ledger = {path: "\n".join(lines).strip() for path, lines in sections.items()
              if "\n".join(lines).strip()}
    return ledger or ({paths[0]: text} if paths else {})


def needs_input(requirement: str) -> bool:
    """Does this requirement imply an argument or a file to read?"""
    return bool(INPUT_WORDS.search(requirement or ""))


def _architect_gate(board: AppMessageBoard) -> tuple[str, str]:
    """(JSON field lines, prose) for the exercise fields the request left open."""
    fields: list[str] = []
    fixed: list[str] = []
    takes_input = needs_input(board.user_requirement)
    if board.run_from == "request":
        fixed.append(f"command: {board.run_cmd}")
    elif takes_input:
        fields.append('  "run": "the command a user would type, arguments '
                      'included, or an empty string",')
    if board.inputs_from == "request":
        fixed.append("inputs: " + ", ".join(sorted(board.inputs)))
    elif takes_input:
        fields.append('  "inputs": {"relative/path": "contents, for a file the '
                      'program reads but does not ship"},')
    if board.stdout_from in ("request", "derived"):
        source = "the caller" if board.stdout_from == "request" \
            else "the requirement"
        fixed.append(f"expected output ({source}): {board.expected_stdout!r}")
    else:
        fields.append('  "expected_stdout": "what a correct run prints, or an '
                      'empty string",')
    gate = ""
    if fixed:
        gate = ("How this program is exercised is fixed for this run. That is "
                "input, not design — do not restate or revise it:\n"
                + "\n".join(f"  {line}" for line in fixed) + "\n")
    rest = ""
    if not takes_input and board.run_from != "request":
        rest = ("This program takes no arguments and reads no files. Do not add "
                "an input just to have one: it is run bare.\n")
    prose = ARCHITECT_RUN_NOTE if fields else ""
    return "".join(line + "\n" for line in fields), gate + rest + prose


def _block(path: str, code: str, language: str) -> str:
    return f"FILE: {path}\n```{language}\n{code.rstrip()}\n```"


def _blame_from_output(text: str, paths) -> str:
    """The file the compiler named, when it named exactly one.

    A toolchain failure with no path makes the repair view degenerate: with
    nothing blamed, the coder is handed the whole project again. The compiler
    usually says which file it choked on, so that is read rather than guessed.
    """
    body = text or ""
    hits = sorted({path for path in paths if path and path in body},
                  key=len, reverse=True)
    # `main.py` inside `src/main.py` is the same complaint, not a second one.
    hits = [hit for hit in hits
            if not any(hit != other and hit in other for other in hits)]
    return hits[0] if len(hits) == 1 else ""


def _gate_note(board: AppMessageBoard) -> str:
    """What the run will be judged on, said plainly to the seats that write it.

    A gate the developer was never told about is not strict, it is hidden: the
    expected output is shown here so a difference is the code's, not a surprise.
    """
    lines: list[str] = []
    if board.run_cmd:
        lines.append(f"  it is run as: {board.run_cmd}")
    if board.inputs:
        lines.append("  it reads: " + ", ".join(sorted(board.inputs)))
    if board.expected_stdout.strip():
        lines.append("  a correct run prints exactly: "
                     f"{board.expected_stdout.strip()!r}")
    if not lines:
        return ""
    return ("\n\nHow this program is judged (the harness does this after you):\n"
            + "\n".join(lines)
            + "\nMatch that exactly — no extra words, no extra punctuation.")


def _log(log, line: str) -> None:
    if log:
        log(line)


async def _ask(chat, system: str, user: str, json_object: bool = False,
               temperature: float | None = None) -> dict:
    """One model turn, off the event loop.

    The chat clients are blocking urllib, so the async surface here is real:
    four seats could overlap, and a run is a coroutine either way.
    """
    return await asyncio.to_thread(chat.ask, system, user, json_object, temperature)


# ── nodes ──────────────────────────────────────────────────────────────────

async def scaffolding_node(state: BandState, chat, log=None) -> BandState:
    """The architect: files, purposes, entry point, dependencies.

    It writes `project_manifest` and nothing else. The code reset that follows a
    new blueprint is the runner's, not the architect's: a seat gains no write
    access by asking the orchestrator to do it.
    """
    board = _board(state)
    requested = state.get("requested") or []
    revision = ""
    if requested:
        revision = ("\nThe developer needs these files as well. Add them to the "
                    "blueprint with a purpose each:\n"
                    + "\n".join(f"- {path}" for path in requested))
    # The requirement's own sentence is read before the architect is asked, so
    # the derivation is not a tie-break against the model's guess: it is what
    # the architect is given to design to, and a seat cannot revise it.
    if board.stdout_from == "":
        derived = derive_expectation(board.user_requirement)
        if board.derive_stdout(derived["expected"], derived["rule"]):
            state["notes"].append(
                f"gate: expects {board.expected_stdout!r} ({derived['rule']})")
            _log(log, f"  gate: expects {board.expected_stdout!r} "
                      f"({derived['rule']})")
    run_fields, gate = _architect_gate(board)
    reply = await _ask(chat, ARCHITECT_SYSTEM, ARCHITECT_ASK.format(
        requirement=board.user_requirement, language=board.language,
        revision=revision, gate=gate, run_fields=run_fields),
        json_object=True, temperature=0.0)
    blueprint = parse_json(reply["content"])
    files = [f for f in (blueprint.get("files") or [])
             if isinstance(f, dict) and str(f.get("path") or "").strip()]
    if not files:
        state["errors"] = ["the architect returned no file paths"]
        state["notes"].append("architect: no blueprint")
        return state
    manifest = {str(f["path"]).strip(): str(f.get("purpose") or "").strip()
                for f in files}
    raw_inputs = blueprint.get("inputs")
    inputs = {str(k).strip(): str(v) for k, v in raw_inputs.items()
              if str(k).strip() and not isinstance(v, (dict, list))} \
        if isinstance(raw_inputs, dict) else {}
    board.commit_manifest("architect", manifest,
                          tree=str(blueprint.get("tree") or ""),
                          entry=str(blueprint.get("entry") or "").strip(),
                          run_cmd=str(blueprint.get("run") or "").strip(),
                          inputs=inputs,
                          expected_stdout=str(blueprint.get("expected_stdout") or ""),
                          dependencies=blueprint.get("dependencies") or {})
    board.reset_code()
    state["requested"] = []
    state["notes"].append(f"architect: {len(manifest)} file(s), "
                          f"entry {board.entry or '—'}"
                          + (f", run `{board.run_cmd}`" if board.run_cmd else ""))
    _log(log, f"  architect: {len(manifest)} files"
              + (f", run `{board.run_cmd}`" if board.run_cmd else "")
              + (" (from the request)" if board.run_from == "request" else ""))
    return state


async def reasoning_node(state: BandState, chat, log=None) -> BandState:
    """The tech lead: per-file logic, in markdown, without code."""
    board = _board(state)
    # The guarded read: the tech lead has a claim on the manifest and no other
    # section, which is exactly what this call proves on every run.
    manifest = board.read("tech_lead", "project_manifest")
    lines = [f"- {path} — {purpose}" for path, purpose in manifest.items()]
    revision = ""
    if state.get("scope") == "design" and state.get("errors"):
        revision = ("\nA first design was rejected for these reasons. Address "
                    "every one of them:\n"
                    + "\n".join(f"- {e}" for e in state["errors"]))
    reply = await _ask(chat, TECH_LEAD_SYSTEM, TECH_LEAD_ASK.format(
        requirement=board.user_requirement,
        blueprint="\n".join(lines) or "(no files planned)",
        revision=revision, gate=_gate_note(board)), temperature=0.2)
    ledger = _ledger_for(str(reply["content"] or ""), list(manifest))
    board.commit_design("tech_lead", ledger)
    size = sum(len(text) for text in ledger.values())
    state["notes"].append(f"tech lead: {size} chars across {len(ledger)} file(s)")
    state["scope"] = "code"
    state["errors"] = []
    _log(log, f"  tech lead: {size} chars")
    return state


async def coder_node(state: BandState, chat, log=None) -> BandState:
    """The developer: complete files, in `FILE:` blocks.

    A repair pass reads the board with `only=failing`, so the failing file and
    its open bugs are the whole context — the healthy files are neither re-sent
    nor rewritten. And a path the architect never named cannot be committed:
    `commit_code` refuses it, so it becomes a request instead.
    """
    board = _board(state)
    language = board.language
    current = dict(board.code_repository)
    if current and state.get("errors"):
        failing = [p for p in (state.get("failing") or []) if p in current] or \
            sorted(current)
        view = board.view("developer", only=set(failing))
        code = "\n\n".join(_block(path, text, language)
                           for path, text in view["code_repository"].items())
        bugs = [b for b in view["bug_tracker"] if b.get("error")]
        errors = "\n".join(
            f"- {(b.get('path') or 'the project')}: {b['error']}" for b in bugs) \
            or "\n".join(f"- {e}" for e in state["errors"])
        ask = DEVELOPER_REPAIR.format(requirement=view["user_requirement"],
                                      errors=errors, code=code,
                                      gate=_gate_note(board))
    else:
        view = board.view("developer")
        blueprint = "\n".join(f"- {path} — {purpose}"
                              for path, purpose in view["project_manifest"].items())
        reasoning = "\n\n".join(f"## {path}\n{logic}"
                                 for path, logic in view["design_ledger"].items())
        ask = DEVELOPER_ASK.format(
            requirement=view["user_requirement"], language=language,
            blueprint=blueprint or "(the architect named no files)",
            reasoning=(reasoning or "(no design)")[:12000],
            gate=_gate_note(board))
    reply = await _ask(chat, DEVELOPER_SYSTEM, ask, temperature=0.2)
    content = reply["content"] or ""
    requested = [m.group(1).strip() for m in REQUEST_RE.finditer(content)]
    parsed = builder.parse_files(
        content, language,
        [{"path": p} for p in board.project_manifest] or None)
    known = set(board.project_manifest)
    planned = {f["path"]: f["content"] for f in parsed
               if f["path"] and f["path"] in known}
    invented = [f["path"] for f in parsed if f["path"] and f["path"] not in known]
    if planned:
        board.commit_code("developer", planned)
    # An explicit `REQUEST_FILE:` and a path it slipped in without asking are
    # the same thing to the board: a file the developer needs and may not add.
    asked = set(requested) | set(invented)
    if asked:
        state["requested"] = sorted(set(state.get("requested") or []) | asked)
    state["notes"].append(
        f"developer: {len(planned)} file(s) written"
        + (f", asked for {len(state['requested'])} more" if state["requested"] else "")
        + (f", refused {len(invented)} unplanned path(s)" if invented else ""))
    _log(log, f"  developer: {len(planned)} file(s)"
              + (f", requested {state['requested']}" if state["requested"] else "")
              + (f", refused {invented}" if invented else ""))
    return state


async def qa_node(state: BandState, chat, log=None) -> BandState:
    """QA's verdict, then the toolchain's. Both must pass.

    The verdict becomes structured bugs on the board — path, scope, attempt,
    toolchain flag — and a passing pass resolves them. Nothing writes over a
    bug: the tracker is audit history, so the fourth copy of the run still
    shows what the first pass got wrong.
    """
    board = _board(state)
    view = board.view("qa")
    files = [{"path": path, "content": text}
             for path, text in view["code_repository"].items()]
    code = "\n\n".join(_block(f["path"], f["content"], board.language) for f in files)
    # QA reads the manifest too, so it reviews the code against the job as it
    # was planned. Without it the reviewer invents requirements the other seats
    # were never given and fails a build for doing what it was told.
    blueprint = "\n".join(f"- {path} — {purpose or 'no purpose stated'}"
                          for path, purpose in view["project_manifest"].items())
    reply = await _ask(chat, QA_SYSTEM, QA_ASK.format(
        requirement=view["user_requirement"], language=board.language,
        blueprint=blueprint or "(no blueprint)", code=code[:24000],
        gate=_gate_note(board)), json_object=True, temperature=0.0)
    verdict = parse_json(reply["content"])
    status = str(verdict.get("status") or "FAILED").upper()
    errors = [str(e).strip() for e in (verdict.get("errors") or []) if str(e).strip()]
    scope = str(verdict.get("scope") or "code").lower()
    blamed = [str(p) for p in (verdict.get("files") or []) if str(p).strip()]

    entry = _entry(state)
    # The invocation is whatever the board holds — the request's if it stated
    # one, the architect's otherwise — minus the entry itself. Fixtures are
    # written into the scratch directory beside the code so the invocation has
    # its input; a path the project ships stays the code's, because source wins
    # and a fixture never becomes part of the app.
    fixtures = [{"path": path, "content": text}
                for path, text in sorted((board.inputs or {}).items())
                if path not in board.code_repository]
    build = execution.run_files(files + fixtures, board.language, entry=entry,
                                timeout_s=60,
                                args=builder.args_from_run(board.run_cmd, entry))
    output = (build.error or build.stderr or build.stdout or "").strip()
    # An exit code of 0 says the program did not crash. It does not say it did
    # the job, and with fixture data the run is only as meaningful as what it is
    # compared against — so when the board names the expected output, the gate
    # compares it.
    want = (board.expected_stdout or "").strip()
    got = (build.stdout or "").strip()
    # None, not True: with no expectation there is nothing to match, and the
    # copy should not claim a check that never happened.
    matched = None if not want else got == want
    silent = matched is None and not got and wants_output(board.user_requirement)
    problem = ""
    if not build.ok:
        problem = output or "the run failed"
    elif matched is False:
        problem = (f"the run printed {got[:300]!r} but a correct run prints "
                   f"{want[:300]!r}")
    elif silent:
        # The fallback when nothing can be derived: the sentence says it prints,
        # so an exit code with no output is not a pass either.
        problem = "the run printed nothing, and the requirement says it prints an answer"
    state["build"] = {"ok": bool(build.ok), "command": build.command,
                      "exit_code": build.exit_code,
                      "expected": want, "expected_from": board.stdout_from,
                      "stdout": got[-1500:], "matches": matched,
                      "error": problem[:1500]}
    # The gate is deterministic evidence; the review is an opinion. When the
    # build compiled and printed exactly what it had to print, the opinion is
    # advice, not a veto — otherwise an unstated requirement the brief never
    # made ("also handle a header row") can fail a build that met its contract.
    verified = matched is True and bool(build.ok)
    advisory = status == "FAILED" and verified and not problem
    state["qa"].append({"status": status, "errors": errors, "scope": scope,
                        "files": blamed, "build_ok": bool(build.ok),
                        "output_ok": matched, "advisory": advisory})
    target = (blamed[0] if len(blamed) == 1
              else _blame_from_output(output, board.code_repository))
    # This verdict supersedes the per-file bugs it did not repeat, so a file
    # fixed two passes ago is not still handed back to the coder as failing.
    # `keep` holds the file the compiler named as well as the ones QA did: a
    # verdict that names nothing must not close a bug the build just repeated.
    board.resolve_stale("qa", set(blamed) | ({target} if target else set()))
    for error in errors:
        board.record_bug("qa", error, path=target, scope=scope,
                         attempt=board.loop_count)
    # The failure says how it was run: "Usage: cli.py <path>" from a bare run
    # reads like broken code, and the developer needs the invocation to tell.
    ran = f" (run as: {build.command})" if build.command else ""
    toolchain_error = ([] if not problem
                       else [f"the toolchain rejected it{ran}: {problem}"])
    if problem:
        board.record_bug("qa", toolchain_error[0], path=target, scope="code",
                         attempt=board.loop_count, toolchain=True)
        scope = "code"
    state["errors"] = [] if advisory else errors + toolchain_error
    state["scope"] = scope if status == "FAILED" else "code"
    state["failing"] = board.failing()
    state["passed"] = not problem and (status == "PASSED" or verified)
    if state["passed"]:
        board.resolve("qa", everything=True)
    detail = ", output differs" if matched is False else \
        (", printed nothing" if silent else "")
    if advisory:
        _log(log, f"  QA: {status} — advisory, the gate verified the build "
                  f"({len(errors)} note(s))")
    else:
        _log(log, f"  QA: {status}, build {'ok' if build.ok else 'failed'}{detail}"
                  f" ({len(state['errors'])} issue(s))")
    return state


# ── the run ────────────────────────────────────────────────────────────────

def _emit_pass(on_pass, state: BandState, board, attempt: int,
               note: str = "") -> None:
    """Hand one finished pass to a watcher: what failed and what it recorded.

    The bug tracker is the run's history, and a copy on disk only shows it at
    the end. A watcher (the app's job status) gets each pass as it happens, so a
    failing run is legible while it is still failing. A broken watcher must
    never fail a build, hence the swallow.
    """
    if on_pass is None:
        return
    try:
        on_pass({"pass": attempt, "passed": bool(state.get("passed")),
                 "failing": list(board.failing()),
                 "bugs": [dict(bug) for bug in board.bug_tracker
                          if bug.get("attempt") == attempt],
                 "note": note})
    except Exception:
        pass


async def run_band(requirement: str, language: str = "python", chat=None,
                   max_attempts: int = MAX_ATTEMPTS, out_root: Path | None = None,
                   log=None, chats: dict | None = None, smoke: str = "",
                   inputs: dict | None = None, expect: str = "",
                   on_pass=None) -> dict:
    """Requirement in, one saved build out. Never raises for a model failure.

    `chats` gives individual seats their own player — `{"qa": vaca, "developer":
    stock}` — which is the whole point of a band: the bulk of the work can run
    on one model and the review on another. A seat with no entry uses `chat`.

    `smoke`, `inputs` and `expect` are the request's own statement of how the
    program is exercised: the command to run, the files it reads, and what a
    correct run prints. They go on the board before the architect speaks and it
    cannot revise them, so the test data is not written by the model being
    tested.

    `on_pass` is called once per finished pass with that pass's bugs — the
    history the app shows while a build is still failing.
    """
    chat = chat or builder.chat_for()
    seats = {seat: chat for seat in SEATS}
    for seat, player in (chats or {}).items():
        if seat not in seats:
            raise KeyError(f"no seat named {seat!r}; the seats are {', '.join(SEATS)}")
        if player is not None:
            seats[seat] = player
    attempts = max(1, int(max_attempts))
    state = new_state(requirement, language, smoke=smoke, inputs=inputs, expect=expect)
    state["model"] = getattr(chat, "model", "")
    state["seats"] = {seat: str(getattr(player, "model", player))
                      for seat, player in seats.items()}
    if len(set(state["seats"].values())) == 1:
        _log(log, f"orchestra: {chat.model} · {language} · max {attempts} pass(es)")
    else:
        _log(log, "orchestra: " + " · ".join(
            f"{seat}={state['seats'][seat]}" for seat in SEATS)
            + f" · max {attempts} pass(es)")
    state = await scaffolding_node(state, seats["architect"], log)
    board = _board(state)
    if board.project_manifest:
        state = await reasoning_node(state, seats["tech_lead"], log)
    while state["loop_count"] < attempts and board.project_manifest:
        state["loop_count"] = board.start_pass()
        attempt = state["loop_count"]
        _log(log, f"pass {attempt}/{attempts}")
        state = await coder_node(state, seats["developer"], log)
        if state.get("requested"):
            # A missing file is a blueprint change: back to the architect.
            asked = list(state["requested"])
            state = await scaffolding_node(state, seats["architect"], log)
            state = await reasoning_node(state, seats["tech_lead"], log)
            state["history"].append({"attempt": attempt, "files": {},
                                     "errors": [f"the developer asked for {p}"
                                                for p in asked],
                                     "passed": False, "requested": asked})
            _emit_pass(on_pass, state, board, attempt, "asked for a file")
            continue
        state = await qa_node(state, seats["qa"], log)
        state["history"].append({
            "attempt": attempt,
            "files": dict(board.code_repository),
            "errors": list(state.get("errors") or []),
            "passed": bool(state.get("passed")),
            "scope": state.get("scope"),
        })
        _emit_pass(on_pass, state, board, attempt)
        if state.get("passed"):
            break
        if state.get("scope") == "design":
            state = await reasoning_node(state, seats["tech_lead"], log)
    saved = save_run(state, out_root)
    _log(log, ("built: " if state["passed"] else "not built: ") + saved["path"])
    return {"passed": bool(state.get("passed")), "attempts": state["loop_count"],
            "path": saved["path"], "files": sorted(_board(state).code_repository),
            "errors": list(state.get("errors") or []), "state": state}


def run(requirement: str, language: str = "python", chat=None,
        max_attempts: int = MAX_ATTEMPTS, out_root: Path | None = None,
        log=None, chats: dict | None = None, smoke: str = "",
        inputs: dict | None = None, expect: str = "", on_pass=None) -> dict:
    """The synchronous door for callers that are not already in an event loop."""
    return asyncio.run(run_band(requirement, language, chat, max_attempts,
                                out_root, log, chats, smoke, inputs, expect,
                                on_pass))


# ── the copy ───────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "app")[:60]


def save_run(state: BandState, root: Path | None = None) -> dict:
    """Write the whole run: blueprint, design, every attempt, verdicts, build."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = (root or (config.data_dir() / "band")) / stamp / _slug(
        state.get("user_requirement", ""))
    seen, base = 1, target
    while target.exists():
        seen += 1
        target = base.with_name(f"{base.name}-{seen}")
    target.mkdir(parents=True, exist_ok=True)

    board = _board(state)
    written = 0
    for path, code in sorted(board.code_repository.items()):
        rel = [p for p in str(path).replace("\\", "/").split("/") if p]
        if not rel or any(p in (".", "..") for p in rel):
            continue
        dest = target / "files" / Path(*rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(code, encoding="utf-8")
        written += 1

    for attempt in state.get("history") or []:
        for path, code in sorted((attempt.get("files") or {}).items()):
            rel = [p for p in str(path).replace("\\", "/").split("/") if p]
            if not rel or any(p in (".", "..") for p in rel):
                continue
            dest = target / f"attempt-{attempt['attempt']}" / "files" / Path(*rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(code, encoding="utf-8")

    # The exercise fields carry who said so: a pass is only worth what the
    # invocation, the fixtures and the expected output are worth, and the copy
    # has to make a self-authored one visible.
    (target / "blueprint.json").write_text(json.dumps({
        "tree": board.tree, "entry": board.entry, "run": board.run_cmd,
        "run_from": board.run_from, "inputs": board.inputs,
        "inputs_from": board.inputs_from,
        "expected_stdout": board.expected_stdout,
        "stdout_from": board.stdout_from, "expected_rule": board.stdout_note,
        "dependencies": board.dependencies,
        "project_manifest": board.project_manifest}, indent=2) + "\n",
        encoding="utf-8")
    (target / "reasoning.md").write_text("\n\n".join(
        [f"## {path}\n\n{logic}" for path, logic in board.design_ledger.items()])
        + "\n", encoding="utf-8")
    (target / "bugs.jsonl").write_text(
        "".join(json.dumps(bug) + "\n" for bug in board.bug_tracker),
        encoding="utf-8")
    (target / "qa.jsonl").write_text(
        "".join(json.dumps(v) + "\n" for v in (state.get("qa") or [])),
        encoding="utf-8")
    build = state.get("build") or {}
    (target / "build.txt").write_text("\n".join([
        f"command: {build.get('command', '')}",
        f"exit: {build.get('exit_code')}",
        f"ok: {build.get('ok')}",
        f"expected: {build.get('expected', '')!r}",
        f"stdout: {build.get('stdout', '')!r}",
        "matches: " + ("unknown" if build.get("matches") is None
                       else str(build.get("matches"))),
        f"error: {build.get('error', '')}",
    ]) + "\n", encoding="utf-8")
    (target / "state.json").write_text(
        json.dumps({**{k: v for k, v in state.items() if k not in ("history", "board")},
                    "board": board.to_dict(),
                    "attempts": len(state.get("history") or [])},
                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (target / "notes.txt").write_text(
        "\n".join(state.get("notes") or []) + "\n", encoding="utf-8")
    return {"path": str(target), "files": written,
            "attempts": len(state.get("history") or [])}


# ── a run as a job the app can start and watch ────────────────────────────
# A build is minutes of four models' time, so it runs on a thread and publishes
# each seat's line as it happens, the way validation, growth and the builder
# already do. The status is mirrored to disk so a restart still shows the last
# run, and the result survives independently of the copy on disk.

JOB_LOCK = threading.RLock()
JOB: dict = {"state": "idle", "requirement": "", "language": "python",
             "player": "", "model": "", "attempts": 0, "smoke": "",
             "expect": "", "started_at": "", "finished_at": "", "error": "",
             "passed": False, "path": "", "files": [], "errors": [],
             "passes": [], "bugs": [], "log": []}
_THREAD: threading.Thread | None = None
MAX_LOG = 80


def status_path() -> Path:
    return config.data_dir() / "orchestra" / "status.json"


def status() -> dict:
    """The job's state, falling back to the last finished run on disk."""
    with JOB_LOCK:
        snapshot = dict(JOB)
    if snapshot.get("state") == "idle":
        path = status_path()
        if path.exists():
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                saved = {}
            if saved.get("state") in ("done", "failed"):
                snapshot = {**snapshot, **saved}
    return snapshot


def _publish(**update) -> None:
    with JOB_LOCK:
        JOB.update(update)
        payload = dict(JOB)
    try:
        path = status_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    except OSError:
        pass


def _say(line: str) -> None:
    with JOB_LOCK:
        log = [*(JOB.get("log") or []), line][-MAX_LOG:]
    _publish(log=log)


def run_job(requirement: str, language: str, player: str, attempts: int,
            chat=None, smoke: str = "", inputs: dict | None = None,
            expect: str = "") -> dict:
    """Run the band and publish the outcome. Never raises."""
    passes: list[dict] = []

    def collect(record: dict) -> None:
        # Each pass is published as it lands, so a failing build is legible in
        # the app while it is still failing rather than only in its copy.
        passes.append(record)
        _publish(passes=list(passes))

    try:
        chat = chat or builder.chat_for(player)
        result = run(requirement, language, chat, attempts, log=_say,
                     smoke=smoke, inputs=inputs, expect=expect, on_pass=collect)
    except Exception as err:  # a missing player must fail the job, not the server
        _publish(state="failed", error=f"{type(err).__name__}: {err}"[:400],
                 finished_at=_now(), passed=False, passes=list(passes))
        return status()
    board = (result.get("state") or {}).get("board")
    _publish(state="done", finished_at=_now(), passed=bool(result["passed"]),
             path=result["path"], files=list(result["files"]),
             errors=list(result["errors"])[:20], attempts=result["attempts"],
             passes=list(passes),
             bugs=[dict(b) for b in getattr(board, "bug_tracker", []) or []])
    return status()


def parse_inputs(pairs: list[str]) -> dict[str, str]:
    """`["notes.txt=hello"]` -> `{"notes.txt": "hello"}` for `--input`.

    The content is taken literally, one line per flag; a fixture that needs more
    lines can be a second flag per line only if the program reads them that way,
    so a long fixture belongs in a file the caller points at instead.
    """
    out: dict[str, str] = {}
    for pair in pairs or []:
        path, sep, content = str(pair).partition("=")
        if not sep or not path.strip():
            raise ValueError(f"--input wants PATH=CONTENT, got {pair!r}")
        out[path.strip()] = content
    return out


def start(requirement: str, language: str = "python", player: str = "",
          attempts: int = MAX_ATTEMPTS, smoke: str = "",
          inputs: dict | None = None, expect: str = "") -> dict:
    """Start a build in the background; returns immediately with its status."""
    global _THREAD
    requirement = (requirement or "").strip()
    if not requirement:
        return {**status(), "error": "say what to build first"}
    with JOB_LOCK:
        if JOB.get("state") == "running":
            return {**status(), "error": "an orchestra run is already going"}
    try:
        chat = builder.chat_for(player)
    except KeyError as err:
        return {**status(), "error": str(err.args[0] if err.args else err)}
    _publish(state="running", requirement=requirement, language=language,
             player=player or "leader", model=getattr(chat, "model", ""),
             attempts=int(attempts), smoke=(smoke or "").strip(),
             expect=(expect or "").strip(), started_at=_now(), finished_at="",
             error="", passed=False, path="", files=[], errors=[], log=[],
             passes=[], bugs=[])
    _THREAD = threading.Thread(target=run_job,
                               args=(requirement, language, player, int(attempts),
                                     chat, smoke, inputs, expect),
                               daemon=True)
    _THREAD.start()
    return status()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Four seated models write one application")
    parser.add_argument("--require", required=True, help="what to build")
    parser.add_argument("--language", default="python")
    parser.add_argument("--player", default="",
                        help="band player to use; the leader when empty")
    parser.add_argument("--attempts", type=int, default=MAX_ATTEMPTS)
    parser.add_argument("--out", default="", help="where to copy the run")
    parser.add_argument("--seat", action="append", default=[], metavar="SEAT=PLAYER",
                        help="give one seat its own band player; repeatable")
    parser.add_argument("--smoke", default="", metavar="COMMAND",
                        help="the invocation the program must satisfy, e.g. "
                             "'python cli.py notes.txt'; the architect cannot "
                             "revise it")
    parser.add_argument("--input", action="append", default=[], metavar="PATH=CONTENT",
                        help="a file the smoke invocation reads, for the run "
                             "only; repeatable")
    parser.add_argument("--expect", default="", metavar="TEXT",
                        help="what a correct run prints; the gate compares it")
    args = parser.parse_args(argv)
    try:
        inputs = parse_inputs(args.input)
    except ValueError as err:
        parser.error(str(err))

    chat = builder.chat_for(args.player)
    chats: dict = {}
    for spec in args.seat:
        seat, _, player = spec.partition("=")
        chats[seat.strip()] = builder.chat_for(player.strip())
    def show_pass(record: dict) -> None:
        """The bug tracker, pass by pass — the part a failing run is judged on."""
        head = (f"pass {record['pass']}: "
                + ("passed" if record.get("passed") else "failed"))
        if record.get("failing"):
            head += " · failing: " + ", ".join(record["failing"])
        if record.get("note"):
            head += f" · {record['note']}"
        print(head, flush=True)
        for bug in record.get("bugs") or []:
            mark = "✓" if bug.get("resolved") else "✗"
            print(f"    {mark} {bug.get('path') or 'project'}: "
                  f"{str(bug.get('error') or '')[:200]}", flush=True)

    result = run(args.require, args.language, chat, args.attempts,
                 Path(args.out) if args.out else None,
                 log=lambda line: print(line, flush=True), chats=chats,
                 smoke=args.smoke, inputs=inputs, expect=args.expect,
                 on_pass=show_pass)
    print(json.dumps({k: result[k] for k in ("passed", "attempts", "path",
                                             "files", "errors")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
