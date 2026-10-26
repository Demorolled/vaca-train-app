"""harvest — every finished build becomes evidence, and once a month a sheet.

Two things are recorded per build, and they are not the same thing:

* the **run** — requirement, blueprint, the design, every attempt, every QA
  verdict, which player ran it, when — goes to `library/band_runs.jsonl`. This
  is the "everything" copy: a failed build is as informative as a passing one,
  and it is never trained on.
* the **task** — only a build whose own toolchain run passed, as one library
  entry per finished program, goes to `library/band_builds.jsonl` with a
  `verified` validation record. That is what a later SFT sheet can learn from.

Three sources, all of them written only after a build finished: the copies
under `data/band/<stamp>/…` (orchestra), `data/builds/…` (builder), and the
builder's own pool (`data/builder/pool.jsonl`) so history from before the
copies existed is not lost. A build that never finished cannot become a task
by accident. Ingestion is idempotent: it dedupes on the code's content hash,
the same key the rest of the library uses, so running it twice — or the timer
firing while you are away — adds nothing twice.

    python3 -m trainapp.harvest --scan        # what is on disk
    python3 -m trainapp.harvest --monthly     # ingest + this month's sheets
    python3 -m trainapp.harvest --status      # when it last ran, what it kept

`--monthly` is the scheduled door (`deploy/vaca-harvest.timer`, OnCalendar=monthly)
and refuses to run twice inside 28 days unless `--force` is passed, so a
restart cannot re-cut a month.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import config, library, librarysft

RUNS_FILE = "band_runs.jsonl"
STATUS_FILE = "harvest.status.json"
SNAPSHOT_DIR = "harvest"
GAP_DAYS = 28


# ── where the copies are ───────────────────────────────────────────────────

def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def status_path() -> Path:
    return library.library_dir() / STATUS_FILE


def runs_path() -> Path:
    return library.library_dir() / RUNS_FILE


def snapshot_dir() -> Path:
    path = library.library_dir() / SNAPSHOT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stamp_dirs(root: Path) -> list[Path]:
    """Every completed run directory under a copy root, newest first."""
    if not root.exists():
        return []
    return sorted((p for p in root.glob("*/*") if p.is_dir()), reverse=True)


def run_dirs() -> list[Path]:
    data = config.data_dir()
    return _stamp_dirs(data / "band") + _stamp_dirs(data / "builds")


# ── reading one run ────────────────────────────────────────────────────────

def _walk_files(root: Path) -> list[dict]:
    if not root.is_dir():
        return []
    out: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            out.append({"path": path.relative_to(root).as_posix(),
                        "content": path.read_text(encoding="utf-8")})
        except (OSError, UnicodeDecodeError):
            continue
    return out


def _json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _lines(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def read_run(directory: Path) -> dict | None:
    """One run, normalised. `None` when the directory holds no finished build."""
    state = _json(directory / "state.json")
    record = _json(directory / "record.json")
    if state:
        files = _walk_files(directory / "files")
        if not files:
            return None
        build = state.get("build") or {}
        # The board is the single source of truth since the blackboard landed;
        # the flat keys are what copies made before it carry, and both are read
        # so a run is never harvested differently because of when it ran.
        board = state.get("board") or {}
        legacy = state.get("scaffolding") or {}
        ledger = board.get("design_ledger") or {}
        manifest = board.get("project_manifest") or {}
        planned = ([{"path": path, "purpose": purpose}
                    for path, purpose in manifest.items()] if manifest
                   else list(legacy.get("files") or []))
        # A pass with nothing to compare printed the right thing only by not
        # crashing. `matches` is True when the gate actually compared the output,
        # False when it compared and differed, and None when nothing was known —
        # only the first is evidence a library entry can rest on.
        compared = build.get("matches")
        checked = compared is not None
        passed_check = compared is True
        return {
            "id": directory.name, "kind": "orchestra", "path": str(directory),
            "at": directory.parent.name,
            "language": board.get("language") or state.get("language", ""),
            "requirement": (board.get("user_requirement")
                            or state.get("user_requirement", "")),
            "model": state.get("model", ""), "files": files,
            "ok": (bool(build.get("ok")) and bool(state.get("passed")) and passed_check),
            "checked": checked,
            "attempts": int(state.get("attempts") or 0),
            "blueprint": {"entry": board.get("entry") or legacy.get("entry", ""),
                          "files": planned},
            "reasoning": ("\n\n".join(ledger.values())
                          or state.get("reasoning_steps") or ""),
            "qa": _lines(directory / "qa.jsonl"),
            "bugs": list(board.get("bug_tracker") or []),
            "build": build,
        }
    if record:
        files = _walk_files(directory / "files") or [
            {"path": str(f.get("path", "")), "content": str(f.get("content", ""))}
            for f in (record.get("files") or [])]
        if not files:
            return None
        task = record.get("task") or {}
        compared = (record.get("build") or {}).get("matches")
        return {
            "id": directory.name, "kind": "builder", "path": str(directory),
            "at": directory.parent.name, "language": task.get("language", ""),
            "requirement": task.get("brief", ""), "model": record.get("model", ""),
            "files": files,
            # The same rule as an orchestra run: a build is evidence only if the
            # plan said what a correct run prints and the run was compared to it.
            "ok": bool(record.get("ok")) and compared is True,
            "checked": compared is not None,
            "attempts": int(record.get("runs") or 0),
            "blueprint": {}, "reasoning": "",
            "qa": [], "build": record.get("build") or {},
        }
    return None


def pool_runs() -> list[dict]:
    """Builds recorded in the builder's pool, which predates the copies."""
    out: list[dict] = []
    for row in _lines(config.data_dir() / "builder" / "pool.jsonl"):
        files = [f for f in (row.get("files") or []) if isinstance(f, dict)]
        if not files:
            continue
        task = row.get("task") or {}
        stamp = str(row.get("at") or "")
        out.append({
            "id": f"{row.get('label', '?')}--{task.get('id', 'task')}",
            "kind": "builder-pool",
            "path": f"pool:{row.get('sha256') or row.get('label', '?')}:"
                    f"{task.get('id', '')}",
            "at": stamp, "language": task.get("language", ""),
            "requirement": task.get("brief", ""),
            "model": row.get("model", ""),
            "files": [{"path": str(f.get("path", "")),
                       "content": str(f.get("content", ""))} for f in files],
            "ok": (bool(row.get("ok"))
                   and (row.get("build") or {}).get("matches") is True),
            "checked": (row.get("build") or {}).get("matches") is not None,
            "attempts": int(row.get("runs") or 0),
            "blueprint": {}, "reasoning": "", "qa": [],
            "build": row.get("build") or {},
        })
    return out


def all_runs() -> list[dict]:
    """Every finished build the project has on disk, newest sources first."""
    return [r for r in (read_run(d) for d in run_dirs()) if r] + pool_runs()


def scan() -> dict:
    """What is on disk now, without writing anything."""
    runs = all_runs()
    by_kind: dict[str, int] = {}
    by_language: dict[str, int] = {}
    for run in runs:
        by_kind[run["kind"]] = by_kind.get(run["kind"], 0) + 1
        if run["ok"]:
            by_language[run["language"]] = by_language.get(run["language"], 0) + 1
    return {"runs": len(runs), "verified": sum(1 for r in runs if r["ok"]),
            "failed": sum(1 for r in runs if not r["ok"]),
            "unchecked": sum(1 for r in runs if r.get("checked") is False),
            "by_kind": by_kind, "verified_by_language": by_language,
            "dirs": [r["path"] for r in runs][:50]}


# ── turning a run into library evidence ────────────────────────────────────

def _hash(language: str, code: str) -> str:
    return hashlib.sha256(f"{language}\0{code}".encode("utf-8")).hexdigest()


def task_from(run: dict) -> dict:
    """A library entry for a verified run: the program, and the set it came in."""
    files = run["files"]
    entry = str((run.get("blueprint") or {}).get("entry") or "")
    target = entry if any(f["path"] == entry for f in files) else files[0]["path"]
    code = next(f["content"] for f in files if f["path"] == target)
    title = (run.get("requirement") or "a small program").strip()[:120]
    return library.task_row(
        origin="band-build",
        language=run["language"],
        title=title,
        code=code,
        description=run.get("requirement", ""),
        runnable=True,
        tags=["harvest", run["kind"]] + ([run["model"]] if run.get("model") else []),
        category="app",
        source=run["path"],
        files=files if len(files) > 1 else None,
        target=target if len(files) > 1 else "",
    )


def _validation(task: dict, run: dict) -> dict:
    build = run.get("build") or {}
    return {"id": task["id"], "language": task["language"], "status": "verified",
            "checked_at": _now(), "duration_ms": 0,
            "command": str(build.get("command") or "harvest: run recorded ok"),
            "exit_code": build.get("exit_code", 0), "stderr": "", "stdout": "",
            "error": "", "source": "harvest", "run": run["path"]}


def _existing_codes() -> set[str]:
    return {_hash(t.get("language", ""), t.get("code", ""))
            for t in library.load_tasks(all_languages=True)}


def _existing_runs() -> set[str]:
    return {row.get("path", "") for row in _lines(runs_path())}


def ingest(dry_run: bool = False) -> dict:
    """Add every run to the run log, and every verified one to the library."""
    runs = all_runs()
    known_runs = _existing_runs()
    known_codes = _existing_codes()
    new_runs = [r for r in runs if r["path"] not in known_runs]
    pairs: list[tuple[dict, dict]] = []
    skipped = 0
    for run in new_runs:
        if not run["ok"]:
            continue
        task = task_from(run)
        key = _hash(task["language"], task["code"])
        if key in known_codes:
            skipped += 1
            continue
        known_codes.add(key)
        pairs.append((task, run))
    tasks = [task for task, _run in pairs]
    by_language: dict[str, int] = {}
    for task in tasks:
        by_language[task["language"]] = by_language.get(task["language"], 0) + 1
    result = {"runs": len(runs), "new_runs": len(new_runs),
              "verified_runs": sum(1 for r in new_runs if r["ok"]),
              "unverified": sum(1 for r in new_runs if not r["ok"]),
              "unchecked": sum(1 for r in new_runs if r.get("checked") is False),
              "added": len(tasks), "skipped": skipped, "by_language": by_language,
              "sheet": str(library.library_dir() / library.BAND_FILE),
              "dry_run": bool(dry_run), "tasks": tasks}
    if dry_run or not new_runs:
        return result
    if new_runs:
        with runs_path().open("a", encoding="utf-8") as handle:
            for run in new_runs:
                handle.write(json.dumps(run, ensure_ascii=False) + "\n")
    if tasks:
        with (library.library_dir() / library.BAND_FILE).open("a", encoding="utf-8") as handle:
            for task in tasks:
                handle.write(json.dumps(task, ensure_ascii=False) + "\n")
        with library.validation_path().open("a", encoding="utf-8") as handle:
            for task, source in pairs:
                handle.write(json.dumps(_validation(task, source),
                                        ensure_ascii=False) + "\n")
    return result


# ── the month's sheets ─────────────────────────────────────────────────────

def sft_rows(tasks: list[dict]) -> list[dict]:
    """Training rows for the harvested programs a single row can carry.

    A file set is not one instruction — `scaffoldsft` is the module that turns a
    set into rows — so only single-file builds land here, which is stated rather
    than silently dropped: the run summary reports both counts.
    """
    rows: list[dict] = []
    for task in tasks:
        if library.is_multi_file(task):
            continue
        code = (task.get("code") or "").strip()
        if not code:
            continue
        rows.append({
            "instruction": librarysft.INSTRUCTION.format(
                language=task["language"], title=task["title"]),
            "input": (task.get("description") or "").strip(),
            "output": code,
            "source": "library:band-build",
            "meta": {"language": task["language"], "task_id": task["id"],
                     "origin": task["origin"], "bytes": len(code.encode("utf-8")),
                     "family": task.get("family", ""), "run": task.get("source", "")},
        })
    return rows


def _month_tasks() -> list[dict]:
    """Band tasks not yet written to this month's sheet.

    The sheet is keyed on the month, not on one invocation: a build harvested by
    hand in the morning still belongs in the month's sheet, and running the job
    again must not write it a second time.
    """
    written = {row.get("id") for row in _lines(snapshot_dir() / f"{_month()}.jsonl")}
    return [task for task in library.ingest_band() if task.get("id") not in written]


def status() -> dict:
    path = status_path()
    if not path.is_file():
        return {"state": "never", "at": "", "month": "", "runs": 0, "added": 0,
                "sheet": str(library.library_dir() / library.BAND_FILE)}
    saved = _json(path)
    return saved or {"state": "never"}


def _too_soon(last: str) -> bool:
    if not last:
        return False
    try:
        when = datetime.fromisoformat(last)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).days < GAP_DAYS


def run(dry_run: bool = False, force: bool = False) -> dict:
    """The monthly door: harvest, refresh the index, cut this month's sheets."""
    previous = status()
    if not force and _too_soon(str(previous.get("at") or "")):
        return {"state": "skipped", "reason": f"last harvest {previous['at']}",
                "at": previous.get("at", ""), "month": previous.get("month", "")}
    gathered = ingest(dry_run=dry_run)
    month = _month()
    fresh = _month_tasks()
    rows = sft_rows(fresh)
    payload = {**gathered, "state": "dry-run" if dry_run else "done",
               "at": _now(), "month": month, "month_tasks": len(fresh),
               "sft_rows": len(rows),
               "sft_skipped_multi_file": sum(1 for t in fresh
                                             if library.is_multi_file(t))}
    payload.pop("tasks", None)
    if dry_run:
        return payload
    index = library.build()
    target = snapshot_dir() / f"{month}.jsonl"
    with target.open("a", encoding="utf-8") as handle:
        for task in fresh:
            handle.write(json.dumps({**task, "harvested_at": payload["at"]},
                                    ensure_ascii=False) + "\n")
    sft_path = snapshot_dir() / f"{month}_sft.jsonl"
    with sft_path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    payload.update({"snapshot": str(target), "sft_sheet": str(sft_path),
                    "library_total": index.get("total", 0),
                    "by_origin": index.get("by_origin", {})})
    status_path().write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gather finished builds into the library")
    parser.add_argument("--monthly", action="store_true",
                        help="ingest and cut this month's sheets")
    parser.add_argument("--force", action="store_true",
                        help="run even if the last harvest was under 28 days ago")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be added, write nothing")
    parser.add_argument("--scan", action="store_true",
                        help="list the runs on disk")
    parser.add_argument("--status", action="store_true",
                        help="when the last harvest ran and what it kept")
    args = parser.parse_args(argv)
    if args.scan:
        print(json.dumps(scan(), indent=2))
        return 0
    if args.status:
        print(json.dumps(status(), indent=2))
        return 0
    result = run(dry_run=args.dry_run, force=args.force)
    printable = {k: v for k, v in result.items() if k not in ("tasks", "dirs")}
    print(json.dumps(printable, indent=2))
    return 0 if result.get("state") in ("done", "dry-run", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
