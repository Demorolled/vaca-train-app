"""functioneval — held-out function sets: did the adapter get better at them?

The night's rows come from one function per set, so scoring on those sets would
measure memory. This holds out every third task id — the same deterministic rule
`trainloop.prepare_data` uses to keep those rows out of training — asks both arms
for the same function, splices it into the real file, builds and runs the set,
and reports compile and behaviour rates per arm.

The split is by task id, not by row, so a held-out set can never leak in through
its pairs or its neighbours in the same file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import config, functionprobe, overnight

HOLDOUT_EVERY = 3
FAMILY_EVERY = 2
# A family needs at least two scored sets to be measured at all, and no family
# may own the pool: fibonacci once held 49 of the 223 judgeable sets.
MIN_FAMILY_SETS = 2
MAX_FAMILY_SETS = 4

# A family is the program, not the file: the same ask in twelve languages is
# one family, which is what a task-level split fails to separate.
LANGUAGES = {"python", "go", "php", "ruby", "javascript", "typescript", "rust",
             "java", "c", "cpp", "csharp", "kotlin", "swift", "ts", "js", "cs",
             "c++", "c#", "py", "rb", "node", "bun", "deno", "golang"}
FILLER = {"a", "an", "the", "cli", "program", "script", "app", "tool", "and"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(text: str) -> int:
    return int(hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:8], 16)


def is_held_out(task_id: str) -> bool:
    return _hash(task_id) % HOLDOUT_EVERY == 0


def family_of(task: dict | str) -> str:
    """The program a task is, with its language and file name taken out.

    `a java cli that prints the first 12 fibonacci numbers` and the Go version
    of the same ask are one family; a task-level split keeps one of them in
    training, which is why a fibonacci hold-out was still partly seen.
    """
    if isinstance(task, dict):
        if task.get("family"):
            return " ".join(re.findall(r"[a-z0-9]+", str(task["family"]).lower()))
        words = _words(str(task.get("description") or task.get("title") or ""))
        if words:
            return " ".join(words)
        return _slug(str(task.get("id", "")))
    return _slug(str(task))


def _slug(task_id: str) -> str:
    """Best effort without a description: the id, minus its hash tail."""
    slug = task_id.split("/")[-1]
    slug = re.sub(r"-[0-9a-f]{6,10}$", "", slug)
    return " ".join(_words(slug.replace("-", " "))) or slug


def _words(text: str) -> list[str]:
    """Significant words of a description, minus language and filler.

    A title carries its file after an em dash (`stock table — main.py`); that
    half names the file, not the program, so it is dropped first.
    """
    head = re.split(r"\s+[—–-]\s+", text)[0]
    return [word for word in re.findall(r"[a-z0-9]+", head.lower())
            if word not in LANGUAGES and word not in FILLER]


def is_family_held_out(family: str) -> bool:
    return _hash(family) % FAMILY_EVERY == 0


def family_sizes(tasks: list[dict]) -> dict[str, list[str]]:
    """Task ids per program family — how many siblings a family actually has."""
    groups: dict[str, list[str]] = {}
    for task in tasks:
        groups.setdefault(family_of(task), []).append(task["id"])
    return groups


def holdout_families(tasks: list[dict]) -> set[str]:
    """Families a family split keeps out — every one that has siblings.

    A family represented by a single set cannot be averaged over its own
    languages, so its score is one draw no matter how the split is drawn. In the
    first family pool 34 of 42 families had exactly one set, which is how a
    language swap inside a family read as a three-task gain (+6/-3, p=0.51).

    Every measurable family is held out rather than a hash-selected third: the
    power of a paired test comes from the number of discordant sets, and sampling
    the eligible families threw away half of the only sets that can produce them.
    """
    groups = family_sizes(tasks)
    return {family for family, ids in groups.items() if len(ids) >= MIN_FAMILY_SETS}


def family_holdout_ids(tasks: list[dict]) -> set[str]:
    """Every task id whose family is held out — for filtering training rows."""
    held = holdout_families(tasks)
    return {t["id"] for t in tasks if family_of(t) in held}


def holdout_task_ids(rows: list[dict]) -> set[str]:
    """Task ids the trainer must not learn from, derived from the rows it has."""
    return {row["task_id"] for row in rows
            if row.get("task_id") and is_held_out(row["task_id"])}


def held_out_tasks(tasks: list[dict] | None = None,
                   by_family: bool = False) -> list[dict]:
    """Held-out sets that a night actually proved judgeable.

    Without an export there is nothing to hold out *from*, so the pool is the
    whole library and the scorer skips the sets whose behaviour is invisible.
    `by_family` holds out whole programs instead of single task ids, so a set
    cannot be scored on a shape its siblings taught in another language.
    """
    pool = tasks if tasks is not None else functionprobe.candidates()
    known = {r.get("task_id") for r in overnight.load_export()["sft"]
             if r.get("verified") == "behaviour"}
    if by_family:
        held = holdout_families(pool)
        taken: dict[str, int] = {}
        out: list[dict] = []
        for task in pool:
            family = family_of(task)
            if family not in held or taken.get(family, 0) >= MAX_FAMILY_SETS:
                continue
            taken[family] = taken.get(family, 0) + 1
            out.append(task)
        return out
    return [t for t in pool
            if is_held_out(t["id"]) and (not known or t["id"] in known)]


def score(coder, tasks: list[dict], timeout_s: float = 25) -> dict:
    """Every held-out set, once, through one arm."""
    rows: list[dict] = []
    for task in tasks:
        try:
            row = functionprobe.probe(task, coder, timeout_s=timeout_s)
        except Exception as err:  # a dead coder is a failed row, not a crash
            row = {"task_id": task["id"], "language": task["language"],
                   "error": f"{type(err).__name__}: {err}"[:300], "at": _now()}
        row["language"] = task.get("language", "")
        rows.append(row)
    return {"rows": rows, "stats": summarise(rows)}


def summarise(rows: list[dict]) -> dict:
    asked = [r for r in rows if not r.get("skipped")]
    return {
        "tasks": len(rows),
        "attempts": len(asked),
        "skipped": len(rows) - len(asked),
        "compile": sum(1 for r in asked if r.get("compile")),
        "match": sum(1 for r in asked if r.get("match")),
        "compile_rate": round(sum(1 for r in asked if r.get("compile")) / len(asked), 3)
        if asked else 0.0,
        "match_rate": round(sum(1 for r in asked if r.get("match")) / len(asked), 3)
        if asked else 0.0,
    }


def evaluate(arms: dict[str, object], tasks: list[dict], timeout_s: float = 25,
             out: Path | None = None) -> dict:
    """Score each arm on the same held-out sets and write the rows."""
    result: dict = {"generated_at": _now(), "held_out": [t["id"] for t in tasks],
                    "arms": {}, "rows": {}}
    for name, coder in arms.items():
        scored = score(coder, tasks, timeout_s)
        result["arms"][name] = scored["stats"]
        result["rows"][name] = scored["rows"]
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "eval.json").write_text(json.dumps(result, indent=2) + "\n",
                                       encoding="utf-8")
        for name, rows in result["rows"].items():
            (out / f"{name}.jsonl").write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score base and adapter on held-out function sets")
    parser.add_argument("--model", default="",
                        help="overrides training.model")
    parser.add_argument("--adapter", default="", help="LoRA adapter directory")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument("--out", default="")
    parser.add_argument("--by-family", action="store_true",
                        help="hold out whole program families, not single tasks")
    args = parser.parse_args(argv)

    from .localcoder import LocalCoder

    model = args.model or config.load()["training"]["model"]
    tasks = held_out_tasks(by_family=args.by_family)
    tasks = tasks[:args.limit] if args.limit else tasks
    if not tasks:
        print("functioneval: no held-out sets")
        return 2
    out = Path(args.out) if args.out else config.data_dir() / "functioneval" / \
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    arms: dict[str, object] = {"base": LocalCoder(model)}
    if args.adapter:
        arms["adapter"] = LocalCoder(model, adapter=args.adapter)
    try:
        result = evaluate(arms, tasks, args.timeout, out)
    finally:
        for coder in arms.values():
            coder.close()
    for name, stats in result["arms"].items():
        print(f"{name:8s} compile {stats['compile']}/{stats['attempts']} "
              f"({stats['compile_rate']:.0%})  behaviour {stats['match']}/"
              f"{stats['attempts']} ({stats['match_rate']:.0%})")
    print(json.dumps({"out": str(out), "arms": result["arms"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
