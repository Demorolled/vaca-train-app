"""librarysft — verified library builds as SFT rows.

The correction sheet teaches repair: a broken file plus the harness's real error
-> the fixed file. It does not teach "write this small program from scratch".
The library's base and medium builds are exactly that shape — a title, a
description and a whole program — and every one of them has already been
compiled and run by `validate.py`.

Only a `verified` validation record qualifies. A `component`, `failed` or
`timeout` record never becomes a demonstration, and multi-file scaffold sets are
excluded because one SFT row cannot carry a set of siblings.

The rows use the same `{instruction, input, output}` shape as the correction
sheet, so `capture.export_dataset(extra_rows=...)` splits and dedupes them with
one implementation instead of a second dataset format.
"""
from __future__ import annotations

from . import library

ORIGINS = ("base-build", "medium-build")
INSTRUCTION = ("Write a {language} program: {title}. It must compile and run on "
               "its own, standard library only. Reply with the complete file.")


def _one_per_program(rows: list[dict], per_language: int) -> list[dict]:
    """Keep at most `per_language` builds of one program in one language.

    The library asks the same question with a different constant: `sum to 5`,
    `sum to 7`, `sum to 9` are one demonstration three times. Left alone they
    are 90% of the sheet — 2600 rows out of 20 programs — so the model spends
    its gradient on constants and all but never sees a family that appears
    once. One demonstration per program per language is the signal; the extra
    variants are augmentation, not evidence.
    """
    if per_language <= 0:
        return rows
    counts: dict[tuple[str, str], int] = {}
    out: list[dict] = []
    for row in rows:
        meta = row.get("meta") or {}
        key = (meta.get("family") or meta.get("task_id", ""), meta.get("language", ""))
        if counts.get(key, 0) >= per_language:
            continue
        counts[key] = counts.get(key, 0) + 1
        out.append(row)
    return out


def rows(per_language: int = 1) -> list[dict]:
    """One SFT row per verified base/medium build, deduped by instruction+code.

    `per_language` is how many builds of the same program in the same language
    survive (default 1, see `_one_per_program`).
    """
    from .functioneval import family_of  # local: keeps this module off the eval graph

    validation = library.load_validation()
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for task in library.load_tasks():
        if task.get("origin") not in ORIGINS:
            continue
        if library.is_multi_file(task):
            continue
        record = validation.get(task["id"]) or {}
        if record.get("status") != "verified":
            continue
        code = (task.get("code") or "").strip()
        if not code:
            continue
        language = task.get("language", "")
        title = (task.get("title") or "").strip() or "a small program"
        instruction = INSTRUCTION.format(language=language, title=title)
        key = (instruction, code)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "instruction": instruction,
            "input": (task.get("description") or "").strip(),
            "output": code,
            "source": "library:verified-build",
            "meta": {
                "language": language,
                "task_id": task["id"],
                "origin": task.get("origin", ""),
                "bytes": len(code.encode("utf-8")),
                "family": family_of(task),
            },
        })
    return _one_per_program(out, per_language)


def stats(per_language: int = 1) -> dict:
    rows_ = rows(per_language=per_language)
    by_language: dict[str, int] = {}
    by_origin: dict[str, int] = {}
    families: set[str] = set()
    for row in rows_:
        language = row["meta"]["language"]
        origin = row["meta"]["origin"]
        by_language[language] = by_language.get(language, 0) + 1
        by_origin[origin] = by_origin.get(origin, 0) + 1
        families.add(row["meta"].get("family", ""))
    return {"rows": len(rows_), "families": len(families),
            "by_language": by_language, "by_origin": by_origin}
