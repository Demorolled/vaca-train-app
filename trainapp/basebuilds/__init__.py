"""basebuilds — 100 elementary, runnable builds per VACA language.

The library already covers three shapes: *idioms* (rosetta snippets), *app
exports* (multi-file sets) and *grown variants* (model restylings). What it
lacked is volume of the simplest thing of all: a small program that prints a
known result. That is the ground floor of a coding corpus — loops, arithmetic,
conditionals, arrays, strings, functions — and it is also what a battery needs to
tell "the model cannot write a loop in Go" apart from "it cannot write an app".

Each language module exposes `programs() -> list[dict]` with `{title, code}`
entries built from a handful of templates and parameter variants. Every program
is deterministic and prints something, so the harness can prove it by compiling
and running it; nothing here is marked verified on trust — `validate.py` still
has to make the real toolchain agree.

Nothing is imported eagerly: a caller that only wants Go never loads Swift.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import tempfile
from pathlib import Path

from .. import library

# language -> module name in this package
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


def languages() -> list[str]:
    return sorted(MODULES)


def module_for(language: str):
    name = MODULES.get(language)
    if not name:
        raise KeyError(f"no base builds for {language!r}")
    return importlib.import_module(f"{__name__}.{name}")


def programs_for(language: str) -> list[dict]:
    """The language's programs, deduped by code and in a stable order."""
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


def build(languages: list[str] | None = None,
          per_language: int = PER_LANGUAGE) -> list[dict]:
    """Library tasks for every requested language (capped, deduped)."""
    tasks: list[dict] = []
    for language in languages or sorted(MODULES):
        rows = programs_for(language)[:per_language]
        for row in rows:
            tasks.append(library._task(
                origin="base-build",
                language=language,
                title=row["title"],
                code=row["code"],
                runnable=True,
                description=(f"Basic {row['template'] or 'program'} in {language}: "
                             "print the result to standard output."),
                tags=["basics"] + ([row["template"]] if row["template"] else []),
                category="basics",
                source=f"trainapp/basebuilds/{MODULES[language]}.py",
            ))
    return tasks


def counts(languages: list[str] | None = None) -> dict[str, int]:
    return {language: len(programs_for(language))
            for language in (languages or sorted(MODULES))}


def ingest(languages: list[str] | None = None,
           per_language: int = PER_LANGUAGE) -> dict:
    """Rewrite the base-build sheet. Never raises on a bad language module."""
    tasks = build(languages, per_language)
    out = library.library_dir() / library.BASE_FILE
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
        description="Generate and ingest the per-language base builds")
    parser.add_argument("--languages", default="",
                        help="comma separated (default: every language)")
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
