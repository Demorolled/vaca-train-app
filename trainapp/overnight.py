"""overnight — the unattended loop around `functionprobe`.

One round is one pass over the verified file sets: ask for a function, splice it
into the real file, build and run the whole set, keep the row whether it passed
or not. The loop repeats rounds until its hour budget is spent (or `--rounds` is
reached), and it is built to be left alone:

* every attempt is appended to `samples.jsonl` / `failures.jsonl` the moment it
  finishes, so a crash or a kill loses at most the attempt in flight;
* `data/overnight.status.json` is rewritten after every attempt — round, counts,
  pass rate, ETA, last task — so progress can be read by anything, including a
  person who is not watching;
* `data/overnight.stop` stops it between attempts and keeps the partial round;
* a model error is retried, then skipped; several in a row end the run instead
  of burning the night on a dead endpoint;
* a restart resumes the round it was in and skips the sets already attempted.

On exit `export/` holds the rows the night produced: SFT rows (passes only) and
preference pairs (a passing reply against a failing one for the same prompt).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config, functionprobe, repair

STATUS_FILE = "overnight.status.json"
STOP_FILE = "overnight.stop"
LOG_FILE = "overnight.log"
ATTEMPT_FILES = ("samples.jsonl", "failures.jsonl", "errors.jsonl", "skipped.jsonl")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def status_path() -> Path:
    return config.data_dir() / STATUS_FILE


def stop_path() -> Path:
    return config.data_dir() / STOP_FILE


def output_root() -> Path:
    path = config.data_dir() / "overnight"
    path.mkdir(parents=True, exist_ok=True)
    return path


def publish(**fields) -> dict:
    """Merge a status update into `overnight.status.json`."""
    path = status_path()
    current: dict = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
    current.update(fields)
    path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return current


def stop_requested() -> bool:
    return stop_path().exists()


def running(status: dict | None = None) -> bool:
    """True when the status file names a process that is still alive."""
    status = status if status is not None else read_status()
    if status.get("state") != "running":
        return False
    pid = status.get("pid")
    if not isinstance(pid, int):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_status() -> dict:
    path = status_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def request_stop() -> Path:
    """Create the stop file; a running loop ends between two attempts."""
    path = stop_path()
    path.write_text(now() + "\n", encoding="utf-8")
    return path


def clear_stop() -> None:
    stop_path().unlink(missing_ok=True)


def round_dirs(root: Path) -> list[Path]:
    """The night's round directories; a root that does not exist yet has none."""
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir())


def seen(root: Path, round_no: int) -> set[str]:
    """Task ids already attempted in this round, across restarts of this run."""
    done: set[str] = set()
    for directory in round_dirs(root):
        for name in ATTEMPT_FILES:
            path = directory / name
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("round") == round_no:
                    done.add(row.get("key") or row.get("task_id") or "")
    return done


def records(root: Path) -> list[dict]:
    """Every attempt in this output root, in order."""
    rows: list[dict] = []
    for directory in round_dirs(root):
        for name in ("samples.jsonl", "failures.jsonl"):
            path = directory / name
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def rotated(tasks: list[dict], round_no: int) -> list[dict]:
    """Each round starts where the last one ended, so a short night still varies."""
    if not tasks:
        return []
    cut = (max(1, round_no) - 1) % len(tasks)
    return tasks[cut:] + tasks[:cut]


def coverage(root: Path | None = None) -> dict[str, dict]:
    """What the night has already shown for each set: attempts, and any that matched."""
    root = Path(root) if root is not None else output_root()
    out: dict[str, dict] = {}
    for row in records(root):
        task_id = row.get("task_id")
        if not task_id:
            continue
        slot = out.setdefault(task_id, {"attempts": 0, "match": 0})
        slot["attempts"] += 1
        slot["match"] += int(bool(row.get("match")))
    return out


def cold_first(tasks: list[dict], root: Path | None = None) -> list[dict]:
    """Sets no night has measured first, then sets that have never passed.

    A short night only reaches a prefix of the pool, and `rotated(pool, 1)` is
    the identity, so a loop that runs one round per cycle re-probed the same
    opening sets every time. The rest of the library was unreachable: it could
    never contribute a row, and a new family could never enter the hold-out.
    Ordering by coverage spends each hour on what is still unmeasured.
    """
    seen = coverage(root)

    def rank(task: dict) -> int:
        row = seen.get(task.get("id", ""))
        if not row:
            return 0
        return 1 if not row["match"] else 2

    return sorted(tasks, key=rank)


def export(root: Path) -> dict:
    """Write the night's rows in the trainer's two shapes."""
    out = root / "export"
    out.mkdir(parents=True, exist_ok=True)
    rows = records(root)
    sft = functionprobe.sft_rows(rows)
    pairs = functionprobe.pair_rows(rows)
    for name, data in (("sft.jsonl", sft), ("pairs.jsonl", pairs)):
        (out / name).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in data),
            encoding="utf-8")
    summary = {"records": len(rows), "sft_rows": len(sft), "pair_rows": len(pairs),
               "exported_at": now()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                      encoding="utf-8")
    return summary


def load_export(root: Path | None = None) -> dict:
    """The rows a finished night exported, in the trainer's two shapes.

    Read by `trainloop.prepare_data`, so a night's verified functions join the
    same hash split as every other proof-gated row. Missing files are normal: a
    night that was never run exports nothing and the trainer just sees less.
    """
    directory = (Path(root) if root is not None else output_root()) / "export"
    out: dict = {"sft": [], "pairs": [], "summary": {}}
    # `nearmiss.jsonl` is written by `trainapp.nearmiss`: same pair shape, but
    # both halves are verified answers on a prompt the model already got right.
    for name, key in (("sft.jsonl", "sft"), ("pairs.jsonl", "pairs"),
                      ("nearmiss.jsonl", "pairs")):
        path = directory / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if key == "sft":
                if not row.get("instruction") or not (row.get("output") or "").strip():
                    continue
            elif not (row.get("prompt") and (row.get("chosen") or "").strip()
                      and (row.get("rejected") or "").strip()):
                continue
            out[key].append(row)
    summary_path = directory / "summary.json"
    if summary_path.exists():
        try:
            out["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            out["summary"] = {}
    return out


def _attempt(task: dict, client, reference: tuple[bool, str] | None,
             timeout_s: float, retries: int, log, fn: dict | None = None) -> dict:
    """One row, retrying the model without failing the round."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            ref_ok, ref_text = reference if reference else (None, None)
            return functionprobe.probe(task, client, timeout_s=timeout_s,
                                       reference=ref_text, reference_ok=ref_ok,
                                       fn=fn)
        except Exception as err:  # a dead model is a skip, not the end of the night
            last = err
            log.write(f"{now()} {task['id']} attempt {attempt + 1} failed: "
                      f"{type(err).__name__}: {err}\n")
            log.flush()
            if attempt < retries:
                time.sleep(5)
    raise last  # type: ignore[misc]


def classify(tasks: list[dict], timeout_s: float = 25,
             reference: dict[str, tuple[bool, str]] | None = None
             ) -> tuple[dict[str, tuple[bool, str]], set[str]]:
    """Run each set untouched: keep the id only when its behaviour is observable.

    A set whose stdout is empty (TypeScript typechecks rather than runs, and some
    scripts print nothing) can only prove "it compiles", which is the lesson
    that made an earlier round format-perfect and useless. A set whose own run
    fails cannot be judged at all. Both are dropped before any model call.
    """
    reference = dict(reference or {})
    judgeable: set[str] = set()
    for task in tasks:
        target = functionprobe.target_of(task)
        if target is None:
            continue
        if task["id"] not in reference:
            base = functionprobe.run_set(task, target["content"], timeout_s)
            reference[task["id"]] = (base.ok,
                                     functionprobe.collapse(base.stdout))
        ok, stdout = reference[task["id"]]
        if ok and stdout:
            judgeable.add(task["id"])
    return reference, judgeable


def run(hours: float = 8.0, rounds: int = 1, limit: int = 0, offset: int = 0,
        root: Path | None = None, client=None, timeout_s: float = 25,
        tasks: list[dict] | None = None, resume: bool = True,
        max_errors: int = 5, retries: int = 1, do_export: bool = True,
        judgeable_only: bool = True, samples: int = 1, all_functions: bool = False,
        max_functions: int = 0) -> dict:
    root = Path(root) if root is not None else output_root()
    root.mkdir(parents=True, exist_ok=True)
    log_path = root / LOG_FILE
    client = client or repair.OllamaClient()
    pool = tasks if tasks is not None else functionprobe.candidates()
    if offset:
        pool = pool[offset:]
    deadline = time.monotonic() + hours * 3600 if hours > 0 else float("inf")
    started = time.monotonic()
    clear_stop()
    # A new run must not inherit the last run's finish time, export or counts.
    publish(state="running", started_at=now(), updated_at=now(), error="",
            root=str(root), hours=hours, total=len(pool), finished_at="",
            export=None, seconds=0, attempts=0, compile=0, match=0, errors=0,
            no_function=0, unjudgeable=0, round=1, done=0, eta_s=None,
            last="", reason="",
            stage="probe", pid=os.getpid())

    totals = {"attempts": 0, "compile": 0, "match": 0, "errors": 0,
              "no_function": 0, "unjudgeable": 0}
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n{now()} overnight start: {len(pool)} set(s), "
                  f"{hours}h, {rounds} round(s), root={root}\n")
        log.flush()
        reference: dict[str, tuple[bool, str]] = {}
        for round_no in range(1, max(1, rounds) + 1):
            # The slice is fixed before resume filtering: a later round must ask
            # the same sets again, because that is what makes a preference pair.
            queue = rotated(pool, round_no)
            if limit:
                queue = queue[:limit]
            done = seen(root, round_no) if resume else set()
            if judgeable_only and queue:
                reference, ok_ids = classify(queue, timeout_s, reference)
                dropped = [t for t in queue if t["id"] not in ok_ids]
                totals["unjudgeable"] += len(dropped)
                if dropped:
                    log.write(f"{now()} round {round_no}: dropping "
                              f"{len(dropped)} set(s) whose behaviour cannot be "
                              f"observed\n")
                queue = [t for t in queue if t["id"] in ok_ids]
                publish(unjudgeable=totals["unjudgeable"], updated_at=now())
            directory = root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            suffix = 1
            while directory.exists():
                directory = directory.with_name(
                    directory.name.split("-r")[0] + f"-r{suffix}")
                suffix += 1
            directory.mkdir(parents=True, exist_ok=True)
            wins = (directory / "samples.jsonl").open("a", encoding="utf-8")
            failures = (directory / "failures.jsonl").open("a", encoding="utf-8")
            errors = (directory / "errors.jsonl").open("a", encoding="utf-8")
            skipped = (directory / "skipped.jsonl").open("a", encoding="utf-8")

            # A set is not a prompt: every function in the target is a separate
            # ask, and each ask can be sampled more than once. One set therefore
            # contributes several prompts and several rows.
            items: list[tuple[dict, dict, str, int]] = []
            skipped_done = 0
            for task in queue:
                fns = functionprobe.probe_functions(
                    task, 1 if not all_functions else max_functions,
                    min_lines=1 if not all_functions else 4)
                if not fns:
                    totals["no_function"] += 1
                    skipped.write(json.dumps({"task_id": task["id"], "key": task["id"],
                                              "round": round_no, "reason": "no function",
                                              "at": now()}) + "\n")
                    continue
                slots = [task["id"] if not all_functions else f"{task['id']}#{i}"
                         for i in range(len(fns))]
                if all(slot in done for slot in slots):
                    skipped_done += 1
                    continue
                for i, fn in enumerate(fns):
                    if slots[i] not in done:
                        items.append((task, fn, slots[i], i))
            if not items:
                for handle in (wins, failures, errors, skipped):
                    handle.close()
                log.write(f"{now()} round {round_no}: nothing left to probe\n")
                continue
            log.write(f"{now()} round {round_no}: {len(items)} prompt(s) from "
                      f"{len({i[0]['id'] for i in items})} set(s), "
                      f"{skipped_done} already attempted, samples={max(1, samples)} "
                      f"-> {directory}\n")
            log.flush()
            publish(round=round_no, stage="probe", out=str(directory),
                    done=0, total=len(items), samples=max(1, samples),
                    prompts=len(items), eta_s=None, last="")
            round_started = time.monotonic()
            streak = 0
            for index, (task, fn, slot, fn_index) in enumerate(items, 1):
                if stop_requested():
                    log.write(f"{now()} stop file found; ending after {index - 1}\n")
                    publish(state="stopped", reason="stop file", updated_at=now())
                    break
                if time.monotonic() > deadline:
                    log.write(f"{now()} hour budget spent; ending round\n")
                    publish(state="done", stage="deadline", updated_at=now())
                    break
                if task["id"] not in reference:
                    target = functionprobe.target_of(task)
                    if target is None:
                        totals["no_function"] += 1
                        continue
                    base = functionprobe.run_set(task, target["content"], timeout_s)
                    reference[task["id"]] = (base.ok,
                                             functionprobe.collapse(base.stdout))
                matched = compiled = False
                gave_up = False
                for sample in range(max(1, samples)):
                    t0 = time.monotonic()
                    try:
                        row = _attempt(task, client, reference[task["id"]],
                                       timeout_s, retries, log, fn=fn)
                    except Exception as err:
                        streak += 1
                        totals["errors"] += 1
                        errors.write(json.dumps({"task_id": task["id"], "key": slot,
                                                 "round": round_no,
                                                 "error": f"{type(err).__name__}: {err}",
                                                 "at": now()}) + "\n")
                        errors.flush()
                        log.write(f"{now()} giving up on {slot} after retries: "
                                  f"{streak} in a row\n")
                        if streak >= max_errors:
                            publish(state="failed", error=str(err), updated_at=now(),
                                    reason=f"{streak} model errors in a row")
                            gave_up = True
                            break
                        continue
                    streak = 0
                    row.update({"round": round_no, "out": str(directory),
                                "key": slot, "function_index": fn_index,
                                "sample": sample,
                                "seconds": round(time.monotonic() - t0, 1)})
                    if row.get("skipped"):
                        totals["no_function"] += 1
                        skipped.write(json.dumps(row, ensure_ascii=False) + "\n")
                        skipped.flush()
                        continue
                    totals["attempts"] += 1
                    totals["compile"] += int(bool(row.get("compile")))
                    totals["match"] += int(bool(row.get("match")))
                    matched = matched or bool(row.get("match"))
                    compiled = compiled or bool(row.get("compile"))
                    handle = wins if row.get("match") else failures
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    handle.flush()
                if gave_up:
                    break
                elapsed = time.monotonic() - round_started
                left = len(items) - index
                publish(done=index, attempts=totals["attempts"],
                        compile=totals["compile"], match=totals["match"],
                        no_function=totals["no_function"], errors=totals["errors"],
                        eta_s=round(elapsed / index * left) if index else None,
                        last=slot, updated_at=now())
                log.write(f"{now()} [{index}/{len(items)}] "
                          f"{'MATCH' if matched else ('build' if compiled else 'fail ')} "
                          f"{task['language']:11s} fn={fn['lines']:3d}L "
                          f"{slot.split('/')[-1][:44]}\n")
                log.flush()
            for handle in (wins, failures, errors, skipped):
                handle.close()
            if stop_requested() or time.monotonic() > deadline:
                break

        summary = {**totals, "seconds": round(time.monotonic() - started),
                   "root": str(root), "finished_at": now()}
        if do_export and totals["attempts"]:
            summary["export"] = export(root)
        state = publish()
        if state.get("state") in ("running", None):
            publish(state="done", stage="rounds-exhausted", updated_at=now(), **summary)
        else:
            publish(updated_at=now(),
                    **{k: v for k, v in summary.items() if k != "root"})
        log.write(f"{now()} overnight end: {json.dumps(summary)}\n")
        log.flush()
    return publish()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Unattended function-level probe: generate, verify, keep.")
    parser.add_argument("--hours", type=float, default=8.0,
                        help="wall-clock budget; 0 means no limit")
    parser.add_argument("--rounds", type=int, default=1,
                        help="passes over the set; later passes make pairs")
    parser.add_argument("--limit", type=int, default=0,
                        help="sets per round (0 = all)")
    parser.add_argument("--offset", type=int, default=0,
                        help="start this many sets into the pool (sharding)")
    parser.add_argument("--model", default="", help="overrides config llm.model")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--temperature", type=float, default=0.2,
                        help="raise it (0.8) when later rounds should make pairs")
    parser.add_argument("--samples", type=int, default=1,
                        help="attempts per function (best-of-n)")
    parser.add_argument("--all-functions", action="store_true",
                        help="probe every function in the target, not just the largest")
    parser.add_argument("--max-functions", type=int, default=0,
                        help="cap functions per target when --all-functions")
    parser.add_argument("--out", default="", help="output root (default data/overnight)")
    parser.add_argument("--no-resume", action="store_true",
                        help="re-attempt sets this run already did")
    parser.add_argument("--no-export", action="store_true")
    parser.add_argument("--include-unjudgeable", action="store_true",
                        help="also probe sets whose stdout cannot be observed")
    parser.add_argument("--train", type=int, default=0, metavar="ROUNDS",
                        help="after exporting, run trainloop for N rounds")
    parser.add_argument("--stop", action="store_true",
                        help="create the stop file for a running loop")
    parser.add_argument("--status", action="store_true", help="print the status file")
    args = parser.parse_args(argv)

    if args.stop:
        print(request_stop())
        return 0
    if args.status:
        status = read_status()
        if not status:
            print("no status yet")
            return 0
        if status.get("state") == "running" and not running(status):
            status["state"] = "stale (process is gone)"
        print(json.dumps(status, indent=2))
        return 0

    client = repair.OllamaClient(model=args.model or None,
                                 temperature=args.temperature)
    result = run(hours=args.hours, rounds=args.rounds, limit=args.limit,
                 offset=args.offset,
                 root=Path(args.out) if args.out else None, client=client,
                 timeout_s=args.timeout, resume=not args.no_resume,
                 do_export=not args.no_export,
                 judgeable_only=not args.include_unjudgeable,
                 samples=args.samples, all_functions=args.all_functions,
                 max_functions=args.max_functions)
    if args.train and result.get("export"):
        publish(stage="train", training={"rounds": args.train, "started_at": now()})
        done = subprocess.run(
            [sys.executable, "-m", "trainapp.trainloop", "--rounds", str(args.train)],
            cwd=str(config.APP_ROOT))
        result["train_exit"] = done.returncode
        publish(stage="train-done", training={"rounds": args.train,
                                              "exit": done.returncode,
                                              "finished_at": now()})
    print(json.dumps(result, indent=2))
    if result.get("train_exit") not in (None, 0):
        return 1
    return 0 if result.get("state") in ("done", "stopped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
