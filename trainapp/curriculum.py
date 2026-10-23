"""curriculum — basic, then medium, then scaffolding, advancing on a plateau.

A corpus that mixes 20-line programs with 400-line app sets teaches neither well:
the model sees one distribution and no signal about which it is failing. This
module turns the library into three stages and defines the rule for moving up:

  basic     elementary, one file, prints a result      (`base-build`, 1,300)
  medium    a complete small program with real logic   (`rosetta`, `curated`)
  scaffold  a file inside a multi-file app             (`vaca-export`, sets)

The goal at every stage is the same and is measured the same way: **verify rate
up, bytes down, runtime down, adherence up**. A stage is done when the coder and
judge stop moving it: `plateau()` requires `min_rounds` evaluations and a gain
below `min_gain` on the efficiency score. Only then does the next stage's data
become the training set.

Nothing here trains by itself — it decides *what* to train on and *when* the
current data is exhausted, so a long run cannot silently overfit one stage. The
state is a small JSON file plus an append-only history, so a restart resumes
where it stopped and every advance is auditable.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from . import config, library

STAGES: tuple[dict, ...] = (
    {"name": "basic", "origins": ("base-build",), "kind": "single",
     "goal": "compile and print the right answer in one file"},
    {"name": "medium", "origins": ("medium-build", "rosetta", "curated", "grown"),
     "kind": "single",
     "goal": "write a complete small program with real logic, compactly"},
    {"name": "scaffold", "origins": ("vaca-export",), "kind": "set",
     "goal": "write one file that fits its siblings and keeps the app building"},
)

# An efficiency point is worth this much: a verified build, minus the cost of
# what it took to get it. Bytes and milliseconds are scaled so neither dominates.
BYTES_WEIGHT = 1 / 2000
MS_WEIGHT = 1 / 400


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state_path() -> Path:
    path = config.data_dir() / "curriculum"
    path.mkdir(parents=True, exist_ok=True)
    return path / "state.json"


def history_path() -> Path:
    return state_path().parent / "history.jsonl"


def stage(name: str) -> dict:
    for entry in STAGES:
        if entry["name"] == name:
            return entry
    raise KeyError(f"unknown stage {name!r}; known: {[s['name'] for s in STAGES]}")


def stage_tasks(name: str, limit: int = 0, confirmed_only: bool = True) -> list[dict]:
    """Tasks belonging to a stage: origin-matched, and proven when asked."""
    entry = stage(name)
    confirmed = {t["id"] for t in library.confirmed()} if confirmed_only else None
    tasks: list[dict] = []
    for task in library.load_tasks():
        if task.get("origin") not in entry["origins"]:
            continue
        is_set = library.is_multi_file(task)
        if entry["kind"] == "set" and not is_set:
            continue
        if entry["kind"] == "single" and is_set:
            continue
        if not task.get("runnable"):
            continue
        if confirmed is not None and task["id"] not in confirmed:
            continue
        tasks.append(task)
    tasks.sort(key=lambda t: (t["language"], t["id"]))
    return tasks[:limit] if limit else tasks


def coverage() -> dict[str, dict]:
    """Per stage: tasks available, proven, and by language."""
    out: dict[str, dict] = {}
    for entry in STAGES:
        tasks = stage_tasks(entry["name"], confirmed_only=False)
        proven = stage_tasks(entry["name"])
        by_language: dict[str, int] = {}
        for task in proven:
            by_language[task["language"]] = by_language.get(task["language"], 0) + 1
        out[entry["name"]] = {"tasks": len(tasks), "proven": len(proven),
                              "by_language": by_language, "goal": entry["goal"]}
    return out


def efficiency(summary: dict) -> dict:
    """One number for "faster, smaller, cleaner" on a battery summary.

    Verify rate is the gate: an arm that fails to compile gains nothing from
    being small. Above it, fewer bytes and fewer milliseconds add up.
    """
    arms = summary.get("arms") or {}
    name, stats = next(iter(arms.items())) if arms else ("", {})
    verify = float(stats.get("verify_rate", 0.0))
    bytes_penalty = float(stats.get("avg_bytes", 0)) * BYTES_WEIGHT
    ms_penalty = float(stats.get("avg_runtime_ms", 0)) * MS_WEIGHT
    return {
        "arm": name,
        "verify_rate": round(verify, 4),
        "avg_bytes": stats.get("avg_bytes", 0),
        "avg_runtime_ms": stats.get("avg_runtime_ms", 0),
        "adherence_rate": stats.get("adherence_rate", 0.0),
        "efficiency": round(verify - bytes_penalty - ms_penalty, 4),
    }


def plateau(history: list[dict], *, min_rounds: int = 3,
            min_gain: float = 0.01) -> dict:
    """Has the current stage stopped improving?

    `history` is the newest-last list of evaluations for ONE stage. The stage is
    exhausted when the last `min_rounds` points gain less than `min_gain` in
    total — or when the gain is negative, which is not a reason to climb higher.
    """
    points = [float(row.get("efficiency", 0.0)) for row in history]
    if len(points) < min_rounds:
        return {"done": False, "reason": f"needs {min_rounds} evaluations, has {len(points)}",
                "rounds": len(points), "gain": 0.0}
    window = points[-min_rounds:]
    gain = round(window[-1] - window[0], 4)
    return {"done": gain < min_gain, "reason":
            f"gain {gain:+.4f} over {min_rounds} rounds (threshold {min_gain})",
            "rounds": len(points), "gain": gain}


def load_state() -> dict:
    path = state_path()
    if not path.exists():
        return {"stage": STAGES[0]["name"], "rounds": 0, "started_at": _now(),
                "history": [], "advanced": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"stage": STAGES[0]["name"], "rounds": 0, "started_at": _now(),
                "history": [], "advanced": []}


def save_state(state: dict) -> None:
    path = state_path()
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def record(evaluation: dict) -> dict:
    """Append one evaluation to the current stage's history."""
    state = load_state()
    entry = {**evaluation, "stage": state["stage"], "at": _now()}
    state.setdefault("history", []).append(entry)
    state["rounds"] = int(state.get("rounds", 0)) + 1
    save_state(state)
    with history_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def stage_history(state: dict | None = None, name: str = "") -> list[dict]:
    state = state or load_state()
    target = name or state["stage"]
    return [row for row in state.get("history", []) if row.get("stage") == target]


def should_advance(*, min_rounds: int = 3, min_gain: float = 0.01) -> dict:
    state = load_state()
    current = state["stage"]
    verdict = plateau(stage_history(state, current), min_rounds=min_rounds,
                      min_gain=min_gain)
    order = [entry["name"] for entry in STAGES]
    index = order.index(current)
    nxt = order[index + 1] if index + 1 < len(order) else ""
    return {"stage": current, "next": nxt, **verdict}


def advance(*, min_rounds: int = 3, min_gain: float = 0.01) -> dict:
    """Move to the next stage only when the plateau rule agrees."""
    decision = should_advance(min_rounds=min_rounds, min_gain=min_gain)
    state = load_state()
    if not decision["done"]:
        return {**decision, "advanced": False}
    if not decision["next"]:
        return {**decision, "advanced": False,
                "reason": "final stage reached; nothing above scaffold"}
    state.setdefault("advanced", []).append(
        {"from": decision["stage"], "to": decision["next"], "at": _now(),
         "gain": decision["gain"], "rounds": decision["rounds"]})
    state["stage"] = decision["next"]
    state["rounds"] = 0
    save_state(state)
    return {**decision, "to": decision["next"], "advanced": True}


def plan(limit: int = 0) -> dict:
    """What to train on next, and what the stage's exit condition is."""
    state = load_state()
    current = stage(state["stage"])
    tasks = stage_tasks(current["name"], limit)
    return {
        "stage": current["name"],
        "goal": current["goal"],
        "rounds_so_far": state.get("rounds", 0),
        "history": stage_history(state, current["name"]),
        "tasks": len(tasks),
        "languages": sorted({t["language"] for t in tasks}),
        "next_command": _next_command(current["name"]),
        "advance_rule": should_advance(),
        "stages": coverage(),
    }


def _next_command(name: str) -> str:
    if name == "scaffold":
        return ("python3 -m trainapp.battery --tasks 30 --languages python,go,java,"
                "csharp,typescript")
    return "python3 -m trainapp.battery --tasks 30"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Staged training curriculum")
    parser.add_argument("--plan", action="store_true", help="what to train on now")
    parser.add_argument("--coverage", action="store_true", help="per stage counts")
    parser.add_argument("--record", metavar="JSON", default="",
                        help="record an evaluation summary file")
    parser.add_argument("--advance", action="store_true", help="apply the plateau rule")
    parser.add_argument("--min-rounds", type=int, default=3)
    parser.add_argument("--min-gain", type=float, default=0.01)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    if args.coverage:
        print(json.dumps(coverage(), indent=2))
        return 0
    if args.record:
        summary = json.loads(Path(args.record).read_text(encoding="utf-8"))
        print(json.dumps(record(efficiency(summary)), indent=2))
        return 0
    if args.advance:
        print(json.dumps(advance(min_rounds=args.min_rounds, min_gain=args.min_gain),
                         indent=2))
        return 0
    print(json.dumps(plan(args.limit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
