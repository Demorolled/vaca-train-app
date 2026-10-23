"""scoreboard — one page that answers "is the trainer actually covering VACA?".

Everything here is derived from files and job state that already exist; nothing
is cached or estimated. The questions it is built to answer, in order:

  * does every language VACA can build have tasks, and how many of them has the
    toolchain actually proven?
  * where did those tasks come from, and how much of it is base builds;
  * which app exports score well as exemplars (the puzzle ranking);
  * how big are the training sets, and what is running right now?

The per-language table is the one that matters after adding the base builds: a
language with 100 tasks and 0 verified is a corpus that cannot be used, and the
difference between "ingested" and "proven" is exactly what this page shows.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import capture, config, execution, library, preferences


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def dataset_stats() -> dict:
    """Row counts per training sheet, read straight off disk."""
    data = config.dataset_dir()
    return {
        "sft_train": _rows(data / "train.jsonl"),
        "sft_val": _rows(data / "val.jsonl"),
        "corrections": _rows(data / "corrections.jsonl"),
        "vaca_captures": _rows(capture.app_sheet_path()),
        "app_knowledge": _rows(capture.knowledge_sheet_path()),
        "pair_train": _rows(data / "pairs_train.jsonl"),
        "pair_val": _rows(data / "pairs_val.jsonl"),
        "pairs_total": _rows(data / "pairs.jsonl"),
    }


def language_table(tasks: list[dict], validation: dict[str, dict],
                   puzzles: dict[str, dict]) -> list[dict]:
    """Per-language coverage: ingested vs proven, split by task kind."""
    table: dict[str, dict] = {}
    for task in tasks:
        language = task.get("language", "")
        entry = table.setdefault(language, {
            "language": language, "tasks": 0, "verified": 0, "failed": 0,
            "other": 0, "base_builds": 0, "base_verified": 0,
            "file_sets": 0, "sets_verified": 0, "puzzle_scored": 0,
        })
        status = validation.get(task["id"], {}).get("status", "unvalidated")
        is_set = library.is_multi_file(task)
        is_base = task.get("origin") == "base-build"
        entry["tasks"] += 1
        if is_set:
            entry["file_sets"] += 1
        elif is_base:
            entry["base_builds"] += 1
        if status == "verified":
            entry["verified"] += 1
            if is_set:
                entry["sets_verified"] += 1
            elif is_base:
                entry["base_verified"] += 1
        elif status == "failed":
            entry["failed"] += 1
        else:
            entry["other"] += 1
    for task_id, row in puzzles.items():
        language = next((t.get("language", "") for t in tasks if t["id"] == task_id), "")
        if language in table:
            table[language]["puzzle_scored"] += 1
    return [table[key] for key in sorted(table)]


def summary() -> dict:
    from . import grow, tournament, training, validate

    tasks = library.load_tasks()
    validation = library.load_validation()
    puzzle_scores = library.load_puzzle_scores()
    stats = library.stats()

    origins: dict[str, dict] = {}
    for task in tasks:
        origin = task.get("origin", "unknown")
        entry = origins.setdefault(origin, {"origin": origin, "tasks": 0, "verified": 0})
        entry["tasks"] += 1
        if validation.get(task["id"], {}).get("status") == "verified":
            entry["verified"] += 1

    ranked = sorted(puzzle_scores.values(), key=lambda r: -r.get("clean", 0))
    return {
        "generated_at": _now(),
        "library": {
            "tasks": stats["tasks"],
            "confirmed": stats["confirmed"],
            "multi_file": stats["index"].get("multi_file", 0),
            "puzzle_scored": len(puzzle_scores),
            "by_status": stats["by_status"],
            "by_origin": sorted(origins.values(), key=lambda r: -r["tasks"]),
            "by_language": language_table(tasks, validation, puzzle_scores),
        },
        "datasets": dataset_stats(),
        "puzzles": {
            "apps": len(puzzle_scores),
            "mean_clean": round(sum(r.get("clean", 0) for r in ranked) / len(ranked), 4)
            if ranked else 0.0,
            "top": ranked[:5],
            "weakest": ranked[-5:][::-1] if ranked else [],
        },
        "runs": {
            "tournament": tournament.status(),
            "training": training.status(),
            "grow": grow.status(),
            "validate": validate.status(),
        },
        "toolchains": {language: bool(execution.resolve_bin(language))
                       for language in sorted(execution.TOOLCHAINS)},
        "pairs_source": preferences.stats(),
    }


def as_text() -> str:
    """A terminal rendering, for the case where the page is not open."""
    data = summary()
    lines = ["VACA TRAINER SCOREBOARD", "=" * 78,
             f"library: {data['library']['tasks']} tasks, "
             f"{data['library']['confirmed']} confirmed, "
             f"{data['library']['multi_file']} file sets", ""]
    header = f"{'language':12s} {'tasks':>6s} {'verified':>8s} {'base':>6s} {'bv':>5s} {'sets':>5s} {'sv':>4s}"
    lines.append(header)
    lines.append("-" * len(header))
    for row in data["library"]["by_language"]:
        lines.append(f"{row['language'][:12]:12s} {row['tasks']:6d} {row['verified']:8d} "
                     f"{row['base_builds']:6d} {row['base_verified']:5d} "
                     f"{row['file_sets']:5d} {row['sets_verified']:4d}")
    lines.append("")
    for name, value in data["datasets"].items():
        lines.append(f"  {name:16s} {value}")
    lines.append("")
    run = data["runs"]["tournament"]
    lines.append(f"tournament: {run.get('state')} {run.get('done')}/{run.get('tasks')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Print the trainer scoreboard")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    print(json.dumps(summary(), indent=2) if args.json else as_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
