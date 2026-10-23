"""scaffoldsft — verified app file-sets as SFT rows: write one file that fits.

The correction sheet teaches repair, and `librarysft` teaches "write this small
program from scratch". Neither teaches the thing the battery fails on: a file
that has to compile and run inside a project that already has its imports,
exports and call sites. That is what the `vaca-export` sets are, and they already
carry a proof — `validate.py` built and ran the whole set.

Each row is one target file with its siblings in the input, built from
`battery.scaffold_instruction` / `battery.scaffold_input`, so a training row and a
battery task are the same prompt. `battery.scaffold_prompt` composes the same two
halves through the same template, which is why the row is written as
instruction/input rather than a pre-flattened string.

The sets are hash-split by task id and only `TRAIN_SHARE` of them are exported:
the battery must keep enough scaffold tasks that this sheet never taught, or the
next battery run measures memorisation again.
"""
from __future__ import annotations

import hashlib

from . import battery, library

TRAIN_SHARE = 75  # percent of verified sets that may be trained on
SOURCE = "library:verified-set"


def bucket(task_id: str) -> int:
    """The same 0-99 bucket the SFT split uses, keyed by task id."""
    return int(hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:8], 16) % 100


def is_trainable(task: dict, share: int = TRAIN_SHARE) -> bool:
    return bucket(task.get("id", "")) < max(0, min(100, share))


def rows(share: int = TRAIN_SHARE) -> list[dict]:
    """One SFT row per verified, trainable multi-file set."""
    validation = library.load_validation()
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for task in library.load_tasks():
        if not library.is_multi_file(task):
            continue
        if (validation.get(task.get("id", "")) or {}).get("status") != "verified":
            continue
        if not is_trainable(task, share):
            continue
        code = (task.get("code") or "").strip()
        if not code:
            continue
        target = task.get("target", "")
        if target not in {entry.get("path") for entry in task.get("files") or []}:
            # A target that is not in the set cannot be a scaffold fill.
            continue
        instruction = battery.scaffold_instruction(task)
        key = (instruction, code)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "instruction": instruction,
            "input": battery.scaffold_input(task),
            "output": code,
            "source": SOURCE,
            "meta": {
                "task_id": task.get("id", ""),
                "language": task.get("language", ""),
                "target": target,
                "siblings": max(0, len(task.get("files") or []) - 1),
                "bytes": len(code.encode("utf-8")),
            },
        })
    return out
