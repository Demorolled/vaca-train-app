"""clisets — multi-file CLI programs whose behaviour can be observed.

The judgeable part of the library is thin: of 158 verified sets only ~30 ever
produced a passing function, and most of those are single-purpose scaffolds.
That is the ceiling on `functioneval`, because a fifth of thirty is six sets.

This package adds sets that were *written* to be judgeable: three files, a thin
entry point, a formatting sibling, and a target module whose functions turn
embedded data into a deterministic report. Standard library only, no stdin, no
argv, no clock, no network, no filesystem — the same contract as `basebuilds`,
across files, because cross-file wiring is the thing the model gets wrong.

Nothing is trusted: `validate.py` still has to build and run every set before it
joins the confirmed library.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
from pathlib import Path

from .. import library

MODULES = {
    "python": "python",
    "go": "go",
    "php": "php",
    "ruby": "ruby",
    "javascript": "javascript",
}
ORIGIN = "cli-set"
SHEET = "cli_sets.jsonl"


def _implemented(language: str) -> bool:
    name = MODULES.get(language)
    if not name:
        return False
    try:
        return importlib.util.find_spec(f"{__name__}.{name}") is not None
    except (ImportError, ValueError):
        return False


def languages() -> list[str]:
    """Languages that actually have a generator module on disk."""
    return sorted(language for language in MODULES if _implemented(language))


def missing() -> list[str]:
    return sorted(language for language in MODULES if not _implemented(language))


def module_for(language: str):
    if not _implemented(language):
        raise KeyError(f"no cli sets for {language!r}")
    return importlib.import_module(f"{__name__}.{MODULES[language]}")


def sets_for(language: str) -> list[dict]:
    """Well-formed sets only: three files, an entry, a target that is not it."""
    out: list[dict] = []
    seen: set[str] = set()
    for raw in module_for(language).sets():
        files = [{"path": str(f.get("path", "")), "content": str(f.get("content", ""))}
                 for f in (raw.get("files") or [])]
        target = str(raw.get("target") or "")
        paths = [f["path"] for f in files]
        if len(files) < 3 or not target or target not in paths:
            continue
        if not any(Path(p).stem in {"main", "index", "app"} for p in paths):
            continue
        if target == next(p for p in paths if Path(p).stem in {"main", "index", "app"}):
            continue
        key = "\0".join(f["path"] + f["content"] for f in files)
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": raw.get("title") or f"{language} cli set",
                    "description": raw.get("description") or "",
                    "family": raw.get("family") or "cli",
                    "files": files, "target": target})
    return out


def build(only: list[str] | None = None) -> list[dict]:
    """Library tasks for the requested languages (implemented ones only)."""
    tasks: list[dict] = []
    for language in only or languages():
        for row in sets_for(language):
            code = next(f["content"] for f in row["files"] if f["path"] == row["target"])
            tasks.append(library._task(
                origin=ORIGIN,
                language=language,
                title=row["title"],
                code=code,
                runnable=True,
                description=row["description"] or
                (f"A three-file {language} CLI: the entry point, a formatter, and the "
                 "module that turns embedded data into a deterministic report."),
                tags=["cli-set", row["family"]],
                category="cli-set",
                # The family slug is what makes the same program in another
                # language a sibling; without it every set was its own family.
                family=row["family"],
                source=f"trainapp/clisets/{MODULES[language]}.py",
                files=row["files"],
                target=row["target"],
            ))
    return tasks


def write(only: list[str] | None = None) -> dict:
    """Write the sheet the library ingests, and report what is in it."""
    tasks = build(only)
    path = library.library_dir() / SHEET
    path.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in tasks),
                    encoding="utf-8")
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task["language"]] = counts.get(task["language"], 0) + 1
    return {"sets": len(tasks), "by_language": counts, "path": str(path)}


def ingest() -> list[dict]:
    path = library.library_dir() / SHEET
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("code") and row.get("files"):
            rows.append(row)
    return rows


def counts(only: list[str] | None = None) -> dict[str, int]:
    return {language: len(sets_for(language))
            for language in (only or languages())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and ingest the CLI sets")
    parser.add_argument("--language", default="", help="comma-separated filter")
    parser.add_argument("--build", action="store_true", help="re-ingest the library")
    parser.add_argument("--show", action="store_true", help="print the sheet summary")
    args = parser.parse_args(argv)

    only = [x.strip() for x in args.language.split(",") if x.strip()] or None
    print(json.dumps(write(only), indent=2))
    print(json.dumps({"counts": counts(only), "missing": missing()}, indent=2))
    if args.build:
        index = library.build()
        print(json.dumps({"library_total": index["total"],
                          "cli_sets": index["by_origin"].get(ORIGIN, 0)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
