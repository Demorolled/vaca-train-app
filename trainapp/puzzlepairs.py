"""puzzlepairs — a caught mutation is a preference pair.

`puzzles.py` builds three candidates for a node in a working app: the real node,
a subtle mutation and a cross-app decoy, then scores them by building and
running the set. This module turns the useful half of that verdict into ORPO
rows:

* the real node is the **chosen** side, the mutation the **rejected** side;
* only puzzles whose real node built (`builds`) and whose mutation was caught by
  the compiler or by a changed stdout (`mutant_detected`) qualify — an inert
  mutation is still correct code, so preferring the original over it would teach
  nothing true;
* the cross-app decoy is not a pair: it is different code for a different app,
  not a worse way to write this node.

The prompt names the node, its purpose and the mutation that was tried, so the
pair tests the discrimination the puzzle scorer actually measured rather than a
generic "write code" request.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import config

PROMPT_TEMPLATE = (
    "### Instruction\n"
    "Choose the {language} {purpose} node from {path} that keeps the app "
    "correct. It must still build and preserve the app's behaviour. Reply with "
    "the complete node.\n\n"
    "### Input\n"
    "Node kind: {kind}\n"
    "Purpose: {purpose}\n"
    "Mutation tried: {mutation}\n\n"
    "### Response\n"
)


def puzzles_dir() -> Path:
    path = config.data_dir() / "puzzles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _key(chosen: str, rejected: str) -> str:
    return hashlib.sha256(f"{chosen}\0{rejected}".encode("utf-8")).hexdigest()


def collect() -> list[dict]:
    """Every strong puzzle verdict, joined to its node text, deduped."""
    seen: set[str] = set()
    out: list[dict] = []
    for run in sorted(puzzles_dir().iterdir()):
        if not run.is_dir():
            continue
        nodes = {row.get("node_id"): row for row in _load_jsonl(run / "puzzles.jsonl")}
        for score in _load_jsonl(run / "scores.jsonl"):
            if not score.get("builds") or not score.get("mutant_detected"):
                continue
            node = nodes.get(score.get("node_id"))
            if not node:
                continue
            chosen = (node.get("correct") or "").strip()
            rejected = (node.get("mutant") or "").strip()
            if not chosen or not rejected or chosen == rejected:
                continue
            key = _key(chosen, rejected)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "task_id": f"puzzle/{run.name}/{score.get('node_id', '')}",
                "language": node.get("language") or score.get("language", "unknown"),
                "path": node.get("path") or score.get("path", ""),
                "kind": node.get("kind") or score.get("kind", ""),
                "purpose": node.get("purpose") or score.get("purpose", "node"),
                "mutation": node.get("mutation") or score.get("mutation", ""),
                "chosen": chosen,
                "rejected": rejected,
                "run": run.name,
                "clean": score.get("clean", 0.0),
            })
    return out


def to_training_pair(puzzle: dict) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        language=puzzle.get("language", "unknown"),
        purpose=puzzle.get("purpose", "node"),
        path=puzzle.get("path", ""),
        kind=puzzle.get("kind", ""),
        mutation=puzzle.get("mutation", ""),
    )
    return {
        "prompt": prompt,
        "chosen": puzzle["chosen"].strip() + "\n",
        "rejected": puzzle["rejected"].strip() + "\n",
        "meta": {
            "task_id": puzzle.get("task_id", ""),
            "language": puzzle.get("language", ""),
            "purpose": puzzle.get("purpose", ""),
            "path": puzzle.get("path", ""),
            "mutation": puzzle.get("mutation", ""),
            "run": puzzle.get("run", ""),
            "clean": puzzle.get("clean", 0.0),
            "source": "puzzle:caught-mutation",
        },
    }


def training_rows() -> list[dict]:
    return [to_training_pair(puzzle) for puzzle in collect()]


def stats() -> dict:
    puzzles = collect()
    by_language: dict[str, int] = {}
    by_purpose: dict[str, int] = {}
    for puzzle in puzzles:
        language = puzzle.get("language", "?")
        purpose = puzzle.get("purpose", "?")
        by_language[language] = by_language.get(language, 0) + 1
        by_purpose[purpose] = by_purpose.get(purpose, 0) + 1
    return {"pairs": len(puzzles), "by_language": by_language, "by_purpose": by_purpose}


def export_pairs(val_ratio: float = 0.1) -> dict:
    """Write `pairs_puzzle.jsonl` plus a hash-split train/val pair of sheets."""
    import hashlib as _hashlib

    rows = training_rows()
    train: list[dict] = []
    val: list[dict] = []
    cut = max(1, round(max(val_ratio, 0.0) * 100))
    for row in rows:
        bucket = int(_hashlib.sha256(
            (row["chosen"] + "\0" + row["rejected"]).encode("utf-8")).hexdigest()[:8], 16) % 100
        (val if bucket < cut else train).append(row)
    out = config.dataset_dir()
    (out / "pairs_puzzle.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (out / "pairs_puzzle_train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in train), encoding="utf-8")
    (out / "pairs_puzzle_val.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in val), encoding="utf-8")
    meta = {"pairs": len(rows), "train_pairs": len(train), "val_pairs": len(val),
            "val_ratio": val_ratio, "source": "puzzle:caught-mutation"}
    (out / "pairs_puzzle_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta
