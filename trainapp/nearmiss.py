"""nearmiss — preference pairs mined from answers that were already right.

The held-out regressions were near misses, not broken code: a Go fibonacci that
seeded at 1 instead of 0, a PHP word count that never accumulated. Both built.
The night's own pairs cannot teach that contrast, because its rejected half is
whatever the model happened to sample — usually something that does not build at
all — so ORPO keeps learning "compiles vs. does not compile" and the boundary
errors survive untouched.

This module manufactures the missing half. Take a passing function, perturb it
mechanically (flip a loop guard, shift a seed, swap an accumulator, bump a
comparison), and keep the perturbation only when the whole set still builds and
its stdout now differs from the reference. A kept perturbation is a pair: the
original answer chosen, the near miss rejected, the same prompt on both sides.

Nothing is asserted about whether a mutation "should" break output — the set
decides. A mutation that compiles but leaves the output identical is dropped as
uninformative, and one that fails to build is dropped as a different lesson.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import execution, functioneval, functionprobe, library, overnight

PAIR_FILE = "nearmiss.jsonl"
SUMMARY_FILE = "nearmiss_summary.json"

# A mutation is only worth a build if it touches a decision the output can see;
# five candidates per answer is enough to find one and bounds the extra builds.
MAX_CANDIDATES = 5

LOOP = re.compile(r"\b(?:for|while)\b[^\n{}]*?(?P<op><=|<)")
RANGE_TWO = re.compile(r"range\(\s*(?P<a>[^,()]+?)\s*,\s*(?P<b>[^,()]+?)\s*\)")
RANGE_ONE = re.compile(r"range\(\s*(?P<a>[^,()]+?)\s*\)")
RUBY_DOTS = re.compile(r"(?<!\.)\.{2,3}(?!\.)")
SEED = re.compile(r"(?m)^(?P<indent>[ \t]*)"
                  r"(?:let\s+|var\s+|const\s+|int\s+|long\s+|short\s+|float\s+|"
                  r"double\s+|auto\s+)?"
                  r"(?P<name>[A-Za-z_]\w*)\s*(?P<op>:=|=)\s*(?P<num>-?\d+)\s*(?:;|$)")
ACCUM = re.compile(r"(?P<lhs>[A-Za-z_]\w*)\s*(?P<op>\+=|-=)")
COND = re.compile(r"\b(?:if|elif|else\s+if|while)\b[^\n{}]*?"
                  r"(?P<op>==|!=|>=|<=|>|<)")
ARITH = re.compile(r"(?P<sign>[+\-*/])\s*(?P<num>\d+)\b")
DIV = re.compile(r"(?P<op>//|/)\s*(?P<num>[2-9])\b")

FLIP = {"<": "<=", "<=": "<", ">": ">=", ">=": ">", "==": "!=", "!=": "==",
        "+=": "-=", "-=": "+="}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sub(code: str, pattern: re.Pattern, build) -> str | None:
    """`code` with the first match of `pattern` replaced, or None."""
    match = pattern.search(code)
    if not match:
        return None
    return code[:match.start()] + build(match) + code[match.end():]


def _swap(match: re.Match, value: str, group: str = "op") -> str:
    """The whole match with `group` replaced by `value`."""
    text = match.group(0)
    start = match.start(group) - match.start()
    end = match.end(group) - match.start()
    return text[:start] + value + text[end:]


def _loop_guard(code: str, language: str) -> str | None:
    """`i < n` becomes `i <= n`: the classic one-iteration-too-many."""
    return _sub(code, LOOP, lambda m: _swap(m, FLIP[m.group("op")]))


def _range_end(code: str, language: str) -> str | None:
    """`range(n)` becomes `range(n + 1)`."""
    if language != "python":
        return None
    def build(match: re.Match) -> str:
        return f"range({match.group('a')}, {match.group('b')} + 1)"
    return (_sub(code, RANGE_TWO, build)
            or _sub(code, RANGE_ONE, lambda m: f"range({m.group('a')} + 1)"))


def _ruby_range(code: str, language: str) -> str | None:
    """`0...n` counts n times, `0..n` counts n + 1 times."""
    if language != "ruby":
        return None
    return _sub(code, RUBY_DOTS,
                lambda m: ".." if m.group(0) == "..." else "...")


def _seed(code: str, language: str) -> str | None:
    """`total = 0` becomes `total = 1`: the accumulator starts one off."""
    def build(match: re.Match) -> str:
        return _swap(match, str(int(match.group("num")) + 1), "num")
    return _sub(code, SEED, build)


def _accumulator(code: str, language: str) -> str | None:
    """`total += x` becomes `total -= x`: the update runs with the wrong sign."""
    return _sub(code, ACCUM, lambda m: _swap(m, FLIP[m.group("op")]))


def _condition(code: str, language: str) -> str | None:
    """A branch tested one step off its boundary."""
    return _sub(code, COND, lambda m: _swap(m, FLIP[m.group("op")]))


def _arithmetic(code: str, language: str) -> str | None:
    """`i + 1` becomes `i + 2`: an index that skips or repeats an element."""
    def build(match: re.Match) -> str:
        return _swap(match, str(int(match.group("num")) + 1), "num")
    return _sub(code, ARITH, build)


def _divisor(code: str, language: str) -> str | None:
    """`n / 2` becomes `n / 3`: the wrong bucket size."""
    def build(match: re.Match) -> str:
        return _swap(match, str(int(match.group("num")) + 1), "num")
    return _sub(code, DIV, build)


STRATEGIES = (("loop-guard", _loop_guard), ("range-end", _range_end),
              ("ruby-range", _ruby_range), ("seed", _seed),
              ("accumulator", _accumulator), ("condition", _condition),
              ("arithmetic", _arithmetic), ("divisor", _divisor))


def mutants(code: str, language: str, limit: int = MAX_CANDIDATES) -> list[dict]:
    """Mechanical perturbations of one function, each a single edit.

    Every strategy is offered the same original, so two mutants never stack
    edits; a strategy that does not apply (no loop, no numeric seed) is skipped.
    """
    out: list[dict] = []
    seen: set[str] = {code}
    for name, strategy in STRATEGIES:
        try:
            changed = strategy(code, language)
        except (KeyError, IndexError):
            changed = None
        if not changed or changed in seen:
            continue
        seen.add(changed)
        out.append({"mutation": name, "code": changed})
        if len(out) >= limit:
            break
    return out


def _task_index(tasks: list[dict]) -> dict[str, dict]:
    return {t["id"]: t for t in tasks}


def _function_for(task: dict, row: dict) -> dict | None:
    """The function a passing row was asked for, found again in the real file."""
    target = functionprobe.target_of(task)
    if target is None:
        return None
    found = functionprobe.find_functions(task["language"], target["content"])
    signature = row.get("function") or ""
    lines = row.get("function_lines")
    same = [f for f in found if f["signature"] == signature
            and (lines is None or f["lines"] == lines)]
    if same:
        return same[0]
    ranked = sorted(found, key=lambda f: f["lines"], reverse=True)
    index = row.get("function_index")
    if isinstance(index, int) and 0 <= index < len(ranked) \
            and not signature:
        return ranked[index]
    return None


def interleaved(records: list[dict], tasks: dict[str, dict]) -> list[dict]:
    """Rows in round-robin family order, so one family cannot fill the sheet.

    The night passes fibonacci-shaped sets far more often than anything else,
    so plain record order mines mostly fibonacci: 169 pairs from 406 rows were
    two thirds one family, which is why the mined data taught that family and
    not programs in general.
    """
    groups: dict[str, list[dict]] = {}
    for row in records:
        task = tasks.get(row.get("task_id", ""))
        family = functioneval.family_of(task) if task else (row.get("task_id") or "")
        groups.setdefault(family, []).append(row)
    queues = [list(rows) for rows in groups.values()]
    order: list[dict] = []
    while any(queues):
        for queue in queues:
            if queue:
                order.append(queue.pop(0))
    return order


def mine(records: list[dict], tasks: list[dict], per_row: int = 1,
         candidates: int = MAX_CANDIDATES, limit: int = 0,
         timeout_s: float = 25, log=None, per_family: int = 0,
         balanced: bool = True) -> dict:
    """Turn passing rows into (original, near-miss) pairs on their own prompts.

    A row is usable only when the untouched set still reproduces the row's
    reference: a set that is flaky or environment-dependent cannot certify a
    mutation, and pairing it would teach noise.

    `per_family` caps how many pairs one program may contribute (0 = no cap) and
    `balanced` walks the rows round-robin by family, so a cap is reached evenly
    instead of by whichever family happened to come first.
    """
    index = _task_index(tasks)
    rows: list[dict] = []
    counts = {"records": 0, "passing": 0, "unstable": 0, "no_function": 0,
              "built": 0, "same_output": 0, "accepted": 0, "capped": 0}
    seen: set[tuple[str, str, str]] = set()
    cache: dict[tuple[str, str], tuple[dict, str] | None] = {}
    per_family_kept: dict[str, int] = {}

    passing = [row for row in records
               if row.get("match") and (row.get("reply") or "").strip()]
    if balanced:
        passing = interleaved(passing, index)

    for row in passing:
        if limit and counts["records"] >= limit:
            break
        task = index.get(row.get("task_id", ""))
        if task is not None and per_family:
            family = functioneval.family_of(task)
            if per_family_kept.get(family, 0) >= per_family:
                counts["capped"] += 1
                continue
        counts["records"] += 1
        if task is None:
            continue
        key = (task["id"], row.get("function") or "")
        if key not in cache:
            fn = _function_for(task, row)
            cache[key] = (fn, fn["signature"] if fn else "") if fn else None
        cached = cache[key]
        if cached is None:
            counts["no_function"] += 1
            continue
        fn = cached[0]
        target = functionprobe.target_of(task)
        chosen = functionprobe.extract_block(task["language"], row["reply"],
                                             fn["signature"])
        if not chosen.strip():
            counts["no_function"] += 1
            continue
        reference = row.get("reference")
        if not reference:
            continue
        original = functionprobe.run_set(
            task, functionprobe.splice(target["content"], fn, chosen), timeout_s)
        if not original.ok or functionprobe.collapse(original.stdout) != reference:
            counts["unstable"] += 1
            continue
        counts["passing"] += 1
        kept = 0
        for mutant in mutants(chosen, task["language"], candidates):
            got = functionprobe.run_set(
                task, functionprobe.splice(target["content"], fn, mutant["code"]),
                timeout_s)
            if not got.ok:
                counts["built"] += 1
                continue
            if functionprobe.collapse(got.stdout) == reference:
                counts["same_output"] += 1
                continue
            pair_key = (row.get("prompt", ""), chosen.strip(),
                        mutant["code"].strip())
            if pair_key in seen:
                continue
            seen.add(pair_key)
            rows.append({
                "prompt": row["prompt"],
                "chosen": chosen.strip() + "\n",
                "rejected": mutant["code"].strip() + "\n",
                "task_id": task["id"], "language": task["language"],
                "mutation": mutant["mutation"],
                "reference": reference,
                "rejected_output": functionprobe.collapse(got.stdout)[:400],
                "origin": "nearmiss:pair", "at": now(),
            })
            counts["accepted"] += 1
            counts.setdefault("families", {})
            family = functioneval.family_of(task)
            counts["families"][family] = counts["families"].get(family, 0) + 1
            per_family_kept[family] = per_family_kept.get(family, 0) + 1
            kept += 1
            if kept >= per_row:
                break
        if log is not None and counts["records"] % 20 == 0:
            log(f"{now()} mined {counts['records']} passing row(s), "
                f"{counts['accepted']} pair(s)")
    return {"rows": rows, "counts": counts}


def write(root: Path, rows: list[dict], counts: dict | None = None) -> dict:
    """Store the pairs beside the night's export, where `load_export` finds them."""
    out = Path(root) / "export"
    out.mkdir(parents=True, exist_ok=True)
    (out / PAIR_FILE).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")
    summary = {**(counts or {}), "pair_rows": len(rows), "written_at": now()}
    (out / SUMMARY_FILE).write_text(json.dumps(summary, indent=2) + "\n",
                                    encoding="utf-8")
    return summary


def mine_night(root: Path | None = None, tasks: list[dict] | None = None,
               **kwargs) -> dict:
    """Mine the night's own passing rows; the default root is the live one."""
    root = Path(root) if root is not None else overnight.output_root()
    pool = tasks if tasks is not None else functionprobe.candidates()
    mined = mine(overnight.records(root), pool, **kwargs)
    return {**mined, "summary": write(root, mined["rows"], mined["counts"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mine near-miss preference pairs from a night's passing rows")
    parser.add_argument("--root", default="",
                        help="night output root (default data/overnight)")
    parser.add_argument("--per-row", type=int, default=1,
                        help="near misses kept per passing answer")
    parser.add_argument("--candidates", type=int, default=MAX_CANDIDATES,
                        help="mutations tried per answer before giving up")
    parser.add_argument("--limit", type=int, default=0,
                        help="passing rows to mine (0 = all)")
    parser.add_argument("--per-family", type=int, default=0,
                        help="pairs one program may contribute (0 = no cap)")
    parser.add_argument("--unbalanced", action="store_true",
                        help="keep record order instead of round-robin by family")
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args(argv)
    result = mine_night(Path(args.root) if args.root else None,
                        per_row=args.per_row, candidates=args.candidates,
                        limit=args.limit, timeout_s=args.timeout,
                        per_family=args.per_family, balanced=not args.unbalanced,
                        log=lambda line: print(line, flush=True))
    print(json.dumps(result["counts"], indent=2))
    print(f"{len(result['rows'])} pair(s) -> "
          f"{(Path(args.root) if args.root else overnight.output_root()) / 'export' / PAIR_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
