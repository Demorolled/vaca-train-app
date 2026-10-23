"""runprobe — an invocation that makes an application set print something.

Half the library cannot be judged because its reference run produces no output:
TypeScript is typechecked rather than run, and an app that ignores its arguments
exits silently. Those sets can only ever prove "it compiles", which is not the
claim the gate is supposed to make.

Some of them do have observable behaviour — a CLI prints usage for `--help`, a
server prints a boot line. This tries a short list of standard invocations, twice
each, and keeps the first one that exits 0 with *identical* non-empty output both
times. The result is stored per task and `functionprobe.run_set` uses it, so the
probe and the reference see the same invocation.

Discovery is deliberately conservative: a non-deterministic line, a hang, or a
non-zero exit all mean "not observable", never a guess.
"""
from __future__ import annotations

import json

from . import execution, library

PROBE_FILE = "run_probes.jsonl"
CANDIDATES: tuple[tuple[str, ...], ...] = (
    (),
    ("--help",),
    ("-h",),
    ("--version",),
)


def probe_path():
    return library.library_dir() / PROBE_FILE


def load() -> dict[str, dict]:
    path = probe_path()
    if not path.exists():
        return {}
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("task_id"):
            rows[row["task_id"]] = row
    return rows


def for_task(task: dict, probes: dict[str, dict] | None = None) -> dict | None:
    rows = probes if probes is not None else load()
    return rows.get(task.get("id", ""))


def _run(task: dict, args: tuple[str, ...], timeout_s: float) -> tuple[bool, str] | None:
    result = execution.run_files(task["files"], task["language"], timeout_s=timeout_s,
                                 args=list(args))
    if not result.ok:
        return None
    text = " ".join((result.stdout or "").split())
    return (True, text) if text else None


def discover(task: dict, timeout_s: float = 8) -> dict | None:
    """The first standard invocation with stable, non-empty output."""
    for args in CANDIDATES:
        first = _run(task, args, timeout_s)
        if first is None:
            continue
        # Only a candidate that printed something is worth a second run: the
        # re-run is the determinism check, not part of the search.
        if _run(task, args, timeout_s) != first:
            return None
        return {"task_id": task["id"], "language": task["language"],
                "args": list(args), "stdout": first[1][:2000]}
    return None


def build(tasks: list[dict], timeout_s: float = 8, log=None) -> dict:
    """Discover probes for `tasks`, merge them into the sheet, and report."""
    existing = load()
    found: dict[str, dict] = {}
    tried = 0
    for task in tasks:
        tried += 1
        probe = discover(task, timeout_s)
        if probe:
            found[task["id"]] = probe
            if log:
                log(f"[probe] {task['language']:10s} {task['id'].split('/')[-1][:40]} "
                    f"args={probe['args']}")
    merged = {**existing, **found}
    probe_path().write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in merged.values()),
        encoding="utf-8")
    return {"tried": tried, "found": len(found), "total": len(merged),
            "by_language": {language: sum(1 for p in found.values()
                                          if p["language"] == language)
                            for language in sorted({p["language"] for p in found.values()})}}
