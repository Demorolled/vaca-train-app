"""preferences — turn tournament verdicts into training pairs.

Tournaments already write `pairs.jsonl` per run: the chosen build, the rejected
build, and the reason. This module collects those runs, dedupes them, and
exports ORPO-ready rows (`prompt`, `chosen`, `rejected`) with a hash split, so
the trainer never sees a val pair it trained on.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import config

PAIRS_FILE = "pairs.jsonl"
PROMPT_TEMPLATE = (
    "### Instruction\n"
    "Write a {language} implementation of: {title}. It must compile and run on "
    "its own, standard library only. Reply with the complete file.\n\n"
    "### Input\n{task}\n\n"
    "### Response\n"
)


def pairs_dir() -> Path:
    path = config.data_dir() / "tournament"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _key(pair: dict) -> str:
    return hashlib.sha256(
        f"{pair.get('task_id','')}\0{pair.get('chosen','')}\0{pair.get('rejected','')}"
        .encode("utf-8")).hexdigest()


def collect_pairs() -> list[dict]:
    """Every judged pair from every tournament run, newest runs included."""
    rows: list[dict] = []
    for path in sorted(pairs_dir().glob("*/pairs.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                pair = json.loads(line)
            except json.JSONDecodeError:
                continue
            if pair.get("chosen") and pair.get("rejected"):
                pair["_run"] = path.parent.name
                rows.append(pair)
    seen: set[str] = set()
    unique: list[dict] = []
    for pair in rows:
        key = _key(pair)
        if key in seen:
            continue
        seen.add(key)
        unique.append(pair)
    return unique


def to_training_pair(pair: dict) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        language=pair.get("language", "unknown"),
        title=(pair.get("title") or "").strip(),
        task=(pair.get("task") or "").strip() or "Make it work.",
    )
    return {
        "prompt": prompt,
        "chosen": pair["chosen"].strip() + "\n",
        "rejected": pair["rejected"].strip() + "\n",
        "meta": {
            "task_id": pair.get("task_id", ""),
            "language": pair.get("language", ""),
            "chosen_style": pair.get("chosen_style", ""),
            "rejected_style": pair.get("rejected_style", ""),
            "chosen_bytes": pair.get("chosen_bytes", 0),
            "rejected_bytes": pair.get("rejected_bytes", 0),
            "reason": (pair.get("reason") or "")[:300],
            "run": pair.get("_run", ""),
        },
    }


def stats() -> dict:
    pairs = collect_pairs()
    by_language: dict[str, int] = {}
    by_style: dict[str, int] = {}
    for pair in pairs:
        lang = pair.get("language", "?")
        by_language[lang] = by_language.get(lang, 0) + 1
        style = pair.get("chosen_style", "?")
        by_style[style] = by_style.get(style, 0) + 1
    return {"pairs": len(pairs), "by_language": by_language, "chosen_styles": by_style}


def export_pairs(val_ratio: float = 0.1) -> dict:
    """Write pairs.jsonl + pairs_{train,val}.jsonl + pairs_meta.json."""
    rows = [to_training_pair(p) for p in collect_pairs()]
    train: list[dict] = []
    val: list[dict] = []
    cut = max(1, round(max(val_ratio, 0.0) * 100))
    for row in rows:
        bucket = int(hashlib.sha256(
            (row["chosen"] + "\0" + row["rejected"]).encode("utf-8")).hexdigest()[:8], 16) % 100
        (val if bucket < cut else train).append(row)
    if not train and val:
        val.sort(key=lambda r: r["chosen"])
        train.append(val.pop())

    out = config.data_dir() / "dataset"
    out.mkdir(parents=True, exist_ok=True)
    (out / PAIRS_FILE).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (out / "pairs_train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in train), encoding="utf-8")
    (out / "pairs_val.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in val), encoding="utf-8")
    meta = {
        "total_pairs": len(rows),
        "train_pairs": len(train),
        "val_pairs": len(val),
        "val_ratio": val_ratio,
        "source": "tournament:preference",
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pairs_path": str(out / PAIRS_FILE),
        "train_path": str(out / "pairs_train.jsonl"),
        "val_path": str(out / "pairs_val.jsonl"),
    }
    (out / "pairs_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta
