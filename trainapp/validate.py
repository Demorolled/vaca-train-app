"""validate — prove library code with the real toolchain, language by language.

Statuses are deliberately narrow and honest:

  verified           compiled (and ran, for programs) with exit 0
  component          compiles, but the file has no entry point, so it is a
                     snippet rather than a program — never a seed
  failed             the toolchain rejected it, or it exited non-zero
  timeout            it compiled but never finished (interactive/server snippet)
  toolchain_missing  this box cannot check that language — install hint included
  unsupported        no execution schema for the declared language
  unvalidated        not checked yet

TypeScript chunks are checked as one `tsc --noEmit` batch: 904 separate tsc
processes would take an hour, one batch takes seconds and still attributes
every diagnostic to its own file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from . import adherence, config, execution, library

STATUS_FILE = "validation.status.json"
TS_ERROR_RE = re.compile(r"^(?P<file>.+?)\((\d+),(\d+)\): error (?P<code>TS\d+): (?P<msg>.+)$")
LOCK = threading.Lock()
PROGRESS: dict = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _record(task: dict, status: str, **extra) -> dict:
    return {
        "id": task["id"],
        "language": task["language"],
        "status": status,
        "checked_at": _now(),
        "duration_ms": extra.pop("duration_ms", 0),
        "command": extra.pop("command", ""),
        "exit_code": extra.pop("exit_code", None),
        "stderr": extra.pop("stderr", "")[-2000:],
        "stdout": extra.pop("stdout", "")[-1000:],
        "error": extra.pop("error", ""),
        **extra,
    }


def _extension(language: str) -> str:
    spec = execution.TOOLCHAINS.get(language)
    return spec.extensions[0] if spec else ".txt"


def _validate_file_set(task: dict, timeout_s: float) -> dict:
    """Prove a whole file set, not one file: build it with its siblings present.

    The adherence score is recorded alongside the build verdict because they
    answer different questions — a set can compile while a module imports a
    sibling nobody wrote (that sibling is simply absent from the set and tsc
    never sees it), and it can be perfectly adherent while the toolchain still
    rejects it.
    """
    files = task.get("files") or []
    language = task.get("language", "")
    report = adherence.score_files(files, language)
    extra = {"adherence": report["score"],
             "adherence_failures": report["failures"],
             "file_count": report["file_count"],
             "target": task.get("target", "")}
    # The target is normally a module, not the program: launching it would run
    # a file that only defines things. Only an entry-named target is launched.
    target = task.get("target", "")
    try:
        result = execution.run_files(
            files, language,
            entry=target if execution.is_entry_name(target) else "",
            timeout_s=timeout_s)
    except OSError as err:
        return _record(task, "failed", error=f"set runner crashed: {err}", **extra)
    if result.ok:
        return _record(task, "verified", duration_ms=result.duration_ms,
                       command=result.command, exit_code=result.exit_code,
                       stdout=result.stdout, stderr=result.stderr, **extra)
    text = result.error or ""
    extra.update(duration_ms=result.duration_ms, command=result.command,
                 exit_code=result.exit_code, stdout=result.stdout,
                 stderr=result.stderr, error=text)
    if "toolchain missing" in text:
        return _record(task, "toolchain_missing", **extra)
    if text == "timed out":
        return _record(task, "timeout", **extra)
    if text.startswith(("no multi-file build", "cargo project not supported")):
        return _record(task, "unsupported", **extra)
    return _record(task, "failed", **extra)


def validate_task(task: dict, timeout_s: float = 20) -> dict:
    language = task.get("language", "")
    if library.is_multi_file(task):
        return _validate_file_set(task, timeout_s)
    if language not in execution.TOOLCHAINS:
        return _record(task, "unsupported", error=f"no schema for {language!r}")
    if language == "typescript":
        return _validate_typescript_single(task, timeout_s)

    is_program = execution.program_entry_point(language, task["code"])
    with tempfile.TemporaryDirectory(prefix="vaca-val-") as tmp:
        # Java launches by class name, and a public class must live in a file of
        # that name — `snippet.java` rejected every one of them.
        stem = execution.source_stem(language, task["code"])
        path = Path(tmp) / f"{stem}{_extension(language)}"
        path.write_text(task["code"], encoding="utf-8")
        result = execution.run_node(path, language, timeout_s=timeout_s,
                                    compile_only=not is_program)
    if result.ok:
        return _record(task, "verified" if is_program else "component",
                       duration_ms=result.duration_ms,
                       command=result.command, exit_code=result.exit_code,
                       stdout=result.stdout, stderr=result.stderr,
                       **({} if is_program else
                          {"note": "compiles; no entry point, so it cannot run as a program"}))
    if "toolchain missing" in (result.error or ""):
        return _record(task, "toolchain_missing", error=result.error, command=result.command)
    if result.error == "timed out":
        return _record(task, "timeout", duration_ms=result.duration_ms,
                       command=result.command, error=result.error, stderr=result.stderr)
    return _record(task, "failed", duration_ms=result.duration_ms,
                   command=result.command, exit_code=result.exit_code,
                   stdout=result.stdout, stderr=result.stderr, error=result.error)


def tsc_path() -> str:
    root = library.vaca_root()
    candidate = root / "node_modules" / ".bin" / "tsc"
    return str(candidate) if candidate.exists() else (shutil.which("tsc") or "")


def _ts_source(task: dict) -> str:
    """A code-bible chunk is `iface` + `code`: the body references the props
    interface declared separately, so compiling `code` alone is never valid."""
    iface = (task.get("iface") or "").strip()
    return (iface + "\n\n" if iface else "") + task["code"]


def _validate_typescript_single(task: dict, timeout_s: float) -> dict:
    """A single TS file when a batch is not in play (bible chunks use the batch)."""
    tsc = tsc_path()
    if not tsc:
        return _record(task, "toolchain_missing",
                       error="tsc not found (VACA node_modules/.bin/tsc)")
    root = library.vaca_root()
    workdir = Path(tempfile.mkdtemp(prefix=".vaca-ts-", dir=str(root)))
    try:
        path = workdir / "snippet.tsx"
        path.write_text(_ts_source(task), encoding="utf-8")
        argv = [tsc, "--noEmit", "--jsx", "react-jsx", "--target", "ES2022",
                "--module", "ESNext", "--moduleResolution", "bundler",
                "--skipLibCheck", "--esModuleInterop", str(path)]
        started = time.monotonic()
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s,
                                  stdin=subprocess.DEVNULL, cwd=str(root))
        except subprocess.TimeoutExpired:
            return _record(task, "timeout", error="tsc timed out")
        duration = int((time.monotonic() - started) * 1000)
        status = "verified" if done.returncode == 0 else "failed"
        return _record(task, status, duration_ms=duration,
                       command=execution.display_command(argv),
                       exit_code=done.returncode, stderr=done.stdout or done.stderr)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def validate_typescript_batch(tasks: list[dict], timeout_s: float = 900) -> dict[str, dict]:
    """One tsc invocation over every chunk; diagnostics attributed per file."""
    tsc = tsc_path()
    if not tsc:
        return {t["id"]: _record(t, "toolchain_missing",
                                 error="tsc not found (VACA node_modules/.bin/tsc)")
                for t in tasks}
    root = library.vaca_root()
    workdir = Path(tempfile.mkdtemp(prefix=".vaca-ts-batch-", dir=str(root)))
    results: dict[str, dict] = {}
    try:
        paths: dict[str, Path] = {}
        for index, task in enumerate(tasks):
            path = workdir / f"chunk_{index:04d}.tsx"
            path.write_text(_ts_source(task), encoding="utf-8")
            paths[path.name] = task  # tsc prints paths relative to its cwd
        argv = [tsc, "--noEmit", "--jsx", "react-jsx", "--target", "ES2022",
                "--module", "ESNext", "--moduleResolution", "bundler",
                "--skipLibCheck", "--esModuleInterop", "--pretty", "false",
                *[str(workdir / name) for name in paths]]
        started = time.monotonic()
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s,
                                  stdin=subprocess.DEVNULL, cwd=str(root))
            stdout, returncode = done.stdout or "", done.returncode
        except subprocess.TimeoutExpired:
            return {t["id"]: _record(t, "timeout", error="tsc batch timed out") for t in tasks}
        duration = int((time.monotonic() - started) * 1000)
        per_file: dict[str, list[str]] = {}
        for line in stdout.splitlines():
            match = TS_ERROR_RE.match(line.strip())
            if match:
                per_file.setdefault(Path(match.group("file")).name, []).append(
                    f"{match.group('code')}: {match.group('msg')}")
        # A batch exits non-zero if ANY file fails. A file is clean only when
        # tsc attributed no diagnostic to it — otherwise one bad chunk marks
        # all 904 failed, which is exactly the bug this replaces.
        attributed = bool(per_file)
        for name, task in paths.items():
            errors = per_file.get(name, [])
            if not errors and (returncode == 0 or attributed):
                results[task["id"]] = _record(task, "verified", duration_ms=duration,
                                              command="tsc --noEmit (batch)",
                                              exit_code=0)
            else:
                joined = "\n".join(errors[:8]) or stdout.strip()[:1500]
                results[task["id"]] = _record(task, "failed", duration_ms=duration,
                                              command="tsc --noEmit (batch)",
                                              exit_code=returncode, stderr=joined)
        return results
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _write_status(update: dict) -> None:
    PROGRESS.update(update)
    path = library.library_dir() / STATUS_FILE
    path.write_text(json.dumps(PROGRESS, indent=2) + "\n", encoding="utf-8")


def status() -> dict:
    path = library.library_dir() / STATUS_FILE
    if not path.exists():
        return {"state": "idle"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"state": "idle"}


def run(tasks: list[dict] | None = None, jobs: int = 4, timeout_s: float = 20,
        skip_typescript: bool = False) -> dict:
    """Validate a task list; overwrite validation.jsonl with the full record set."""
    tasks = tasks if tasks is not None else library.load_tasks()
    if not tasks:
        library.build()
        tasks = library.load_tasks()
    # A multi-file task is one set, so it can never join the single-file tsc
    # batch (that batch writes one snippet per file and would silently score the
    # target without its siblings). Sets go through the threaded path instead.
    sets = [t for t in tasks if library.is_multi_file(t)]
    single = [t for t in tasks if not library.is_multi_file(t)]
    # The tsc batch compiles many files as ONE program, which is right for the
    # code-bible chunks (they are components, checked for compiling at all) and
    # wrong for runnable TypeScript programs: 100 independent programs batched
    # together collide on `main`, `TEXT`, `VALUES` and fail as duplicates. Those
    # go through the single-file path instead.
    ts_tasks = [t for t in single if t["language"] == "typescript" and not t.get("runnable")]
    ts_programs = [t for t in single if t["language"] == "typescript" and t.get("runnable")]
    other = [t for t in single if t["language"] != "typescript"] + sets + ts_programs

    _write_status({"state": "running", "total": len(tasks), "done": 0,
                   "verified": 0, "failed": 0, "missing": 0, "timeout": 0,
                   "started_at": _now(), "finished_at": "", "current": ""})
    results: dict[str, dict] = {}
    started = time.monotonic()
    counters = {"done": 0, "verified": 0, "failed": 0, "missing": 0, "timeout": 0}

    def note(record: dict) -> None:
        results[record["id"]] = record
        counters["done"] += 1
        key = {"verified": "verified", "failed": "failed",
               "toolchain_missing": "missing", "timeout": "timeout"}.get(record["status"])
        if key:
            counters[key] += 1
        with LOCK:
            _write_status({**counters, "current": record["id"],
                           "elapsed_s": round(time.monotonic() - started, 1)})

    if ts_tasks and not skip_typescript:
        with LOCK:
            _write_status({"current": f"tsc batch ({len(ts_tasks)} chunks)"})
        batch = validate_typescript_batch(ts_tasks)
        # Some chunks carry an `iface` that is documentation rather than valid
        # TypeScript (method signatures in an object literal). Those are given
        # a second chance with the code alone; a component that genuinely needs
        # its props interface still fails, and is reported as such.
        retry = [{**task, "iface": ""} for task in ts_tasks
                 if batch[task["id"]]["status"] == "failed" and task.get("iface")]
        if retry:
            with LOCK:
                _write_status({"current": f"tsc retry without iface ({len(retry)} chunks)"})
            second = validate_typescript_batch(retry)
            for task in retry:
                record = second[task["id"]]
                if record["status"] == "verified":
                    record["note"] = "verified code-only: the chunk's iface is not compilable TypeScript"
                    batch[task["id"]] = record
        for record in batch.values():
            note(record)

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {pool.submit(validate_task, task, timeout_s): task for task in other}
        for future in as_completed(futures):
            try:
                note(future.result())
            except Exception as err:  # one bad snippet must not kill the run
                task = futures[future]
                note(_record(task, "failed", error=f"validator crashed: {err}"))

    # A filtered run (one language, a limit) must not erase the records of the
    # tasks it did not touch.
    merged = {**library.load_validation(), **results}
    ordered = [merged[key] for key in sorted(merged)]
    with library.validation_path().open("w", encoding="utf-8") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = {
        "state": "done", "total": len(tasks), "done": len(ordered),
        "verified": counters["verified"], "failed": counters["failed"],
        "missing": counters["missing"], "timeout": counters["timeout"],
        "elapsed_s": round(time.monotonic() - started, 1),
        "finished_at": _now(),
        "by_language": {},
    }
    for record in ordered:
        entry = summary["by_language"].setdefault(
            record["language"], {"verified": 0, "failed": 0, "missing": 0, "timeout": 0})
        key = {"verified": "verified", "failed": "failed",
               "toolchain_missing": "missing", "timeout": "timeout"}.get(record["status"])
        if key:
            entry[key] += 1
    _write_status(summary)
    return summary


def start_background(languages: set[str] | None = None, limit: int = 0, jobs: int = 4,
                     timeout_s: float = 20, skip_typescript: bool = False) -> dict:
    """Validate in a thread; the UI polls `status()` for progress."""
    if status().get("state") == "running":
        return {**status(), "error": "a validation run is already in progress"}
    if not library.tasks_path().exists():
        library.build()
    tasks = library.load_tasks()
    if languages:
        tasks = [t for t in tasks if t["language"] in languages]
    if limit:
        tasks = tasks[:limit]
    _write_status({"state": "running", "total": len(tasks), "done": 0,
                   "started_at": _now(), "current": "starting"})
    threading.Thread(target=run, args=(tasks, jobs, timeout_s, skip_typescript),
                     daemon=True).start()
    return {"state": "running", "total": len(tasks)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the VACA library against real toolchains")
    parser.add_argument("--build", action="store_true", help="re-ingest tasks first")
    parser.add_argument("--language", default="", help="comma-separated language filter")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--no-typescript", action="store_true")
    args = parser.parse_args(argv)

    if args.build or not library.tasks_path().exists():
        print("ingest:", json.dumps(library.build()))
    tasks = library.load_tasks()
    if args.language:
        wanted = {x.strip().lower() for x in args.language.split(",") if x.strip()}
        tasks = [t for t in tasks if t["language"] in wanted]
    if args.limit:
        tasks = tasks[: args.limit]
    summary = run(tasks, jobs=args.jobs, timeout_s=args.timeout,
                  skip_typescript=args.no_typescript)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
