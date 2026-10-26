"""buildfix — repair rows mined from the night's own build failures.

The held-out families that never build (binary search trace, ISBN checksum, LRU
cache, vending change …) are the metric: they cannot be trained on without
teaching the answer. What *can* be trained on is the failure itself. Every night
attempt records the function it asked for, the compiler's own words, and the
function the model wrote; 3,008 of them in the current corpus did not build.

Two shapes come out of that record:

* an SFT row whose instruction quotes the build error and whose answer is the
  library's own working function for the same ask, so the model learns "this
  build complaint means this correction", not just "here is another program";
* a preference pair with the working function chosen over the broken reply, for
  the same reason `nearmiss` exists: the night's pairs teach compiles-versus-
  does-not-compile, while these teach this-answer-versus-that-answer.

Not every recorded failure is the model's. Some are the harness: `find_functions`
on PHP sometimes asks for a `foreach` block instead of a function, and splicing a
whole function over a loop body produces "Cannot redeclare". Those rows are
dropped rather than taught, and rows with no diagnostic at all are dropped too —
a failure with no reason cannot be repaired from.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config, functioneval, functionprobe, library, overnight

INSTRUCTION = (
    "This function for `{target}` ({language}) fails to build:\n"
    "---\n{error}\n---\n"
    "Rewrite it so the whole project builds and runs. Reply with the function "
    "only: no fences, no prose, and do not change the signature.")

# What `find_functions` returns when it has matched a block instead of a
# declaration: asking a model to "write this foreach" cannot produce a build.
CONTROL = re.compile(r"^\s*(foreach|for|if|while|switch|case|try|catch|else|do)\b")
DECLARATION = re.compile(
    r"^\s*(@|\[|#|public|private|protected|internal|static|final|abstract|async|"
    r"export|default|synchronized|inline|template|func|fn|def|function|"
    r"sub|void|int|char|float|double|long|bool|boolean|string|let|const|var|"
    r"class|struct|type|interface|module|namespace|[A-Za-z_][\w:<>,.\[\]]*\s+\w+\s*\()")


def records(root: Path | None = None) -> list[dict]:
    """Every night attempt with a reply, newest directory first, deduped."""
    base = Path(root) if root is not None else config.data_dir() / "overnight"
    out: list[dict] = []
    seen: set[tuple] = set()
    for path in sorted(base.glob("*/samples.jsonl")) + sorted(base.glob("*/failures.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            key = (row.get("task_id"), row.get("function"), row.get("reply"),
                   row.get("at"))
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
    return out


def usable(row: dict) -> tuple[bool, str]:
    """Whether a failed attempt can become a repair row, and why not."""
    if row.get("compile") is not False:
        return False, "did not fail to build"
    if not (row.get("reply") or "").strip():
        return False, "no reply recorded"
    if not (row.get("error") or "").strip():
        return False, "no diagnostic"
    asked = row.get("function") or ""
    if not asked.strip():
        return False, "no function asked"
    if CONTROL.match(asked) or not DECLARATION.match(asked):
        return False, "asked a control block, not a function"
    return True, ""


def _reference(task: dict, signature: str) -> str:
    """The library's own working version of the function the row asked for."""
    target = functionprobe.target_of(task)
    if target is None:
        return ""
    for fn in functionprobe.find_functions(task["language"], target["content"]):
        if fn["signature"].strip() == signature.strip():
            return fn["block"].rstrip() + "\n"
    return ""


def _error(row: dict) -> str:
    """The diagnostic, trimmed to what a reader (and a prompt) needs."""
    text = " ".join((row.get("error") or "").split())
    return text[:400]


def rows(limit: int = 0, root: Path | None = None) -> list[dict]:
    """One SFT row per (set, function): quote the build error, answer correctly."""
    tasks = {t["id"]: t for t in library.load_tasks(all_languages=True)}
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in records(root):
        ok, _why = usable(row)
        if not ok:
            continue
        task = tasks.get(row.get("task_id") or "")
        if task is None:
            continue
        key = (task["id"], row["function"].strip())
        if key in seen:
            continue
        answer = _reference(task, row["function"])
        if not answer:
            continue
        seen.add(key)
        out.append({
            "instruction": INSTRUCTION.format(
                target=task.get("target", ""), language=task.get("language", ""),
                error=_error(row)),
            "input": row.get("input") or "",
            "output": answer,
            "source": "buildfix:repair",
            "meta": {"task_id": task["id"], "language": task.get("language", ""),
                     "family": functioneval.family_of(task),
                     "function": row["function"].strip(),
                     "error": _error(row)[:200]},
        })
        if limit and len(out) >= limit:
            break
    return out + _cached("broken_rows.jsonl")[:limit or None]


def pairs(limit: int = 0, root: Path | None = None) -> list[dict]:
    """The same ask: the working function chosen, the model's broken reply rejected.

    Both halves are narrowed to the asked function, so the pair is a comparison
    of two answers to one question rather than of two documents.
    """
    tasks = {t["id"]: t for t in library.load_tasks(all_languages=True)}
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in records(root):
        ok, _why = usable(row)
        if not ok:
            continue
        task = tasks.get(row.get("task_id") or "")
        if task is None:
            continue
        language = task.get("language", "")
        rejected = functionprobe.extract_block(language, row["reply"], row["function"])
        chosen = _reference(task, row["function"])
        if not chosen or not rejected.strip() or rejected.strip() == chosen.strip():
            continue
        key = (task["id"], row["function"].strip())
        if key in seen:
            continue
        seen.add(key)
        prompt = functionprobe.prompt_for(task, {
            "signature": row["function"], "block": "", "lines": 0, "start": 0,
            "end": 0})
        out.append({
            "prompt": prompt,
            "chosen": chosen,
            "rejected": rejected.rstrip() + "\n",
            "meta": {"task_id": task["id"], "source": "buildfix:pair",
                     "language": language, "family": functioneval.family_of(task),
                     "error": _error(row)[:200]},
        })
        if limit and len(out) >= limit:
            break
    return out + _cached("broken_pairs.jsonl")[:limit or None]


def variants(language: str, block: str) -> list[tuple[str, str]]:
    """One-edit breakages of a working function, best first.

    These are proposals, not facts: what makes a row is the toolchain rejecting
    the result, so a mutation that still builds is silently dropped.
    """
    lines = block.splitlines()
    if len(lines) < 2:
        return []
    out: list[tuple[str, str]] = []
    last = lines[-1].strip()
    if last.endswith("}") or last == "end" or last.startswith("end"):
        out.append(("drop-closing", "\n".join(lines[:-1]) + "\n"))
    elif last:
        # No closer to drop (Python, Ruby without a trailing `end`): the last
        # statement is the body's only line, so removing it leaves a signature
        # with nothing under it.
        out.append(("drop-body", "\n".join(lines[:-1]) + "\n"))
    for index in range(1, len(lines)):
        if ";" in lines[index]:
            edited = list(lines)
            edited[index] = edited[index].replace(";", "", 1)
            out.append(("drop-semicolon", "\n".join(edited) + "\n"))
            break
    for index in range(1, len(lines)):
        if ")" in lines[index]:
            edited = list(lines)
            edited[index] = edited[index].replace(")", "", 1)
            out.append(("drop-paren", "\n".join(edited) + "\n"))
            break
    for index in range(1, len(lines)):
        match = re.search(r"\b(\d+)\b", lines[index])
        if match:
            edited = list(lines)
            edited[index] = (edited[index][:match.start()] + '"x"'
                             + edited[index][match.end():])
            out.append(("type-swap", "\n".join(edited) + "\n"))
            break
    return out


def cache_dir() -> Path:
    return config.data_dir() / "buildfix"


def generate(limit: int = 200, per_function: int = 2, timeout_s: float = 25,
             log=None) -> dict:
    """Break trainable sets on purpose and keep the failures the compiler names.

    The night's own failures yield only 30 trainable rows, because the sets that
    fail hardest are the held-out ones. This manufactures the same lesson from
    the trainable side: a working function, one edit, the toolchain's objection,
    and the working function as the answer. Proof-gated — a mutation that still
    builds is discarded, so every row carries a real diagnostic.
    """
    log = log or (lambda line: None)
    pool = functionprobe.pool_candidates()
    held = functioneval.holdout_families(pool)
    rows: list[dict] = []
    pairs: list[dict] = []
    tried = kept = 0
    by_mutation: dict[str, int] = {}
    for task in pool:
        if functioneval.family_of(task) in held:
            continue
        target = functionprobe.target_of(task)
        if target is None:
            continue
        for fn in functionprobe.probe_functions(task, 2):
            got = 0
            for name, block in variants(task["language"], fn["block"]):
                tried += 1
                result = functionprobe.run_set(
                    task, functionprobe.splice(target["content"], fn, block),
                    timeout_s, compile_only=True)
                if result.ok:
                    continue
                error = functionprobe.diagnostic(result)
                rows.append({
                    "instruction": INSTRUCTION.format(
                        target=task.get("target", ""),
                        language=task.get("language", ""), error=error),
                    "input": "",
                    "output": fn["block"].rstrip() + "\n",
                    "source": "buildfix:broken",
                    "meta": {"task_id": task["id"],
                             "language": task.get("language", ""),
                             "family": functioneval.family_of(task),
                             "function": fn["signature"].strip(),
                             "mutation": name, "error": error[:200]},
                })
                pairs.append({
                    "prompt": functionprobe.prompt_for(task, fn),
                    "chosen": fn["block"].rstrip() + "\n",
                    "rejected": block.rstrip() + "\n",
                    "meta": {"task_id": task["id"], "source": "buildfix:broken-pair",
                             "language": task.get("language", ""),
                             "family": functioneval.family_of(task),
                             "mutation": name, "error": error[:200]},
                })
                by_mutation[name] = by_mutation.get(name, 0) + 1
                kept += 1
                got += 1
                if got >= per_function:
                    break
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    out = cache_dir()
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (("broken_rows.jsonl", rows), ("broken_pairs.jsonl", pairs)):
        (out / name).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in data),
            encoding="utf-8")
    summary = {"tried": tried, "kept": kept, "rows": len(rows),
               "pairs": len(pairs), "by_mutation": by_mutation,
               "path": str(out)}
    log(f"buildfix: {len(rows)} rows from {tried} mutations {by_mutation}")
    return summary


def _cached(name: str) -> list[dict]:
    path = cache_dir() / name
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def stats(root: Path | None = None) -> dict:
    """Why the recorded failures were kept or dropped, for the status sheet."""
    counts: dict[str, int] = {}
    for row in records(root):
        ok, why = usable(row)
        key = "kept" if ok else why
        counts[key] = counts.get(key, 0) + 1
    return {"attempts": sum(counts.values()), "by_reason": counts,
            "rows": len(rows(root=root)), "pairs": len(pairs(root=root))}
