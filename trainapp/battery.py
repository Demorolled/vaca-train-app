"""battery — score a coder by compiling and running what it writes.

Held-out preference margins only say a policy *prefers* one file over another.
This says whether the code it writes actually compiles, runs, and produces the
library reference's output — the thing the library is supposed to guarantee.

Two arms (base model, base+adapter) run the same tasks, with the same prompt
the preference pairs were built from, so the only variable is the weights.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import adherence, config, execution, library, preferences, repair, tournament

PROMPT = preferences.PROMPT_TEMPLATE
VALID_LANGUAGES = tuple(sorted(execution.TOOLCHAINS))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seen_task_ids() -> set[str]:
    """Tasks the preference pairs were built from — never score on those."""
    return {p.get("task_id", "") for p in preferences.collect_pairs() if p.get("task_id")}


def sft_task_ids() -> set[str]:
    """Tasks the SFT sheet taught — never score on those either.

    `librarysft` exports the verified base/medium builds, and `library.load_tasks()`
    serves the battery from the same two sheets. Excluding only the preference
    tasks left the adapter scored on programs it had memorised, which flatters
    the arm that trained and says nothing about the data.
    """
    ids: set[str] = set()
    out = config.dataset_dir()
    for name in ("train.jsonl", "val.jsonl"):
        path = out / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            task_id = ((row.get("meta") or {}).get("task_id") or "").strip()
            if task_id:
                ids.add(task_id)
    return ids


def held_out_ids() -> set[str]:
    """Everything the two trained sheets already taught."""
    return seen_task_ids() | sft_task_ids()


def balanced(tasks: list[dict], limit: int) -> list[dict]:
    """Round-robin across languages so a battery is not all C.

    Deterministic: within each language the tasks are sorted by id, so the same
    library always yields the same battery.
    """
    groups: dict[str, list[dict]] = {}
    for task in sorted(tasks, key=lambda t: t["id"]):
        groups.setdefault(task.get("language", ""), []).append(task)
    picked: list[dict] = []
    while len(picked) < limit:
        progressed = False
        for language in sorted(groups):
            bucket = groups[language]
            if not bucket:
                continue
            picked.append(bucket.pop(0))
            progressed = True
            if len(picked) == limit:
                break
        if not progressed:
            break
    return picked


def select_tasks(tasks: list[dict], excluded: set[str], limit: int,
                 languages: set[str] | None = None,
                 proven: set[str] | None = None) -> list[dict]:
    """Only tasks the toolchain has proven — a compilable snippet is not a program.

    `runnable` is an ingest-time guess (every Rosetta row sets it), so it let
    files with no entry point into the battery, where they could only ever be
    skipped. Selection now asks validation instead.
    """
    if proven is None:
        proven = {t["id"] for t in library.confirmed()}
    usable = [t for t in tasks
              if t["id"] in proven and t.get("runnable")
              and t.get("language") in execution.TOOLCHAINS
              and t["id"] not in excluded]
    if languages:
        usable = [t for t in usable if t["language"] in languages]
    return balanced(usable, limit)


def prompt_for(task: dict) -> str:
    return PROMPT.format(
        language=task.get("language", ""),
        title=(task.get("title") or "").strip(),
        task=(task.get("description") or "").strip() or (task.get("title") or ""),
    )


def _set_files(task: dict, code: str) -> list[dict]:
    """The project with the target file replaced by `code`."""
    target = task.get("target", "")
    return [{"path": f["path"],
             "content": code if f["path"] == target else f["content"]}
            for f in task.get("files") or []]


def _run_set(task: dict, code: str, timeout_s: float) -> dict:
    """Build and run the whole set — the only honest grade for a scaffold.

    The target is usually a module, so it is only launched when its name says it
    is the entry; otherwise the set's real entry point is used.
    """
    target = task.get("target", "")
    result = execution.run_files(_set_files(task, code), task.get("language", ""),
                                 entry=target if execution.is_entry_name(target) else "",
                                 timeout_s=timeout_s)
    return {"valid": result.ok, "stdout": result.stdout,
            "runtime_ms": result.duration_ms,
            "error": result.error or (result.stderr or "")[:300]}


SCAFFOLD_INSTRUCTION = (
    "Write the complete `{target}` file for the project below.\n"
    "It must work with the files that already exist: use their real exports,\n"
    "and do not invent imports that no listed file provides. Reply with the\n"
    "file only — no markdown fence, no commentary."
)


def scaffold_instruction(task: dict) -> str:
    return SCAFFOLD_INSTRUCTION.format(target=task.get("target", ""))


def scaffold_input(task: dict, max_file_chars: int = 1200,
                  max_total_chars: int = 5000) -> str:
    """The project the target has to fit into, as the Input half of a row."""
    target = task.get("target", "")
    lines = [
        f"REQUEST: {(task.get('description') or task.get('title') or '').strip()}",
        f"LANGUAGE: {task.get('language', '')}",
        f"TARGET FILE: {target}",
        "",
        "### Existing project files",
    ]
    budget = max_total_chars
    for entry in task.get("files") or []:
        if entry["path"] == target or budget <= 0:
            continue
        body = (entry.get("content") or "")[: min(max_file_chars, budget)]
        budget -= len(body)
        lines.append(f"--- {entry['path']} ---")
        lines.append(body.rstrip())
    return "\n".join(lines)


def scaffold_prompt(task: dict, max_file_chars: int = 1200,
                    max_total_chars: int = 5000) -> str:
    """A file-in-context prompt: the siblings are given, one file is wanted.

    This is the prompt shape VACA's own capture uses ("Generate the COMPLETE
    file 'X'"), so a battery score and a training row measure the same thing —
    whether the file fits the project it is written into. `scaffoldsft` builds
    its rows from the same two halves and the same template.
    """
    return PROMPT.format(
        instruction=scaffold_instruction(task),
        language=task.get("language", ""),
        title=(task.get("title") or "").strip(),
        task=scaffold_input(task, max_file_chars, max_total_chars),
    )


def failure_reason(result: dict) -> str:
    """One line saying why a reference could not be scored.

    A program that fails after compiling often writes nothing to stderr (it
    exits non-zero on EOF, say), so neither source may be assumed non-empty.
    """
    for text in (result.get("error"), result.get("stderr"), result.get("stdout")):
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        if lines:
            return lines[-1][:200]
    code = result.get("exit_code")
    return f"exited {code} with no output" if code not in (None, 0) else \
        "reference does not compile/run here"


def score(rows: list[dict]) -> dict:
    """Rates for one arm. `behavior` only counts tasks with a stable reference."""
    attempts = [r for r in rows if not r.get("skipped")]
    verified = [r for r in attempts if r.get("valid")]
    behavioral = [r for r in attempts if r.get("deterministic")]
    matched = [r for r in behavioral if r.get("stdout_match")]
    scaffolds = [r for r in verified if r.get("scaffold")]
    adherence_scores = [r.get("adherence", 0.0) for r in scaffolds]
    by_language: dict[str, dict] = {}
    for row in attempts:
        bucket = by_language.setdefault(row.get("language", ""), {"attempts": 0, "verified": 0})
        bucket["attempts"] += 1
        bucket["verified"] += 1 if row.get("valid") else 0
    return {
        "attempts": len(attempts),
        "verified": len(verified),
        "verify_rate": round(len(verified) / len(attempts), 4) if attempts else 0.0,
        "behavior_checked": len(behavioral),
        "behavior_matched": len(matched),
        "behavior_rate": round(len(matched) / len(behavioral), 4) if behavioral else 0.0,
        "avg_bytes": round(sum(r.get("bytes", 0) for r in verified) / len(verified)) if verified else 0,
        "avg_runtime_ms": round(sum(r.get("runtime_ms", 0) for r in verified) / len(verified)) if verified else 0,
        "scaffold_verified": len(scaffolds),
        "adherence_rate": round(sum(adherence_scores) / len(adherence_scores), 4) if adherence_scores else 0.0,
        "by_language": by_language,
    }


def run(arms: dict, tasks: list[dict], timeout_s: float = 20.0,
        out_dir: Path | None = None, log=print,
        held_out: dict | None = None) -> dict:
    """Generate, compile, run and compare every task for every arm."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_dir = out_dir or (config.data_dir() / "battery" / stamp)
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "results.jsonl"

    references: dict[str, dict] = {}
    with results_path.open("w", encoding="utf-8") as handle:
        for task in tasks:
            scaffold = library.is_multi_file(task)
            run = (lambda code, t=task: _run_set(t, code, timeout_s)) if scaffold \
                else (lambda code, t=task: tournament._run_code(t, code, timeout_s))
            first = run(task["code"])
            again = run(task["code"])
            # TypeScript sets are typechecked, not executed, so an empty stdout
            # on both sides would score as a behaviour match for free.
            deterministic = tournament._normalize_stdout(first.get("stdout", "")) == \
                tournament._normalize_stdout(again.get("stdout", "")) and \
                not (scaffold and task.get("language") == "typescript")
            references[task["id"]] = {
                "valid": bool(first.get("valid")),
                "deterministic": deterministic,
                "stdout": tournament._normalize_stdout(first.get("stdout", "")),
                "runtime_ms": first.get("runtime_ms", 0),
            }
            for name, coder in arms.items():
                row = {"arm": name, "task_id": task["id"], "language": task["language"],
                       "title": task.get("title", ""), "at": _now(),
                       "deterministic": deterministic, "valid": False,
                       "stdout_match": False, "bytes": 0, "runtime_ms": 0,
                       "scaffold": scaffold,
                       "context_files": max(0, len(task.get("files") or []) - 1) if scaffold else 0,
                       "skipped": not references[task["id"]]["valid"]}
                if row["skipped"]:
                    row["error"] = failure_reason(first)
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    continue
                try:
                    prompt = scaffold_prompt(task) if scaffold else prompt_for(task)
                    code = repair.extract_code(coder.complete(prompt))
                except Exception as err:  # a broken coder is data, not a crash
                    row["error"] = f"coder failed: {err}"[:300]
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    continue
                result = run(code)
                row.update({
                    "valid": bool(result.get("valid")),
                    "runtime_ms": result.get("runtime_ms", 0),
                    "bytes": len(code.encode("utf-8")),
                    "stdout_match": deterministic and
                    tournament._normalize_stdout(result.get("stdout", "")) ==
                    references[task["id"]]["stdout"],
                    "error": (result.get("error") or "")[:300],
                    "code": code,
                })
                if scaffold:
                    row["adherence"] = adherence.score_files(
                        _set_files(task, code), task.get("language", ""))["score"]
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                log(f"{name:8s} {task['language']:5s} {task['id'][:44]:44s} "
                    f"{'PASS' if row['valid'] else 'fail'}")

    rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    summary = {
        "arms": {name: score([r for r in rows if r["arm"] == name]) for name in arms},
        "tasks": len(tasks),
        "languages": sorted({t["language"] for t in tasks}),
        "held_out": held_out or {},
        "task_ids": [t["id"] for t in tasks],
        "references": {k: {kk: vv for kk, vv in v.items() if kk != "stdout"}
                       for k, v in references.items()},
        "finished_at": _now(),
        "run_dir": str(run_dir),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score coder arms by compiling and running their code")
    parser.add_argument("--tasks", type=int, default=12)
    parser.add_argument("--model", default="")
    parser.add_argument("--adapter", default="")
    parser.add_argument("--languages", default="")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    from . import localcoder

    cfg = config.load()
    model = args.model or cfg["training"]["model"]
    pairs_seen = seen_task_ids()
    sft_seen = sft_task_ids()
    languages = {s.strip() for s in args.languages.split(",") if s.strip()} or None
    tasks = select_tasks(library.load_tasks(), pairs_seen | sft_seen, args.tasks, languages)
    if not tasks:
        print("battery: no held-out confirmed tasks to score", file=sys.stderr)
        return 2
    print(f"battery: {len(tasks)} task(s); held out {len(pairs_seen)} pair task(s) "
          f"and {len(sft_seen)} SFT task(s)", flush=True)

    arms: dict[str, object] = {"base": localcoder.LocalCoder(model)}
    if args.adapter:
        arms["orpo"] = localcoder.LocalCoder(model, adapter=args.adapter)
    out_dir = Path(args.out) if args.out else None
    summary = run(arms, tasks, args.timeout, out_dir,
                  held_out={"pairs": len(pairs_seen), "sft": len(sft_seen)})
    for name, stats in summary["arms"].items():
        print(f"{name:8s} verified {stats['verified']}/{stats['attempts']} "
              f"({stats['verify_rate']:.0%})  behavior {stats['behavior_matched']}/"
              f"{stats['behavior_checked']} ({stats['behavior_rate']:.0%})  "
              f"{stats['avg_bytes']} B  {stats['avg_runtime_ms']} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
