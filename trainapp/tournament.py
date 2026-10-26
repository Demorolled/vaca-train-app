"""tournament — small builds in every style, measured and judged.

For one confirmed library task, the coder model writes the same program in each
style (terse, idiomatic, functional, oop, defensive, readable, fast). Every
variant must pass the real toolchain and actually run. Then the larger judge
model compares builds against the confirmed reference and against each other,
with measured bytes and runtime in front of it.

What comes out is not an opinion: it is a verified winner per task, a
preference pair for every judged match, and a summary of which styles actually
produce smaller/faster builds.
"""
from __future__ import annotations

import json
import re
import statistics
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import capture, config, execution, judge, library, preferences, repair

STYLES: dict[str, str] = {
    "terse": "as few lines and bytes as possible while staying correct",
    "idiomatic": "the canonical, most natural way in this language",
    "functional": "pure functions and expressions, avoid mutable state",
    "oop": "a class or struct with methods that owns its state",
    "defensive": "validate inputs, handle every error path, never crash",
    "readable": "clear names and comments for a junior reader",
    "fast": "minimise runtime: no needless allocation, linear where possible",
}

SYSTEM = (
    "You write a single file that solves the given task. Reply with the "
    "complete file only — no markdown fence, no explanation."
)

JOB_LOCK = threading.RLock()
JOB: dict = {"state": "idle", "tasks": 0, "done": 0, "current": "",
             "started_at": "", "finished_at": "", "error": "", "summary": {},
             "run_dir": ""}
_THREAD: threading.Thread | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _status_file() -> Path:
    return config.data_dir() / "tournament.status.json"


def status() -> dict:
    """Live job state, or the last run's persisted summary after a restart."""
    with JOB_LOCK:
        snapshot = dict(JOB)
    if snapshot.get("state") == "idle":
        path = _status_file()
        if path.exists():
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
                # A run started from the CLI owns the file, not this process:
                # show it while the file is fresh so the UI does not claim idle
                # during an overnight run. A stale "running" is a dead process.
                fresh = time.time() - path.stat().st_mtime < 900
                if saved.get("state") in ("done", "failed") or \
                        (saved.get("state") == "running" and fresh):
                    snapshot = {**snapshot, **saved}
            except (OSError, json.JSONDecodeError):
                pass
    return snapshot


def _publish(**update) -> None:
    with JOB_LOCK:
        JOB.update(update)
        payload = dict(JOB)
    try:
        _status_file().write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _style_prompt(task: dict, style: str) -> str:
    return (
        f"TASK: {task.get('title','')}\n"
        f"WHAT IT MUST DO: {task.get('description','')}\n"
        f"LANGUAGE: {task.get('language','')}\n"
        f"REFERENCE IMPLEMENTATION (known working — match its behaviour, not its text):\n"
        f"```\n{task.get('code','')[:4000]}\n```\n\n"
        f"Write the same program in the **{style}** style: {STYLES.get(style, style)}.\n"
        "Standard library only. It must compile and run on its own."
    )


def _child_env() -> dict:
    return {**dict(), "PYTHONIOENCODING": "utf-8"}


def _target_of(task: dict) -> str:
    """The one file a set is asked to write, if the set names a real one."""
    target = task.get("target") or ""
    paths = {entry.get("path") for entry in task.get("files") or []}
    return target if target in paths else ""


def _target_code(task: dict, target: str) -> str:
    for entry in task.get("files") or []:
        if entry.get("path") == target:
            return entry.get("content") or ""
    return ""


def _scaffold_prompt(task: dict, style: str = "") -> str:
    """The file-in-context ask, in this tournament's style slot.

    A file set has no single program to restyle, so the unit written here is
    the target file with its siblings in view — the same ask `battery` scores
    and `scaffoldsft` trains, which is what makes a pair from it comparable
    with a library row. The style rides at the end of the Input half: the
    reply slot after `### Response` stays a clean file.
    """
    from . import battery  # battery imports this module; import at call time

    body = battery.scaffold_input(task)
    if style:
        body += (f"\n\nSTYLE: write this file in the **{style}** style: "
                 f"{STYLES.get(style, style)}.")
    return preferences.PROMPT_TEMPLATE.format(
        language=task.get("language", ""),
        title=(task.get("title") or "").strip(),
        task=body,
    )


def _run_scaffold(task: dict, code: str, timeout_s: float,
                  repeats: int = 1) -> dict:
    """Build and run the whole set with `code` in the target file."""
    from . import battery

    first = battery._run_set(task, code, timeout_s)
    runs = [first.get("runtime_ms", 0)]
    if first.get("valid") and repeats > 1:
        for _ in range(repeats - 1):
            again = battery._run_set(task, code, timeout_s)
            if again.get("valid"):
                runs.append(again.get("runtime_ms", 0))
    return {"valid": bool(first.get("valid")),
            "stdout": first.get("stdout", ""),
            "runtime_ms": int(statistics.median(runs)) if first.get("valid") else 0,
            "error": first.get("error", "")}


def _run_code(task: dict, code: str, timeout_s: float, repeats: int = 1) -> dict:
    """Compile + run one implementation, returning validity and median runtime."""
    language = task.get("language", "")
    spec = execution.TOOLCHAINS.get(language)
    if not spec:
        return {"valid": False, "error": f"no schema for {language!r}", "runtime_ms": 0}
    import tempfile

    with tempfile.TemporaryDirectory(prefix="vaca-tour-") as tmp:
        path = Path(tmp) / f"{execution.source_stem(language, code)}{spec.extensions[0]}"
        path.write_text(code, encoding="utf-8")
        runs = []
        first = execution.run_node(path, language, timeout_s=timeout_s)
        runs.append(first.duration_ms)
        if first.ok and repeats > 1:
            for _ in range(repeats - 1):
                again = execution.run_node(path, language, timeout_s=timeout_s)
                runs.append(again.duration_ms)
        return {
            "valid": first.ok,
            "runtime_ms": int(statistics.median(runs)) if first.ok else 0,
            "stdout": first.stdout,
            "stderr": first.stderr,
            "exit_code": first.exit_code,
            "command": first.command,
            "error": first.error,
        }


def _normalize_stdout(text: str) -> str:
    return " ".join((text or "").split())


def _variant(task: dict, style: str, code: str, result: dict, reference_stdout: str) -> dict:
    return {
        "task_id": task["id"],
        "language": task["language"],
        "style": style,
        "code": code,
        "bytes": len(code.encode("utf-8")),
        "lines": code.count("\n") + 1,
        "valid": bool(result.get("valid")),
        "runtime_ms": result.get("runtime_ms", 0),
        "stdout_match": _normalize_stdout(result.get("stdout", "")) == reference_stdout,
        "exit_code": result.get("exit_code"),
        "error": result.get("error", ""),
    }


def choose_tasks(tasks: list[dict], limit: int, languages: set[str] | None = None,
                 exclude: set[str] | None = None, sets: bool = False,
                 origin: str = "") -> list[dict]:
    """Confirmed seeds a run may restyle, optionally skipping ids it covered.

    Single-file programs are the default seed. `sets=True` takes confirmed
    file sets instead, which are restyled one target file at a time; a set
    without a real target has nothing to ask for and is skipped. `origin`
    narrows either kind to one source, so a round can be aimed at the builds
    a distiller just produced instead of the whole sheet.
    """
    confirmed = [t for t in tasks if t.get("runnable")
                 and t.get("language") in execution.TOOLCHAINS
                 and bool(library.is_multi_file(t)) == sets]
    if sets:
        confirmed = [t for t in confirmed if _target_of(t)]
    if origin:
        confirmed = [t for t in confirmed if (t.get("origin") or "") == origin]
    if languages:
        confirmed = [t for t in confirmed if t["language"] in languages]
    if exclude:
        confirmed = [t for t in confirmed if t["id"] not in exclude]
    confirmed.sort(key=lambda t: (t["language"], t["id"]))
    return confirmed[: max(0, limit)] if limit else confirmed


def run_task(task: dict, *, styles: list[str], run_timeout_s: float,
             repeats: int, coder=None, judge_fn=None,
             prompt_fn=None, runner=None) -> dict:
    """One task: 7 style variants -> validate -> judge -> winner + pairs.

    `prompt_fn` and `runner` are the two seams a file set needs: the ask is
    the target file with its siblings in view, and the grade is the whole set
    building and running, not one file on its own. Both default to the
    single-file behaviour, so a program task is unchanged by them.
    """
    if library.is_multi_file(task) and prompt_fn is None:
        return run_set_task(task, styles=styles, run_timeout_s=run_timeout_s,
                            repeats=repeats, coder=coder, judge_fn=judge_fn)
    coder = coder or repair.OllamaClient()
    judge_fn = judge_fn or judge.compare
    prompt_fn = prompt_fn or _style_prompt

    run = runner or (lambda t, code, count:
                     _run_code(t, code, run_timeout_s, repeats=count))

    reference = run(task, task["code"], 1)
    reference_stdout = _normalize_stdout(reference.get("stdout", ""))
    baseline = {
        "style": "reference", "code": task["code"],
        "bytes": len(task["code"].encode("utf-8")),
        "lines": task["code"].count("\n") + 1,
        "valid": bool(reference.get("valid")),
        "runtime_ms": reference.get("runtime_ms", 0),
        "readable": False,
    }

    variants: list[dict] = []
    for style in styles:
        try:
            raw = coder.complete(prompt_fn(task, style))
        except Exception as err:  # a coder failure skips one style, never the task
            variants.append({"task_id": task["id"], "language": task["language"],
                             "style": style, "code": "", "bytes": 0, "lines": 0,
                             "valid": False, "runtime_ms": 0, "stdout_match": False,
                             "error": f"coder failed: {err}"[:300]})
            continue
        code = repair.extract_code(raw)
        result = run(task, code, repeats)
        variants.append(_variant(task, style, code, result, reference_stdout))

    verdicts: list[dict] = []
    score = {v["style"]: 0.0 for v in variants if v["valid"]}
    for variant in [v for v in variants if v["valid"]]:
        decision = judge_fn(task, task["code"], baseline, variant)
        verdicts.append({
            "task_id": task["id"], "a_style": "reference", "b_style": variant["style"],
            "winner": decision.get("winner", ""), "reason": decision.get("reason", ""),
            "dimensions": decision.get("dimensions", {}), "source": decision.get("source", ""),
            "error": decision.get("error", ""), "at": _now(),
        })
        if decision.get("winner") == "B":
            score[variant["style"]] += 1.0
        elif decision.get("winner") == "tie":
            score[variant["style"]] += 0.5

    # Head-to-head between the two strongest valid styles: order, not just
    # "beat the reference", so the winner is the best build, not the first one.
    ranked = sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) >= 2:
        first_style, second_style = ranked[0][0], ranked[1][0]
        first = next(v for v in variants if v["style"] == first_style)
        second = next(v for v in variants if v["style"] == second_style)
        decision = judge_fn(task, task["code"], first, second)
        verdicts.append({
            "task_id": task["id"], "a_style": first_style, "b_style": second_style,
            "winner": decision.get("winner", ""), "reason": decision.get("reason", ""),
            "dimensions": decision.get("dimensions", {}), "source": decision.get("source", ""),
            "error": decision.get("error", ""), "at": _now(),
        })
        if decision.get("winner") == "A":
            score[first_style] += 1.0
        elif decision.get("winner") == "B":
            score[second_style] += 1.0
        else:
            score[first_style] += 0.5
            score[second_style] += 0.5

    valid = [v for v in variants if v["valid"]]
    win_style = max(score.items(), key=lambda kv: (kv[1], -next(
        v["bytes"] for v in variants if v["style"] == kv[0]))) [0] if score else ""
    winner = next((v for v in valid if v["style"] == win_style), None)
    if winner is None and valid:
        winner = min(valid, key=lambda v: (v["bytes"], v["runtime_ms"]))

    pairs = []
    for verdict in verdicts:
        if verdict["winner"] not in ("A", "B"):
            continue
        a = next((v for v in [baseline] + variants if v["style"] == verdict["a_style"]), None)
        b = next((v for v in variants if v["style"] == verdict["b_style"]), None)
        if not a or not b or not a.get("code") or not b.get("code"):
            continue
        chosen, rejected = (b, a) if verdict["winner"] == "B" else (a, b)
        pairs.append({
            "task_id": task["id"], "language": task["language"], "title": task["title"],
            "chosen_style": chosen["style"], "rejected_style": rejected["style"],
            "chosen": chosen["code"], "rejected": rejected["code"],
            "chosen_bytes": chosen["bytes"], "rejected_bytes": rejected["bytes"],
            "reason": verdict["reason"], "task": task["description"],
        })

    return {
        "task": {k: task[k] for k in ("id", "title", "language", "description")},
        "reference": baseline,
        "variants": variants,
        "verdicts": verdicts,
        "score": score,
        "winner": winner,
        "pairs": pairs,
    }


def run_set_task(task: dict, *, styles: list[str], run_timeout_s: float,
                 repeats: int, coder=None, judge_fn=None) -> dict:
    """A confirmed file set: the target file restyled, graded by the set.

    The siblings are in the prompt because that is the contract VACA's own
    builder works under — one file, written to fit what already exists. Every
    variant is judged only after the whole set has built and run, so a file
    that reads well but breaks the project loses on the toolchain.
    """
    target = _target_of(task)
    if not target:
        raise ValueError(f"{task.get('id', '?')} has no target file to restyle")
    reference_code = _target_code(task, target)
    outcome = run_task(
        {**task, "code": reference_code},
        styles=styles, run_timeout_s=run_timeout_s, repeats=repeats,
        coder=coder, judge_fn=judge_fn,
        prompt_fn=_scaffold_prompt,
        runner=lambda t, code, count: _run_scaffold(t, code, run_timeout_s, count))
    for pair in outcome["pairs"]:
        pair["kind"] = "scaffold"
        pair["target"] = target
        pair["prompt"] = _scaffold_prompt(task)
    if outcome.get("winner"):
        outcome["capture_row"] = _set_winner_row(task, outcome["winner"])
    return outcome


def _set_winner_row(task: dict, winner: dict) -> dict:
    """The winning target file as a scaffold-shaped training row."""
    from . import battery

    return {
        "instruction": battery.scaffold_instruction(task),
        "input": battery.scaffold_input(task),
        "output": winner["code"],
        "source": "tournament:winner",
        "meta": {"language": task["language"], "task_id": task["id"],
                 "target": task.get("target", ""), "style": winner["style"],
                 "bytes": winner["bytes"], "runtime_ms": winner["runtime_ms"],
                 "scaffold": True},
    }


def _winner_row(task: dict, winner: dict) -> dict:
    return {
        "instruction": (
            f"Write a {winner['style']} {task['language']} implementation of: "
            f"{task['title']}. It must compile and run on its own, standard "
            "library only. Reply with the complete file."
        ),
        "input": f"Task: {task.get('description','')}\nStyle: {winner['style']}",
        "output": winner["code"],
        "source": "tournament:winner",
        "meta": {"language": task["language"], "task_id": task["id"],
                 "style": winner["style"], "bytes": winner["bytes"],
                 "runtime_ms": winner["runtime_ms"]},
    }


def execute(max_tasks: int, styles: list[str], run_timeout_s: float = 20,
            repeats: int = 3, languages: set[str] | None = None,
            coder=None, judge_fn=None, exclude: set[str] | None = None,
            sets: bool = False, origin: str = "") -> dict:
    """Run a bounded tournament; writes a run directory plus a summary."""
    if not library.tasks_path().exists():
        library.build()
    confirmed_ids = {t["id"] for t in library.confirmed()}
    candidates = [t for t in library.load_tasks() if t["id"] in confirmed_ids]
    chosen = choose_tasks(candidates, max_tasks, languages, exclude,
                          sets=sets, origin=origin)
    if not chosen:
        _publish(state="failed", error="no confirmed runnable tasks — run library validation first",
                 finished_at=_now())
        return status()

    run_dir = config.data_dir() / "tournament" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    _publish(state="running", tasks=len(chosen), done=0, current="", error="",
             started_at=_now(), finished_at="", run_dir=str(run_dir), summary={})

    results: list[dict] = []
    pairs_path = run_dir / "pairs.jsonl"
    with pairs_path.open("w", encoding="utf-8") as pairs_handle, \
            (run_dir / "results.jsonl").open("w", encoding="utf-8") as results_handle:
        for index, task in enumerate(chosen, start=1):
            _publish(current=f"{task['language']}: {task['title']}")
            try:
                result = run_task(task, styles=styles, run_timeout_s=run_timeout_s,
                                  repeats=repeats, coder=coder, judge_fn=judge_fn)
            except Exception as err:
                result = {"task": {k: task.get(k, "") for k in ("id", "title", "language", "description")},
                          "error": f"{type(err).__name__}: {err}", "variants": [],
                          "verdicts": [], "pairs": [], "winner": None, "score": {}}
            results.append(result)
            results_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            for pair in result.get("pairs", []):
                pairs_handle.write(json.dumps(pair, ensure_ascii=False) + "\n")
            if result.get("winner"):
                capture.append_row(result.get("capture_row")
                                   or _winner_row(result["task"], result["winner"]))
            pairs_handle.flush()
            results_handle.flush()
            _publish(done=index)

    summary = summarize(results)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    _publish(state="done", finished_at=_now(), current="", summary=summary)
    return status()


def summarize(results: list[dict]) -> dict:
    style_wins: dict[str, int] = {}
    style_bytes: dict[str, list[int]] = {}
    style_runtime: dict[str, list[int]] = {}
    verified = 0
    total_variants = 0
    reference_bytes: list[int] = []
    winner_bytes: list[int] = []
    pairs = 0
    for result in results:
        pairs += len(result.get("pairs", []))
        for variant in result.get("variants", []):
            total_variants += 1
            if variant.get("valid"):
                verified += 1
            if variant.get("bytes"):
                style_bytes.setdefault(variant["style"], []).append(variant["bytes"])
            if variant.get("valid") and variant.get("runtime_ms"):
                style_runtime.setdefault(variant["style"], []).append(variant["runtime_ms"])
        winner = result.get("winner")
        if winner:
            style_wins[winner["style"]] = style_wins.get(winner["style"], 0) + 1
            winner_bytes.append(winner["bytes"])
        if result.get("reference", {}).get("bytes"):
            reference_bytes.append(result["reference"]["bytes"])
    return {
        "tasks": len(results),
        "variants": total_variants,
        "verified_variants": verified,
        "verified_rate": round(verified / total_variants, 3) if total_variants else 0,
        "style_wins": style_wins,
        "avg_variant_bytes": {s: round(sum(v) / len(v)) for s, v in style_bytes.items() if v},
        "avg_runtime_ms": {s: round(sum(v) / len(v)) for s, v in style_runtime.items() if v},
        "avg_reference_bytes": round(sum(reference_bytes) / len(reference_bytes)) if reference_bytes else 0,
        "avg_winner_bytes": round(sum(winner_bytes) / len(winner_bytes)) if winner_bytes else 0,
        "pairs": pairs,
        "finished_at": _now(),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run a style tournament over confirmed library tasks")
    parser.add_argument("--tasks", type=int, default=5)
    parser.add_argument("--styles", default="")
    parser.add_argument("--languages", default="", help="comma-separated filter")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--exclude-covered", action="store_true",
                        help="skip seeds that already have preference pairs")
    parser.add_argument("--sets", action="store_true",
                        help="restyle confirmed file sets instead of single files")
    parser.add_argument("--origin", default="",
                        help="only seeds from one origin (e.g. distiller-build)")
    args = parser.parse_args(argv)
    styles = [s.strip() for s in args.styles.split(",") if s.strip()] or list(STYLES)
    languages = {x.strip().lower() for x in args.languages.split(",") if x.strip()} or None
    exclude = None
    if args.exclude_covered:
        from . import preferences
        exclude = {p.get("task_id", "") for p in preferences.collect_pairs()}
    result = execute(args.tasks, styles, args.timeout, args.repeats, languages,
                     exclude=exclude, sets=args.sets, origin=args.origin)
    print(json.dumps({k: result.get(k) for k in ("state", "done", "tasks", "summary", "error")},
                     indent=2))
    return 0 if result.get("state") == "done" else 1


def start(max_tasks: int | None = None, styles: list[str] | None = None,
          languages: set[str] | None = None) -> dict:
    global _THREAD
    with JOB_LOCK:
        if JOB.get("state") == "running":
            return {**status(), "error": "a tournament is already running"}
        settings = config.load()["tournament"]
        # Refuse synchronously: the UI must not show a run that can never start.
        if not library.tasks_path().exists():
            library.build()
        confirmed = {t["id"] for t in library.confirmed()}
        runnable = [t for t in library.load_tasks()
                    if t["id"] in confirmed and t.get("runnable")
                    and not library.is_multi_file(t)]
        if not runnable:
            return {**status(),
                    "error": "no confirmed runnable tasks — validate the library first"}
        tasks = int(max_tasks or settings["max_tasks"])
        chosen_styles = styles or [s for s in settings["styles"] if s in STYLES]
        JOB.update(state="running", error="", summary={})
    _THREAD = threading.Thread(
        target=execute,
        args=(tasks, chosen_styles, float(settings["run_timeout_s"]),
              int(settings["repeat_runs"]), languages),
        daemon=True,
    )
    _THREAD.start()
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
