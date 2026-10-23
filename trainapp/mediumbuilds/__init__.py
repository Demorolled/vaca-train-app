"""mediumbuilds — 100 multi-function, data-structure programs per language.

The base builds prove a model can write a loop and print. That is the floor, and
a model that clears it tells you nothing about whether it can hold a small design
in its head: a record type, a dictionary, a class with invariants, a parse then a
report. This package is the next rung — the same thirteen languages, the same
deterministic one-file-shape, but each program has several functions and a real
data structure between them.

Same contract as `basebuilds`: standard library only, no stdin, no files, no
clock, no randomness, deterministic output, and nothing is trusted — `validate.py`
still has to compile and run every one before it joins the confirmed library.

Written so far: python, cpp, java, csharp, go (100 each). `MODULES` names the
full target and `missing()` reports what is still absent, so an ingest can never
count a language whose generator does not exist yet.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path

from .. import library

MODULES = {
    "python": "python",
    "go": "go",
    "rust": "rust",
    "c": "c",
    "cpp": "cpp",
    "java": "java",
    "csharp": "csharp",
    "javascript": "javascript",
    "typescript": "typescript",
    "php": "php",
    "ruby": "ruby",
    "swift": "swift",
    "kotlin": "kotlin",
}

PER_LANGUAGE = 100
ORIGIN = "medium-build"


def _implemented(language: str) -> bool:
    name = MODULES.get(language)
    if not name:
        return False
    try:
        return importlib.util.find_spec(f"{__name__}.{name}") is not None
    except (ImportError, ValueError):
        return False


def languages() -> list[str]:
    """Languages that actually have a generator module on disk.

    MODULES is the target: every language VACA can build. This list is what is
    written today, so callers never trip over a half-landed language.
    """
    return sorted(language for language in MODULES if _implemented(language))


def missing() -> list[str]:
    return sorted(language for language in MODULES if not _implemented(language))


def module_for(language: str):
    name = MODULES.get(language)
    if not name or not _implemented(language):
        raise KeyError(f"no medium builds for {language!r}")
    return importlib.import_module(f"{__name__}.{name}")


def programs_for(language: str) -> list[dict]:
    seen: set[str] = set()
    rows: list[dict] = []
    for row in module_for(language).programs():
        code = (row.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append({"title": row.get("title") or f"{language} program {len(rows) + 1}",
                     "code": code + "\n",
                     "template": row.get("template") or ""})
    return rows


def build(only: list[str] | None = None,
          per_language: int = PER_LANGUAGE) -> list[dict]:
    """Library tasks for the requested languages (implemented ones only)."""
    tasks: list[dict] = []
    for language in only or languages():
        for row in programs_for(language)[:per_language]:
            tasks.append(library._task(
                origin=ORIGIN,
                language=language,
                title=row["title"],
                code=row["code"],
                runnable=True,
                description=(f"Medium {row['template'] or 'program'} in {language}: "
                             "several functions and a data structure, printing a "
                             "deterministic report."),
                tags=["medium"] + ([row["template"]] if row["template"] else []),
                category="medium",
                source=f"trainapp/mediumbuilds/{MODULES[language]}.py",
            ))
    return tasks


def counts(only: list[str] | None = None) -> dict[str, int]:
    return {language: len(programs_for(language))
            for language in (only or languages())}


def ingest(only: list[str] | None = None,
           per_language: int = PER_LANGUAGE) -> dict:
    tasks = build(only, per_language)
    out = library.library_dir() / library.MEDIUM_FILE
    payload = "".join(json.dumps(t, ensure_ascii=False) + "\n" for t in tasks)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                         dir=str(out.parent), suffix=".tmp")
    try:
        with handle:
            handle.write(payload)
        os.replace(handle.name, out)
    except OSError:
        Path(handle.name).unlink(missing_ok=True)
        raise
    by_language: dict[str, int] = {}
    for task in tasks:
        by_language[task["language"]] = by_language.get(task["language"], 0) + 1
    return {"tasks": len(tasks), "by_language": by_language, "path": str(out)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate and ingest the per-language medium builds")
    parser.add_argument("--languages", default="")
    parser.add_argument("--per-language", type=int, default=PER_LANGUAGE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    chosen = [s.strip() for s in args.languages.split(",") if s.strip()] or None
    if args.dry_run:
        print(json.dumps(counts(chosen), indent=2))
        return 0
    print(json.dumps(ingest(chosen, args.per_language), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
