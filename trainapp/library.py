"""library — VACA's confirmed code, ingested as validation/tournament tasks.

Three real sources, read-only:

  data/code-bible/*.py       904 TypeScript/React chunks (components; compile-check only)
  backend/src/knowledge/rosettaCorpus.json  313 complete programs across 11 languages
  backend/src/knowledge/curatedLanguagePatterns.ts  6 hand-written non-TS idioms

Nothing is invented here. A task only becomes part of the *confirmed* library
after validate.py has run it through the real toolchain.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from . import config

DEFAULT_VACA_ROOT = Path.home() / "Desktop" / "visual-ai-architect"
TASK_FILE = "tasks.jsonl"
GROWN_FILE = "grown.jsonl"
IMPORTED_FILE = "app_tasks.jsonl"
BASE_FILE = "base_builds.jsonl"
MEDIUM_FILE = "medium_builds.jsonl"
CLI_FILE = "cli_sets.jsonl"
INDEX_FILE = "index.json"
VALIDATION_FILE = "validation.jsonl"
PUZZLE_FILE = "puzzle_scores.jsonl"


def vaca_root() -> Path:
    return Path(os.environ.get("VACA_ROOT") or DEFAULT_VACA_ROOT).expanduser()


def library_dir() -> Path:
    path = config.data_dir() / "library"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tasks_path() -> Path:
    return library_dir() / TASK_FILE


def grown_path() -> Path:
    return library_dir() / GROWN_FILE


def validation_path() -> Path:
    return library_dir() / VALIDATION_FILE


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:80]


def _code_hash(language: str, code: str) -> str:
    return hashlib.sha256(f"{language}\0{code}".encode("utf-8")).hexdigest()


def _task(*, origin: str, language: str, title: str, code: str, runnable: bool,
          description: str = "", tags: list[str] | None = None,
          category: str = "", iface: str = "", source: str = "",
          files: list[dict] | None = None, target: str = "",
          family: str = "") -> dict:
    """One library entry.

    A single-file task carries `code` and nothing else. A *multi-file* task (a
    real VACA export) additionally carries `files` — every file of the set — and
    `target`, the path inside it that a model is asked to write. `code` stays the
    target's reference implementation, so dedupe, sizes and prompts keep working
    for both kinds.
    """
    task = {
        "id": f"{origin}/{slug(title)}-{_code_hash(language, code)[:8]}",
        "origin": origin,
        "language": language,
        "title": title,
        "description": description,
        "code": code,
        "iface": iface,
        "family": family,
        "tags": tags or [],
        "category": category,
        "runnable": runnable,
        "source": source,
    }
    if files:
        task["files"] = [{"path": str(f.get("path", "")),
                          "content": str(f.get("content", ""))} for f in files]
        task["target"] = target or ""
    return task


def is_multi_file(task: dict) -> bool:
    """True when the task is a file set (a scaffold), not a lone program."""
    return bool(task.get("files")) and bool(task.get("target"))


def ingest_base() -> list[dict]:
    """The elementary per-language programs (see basebuilds/).

    Kept in their own sheet because they are generated rather than scraped, and
    regenerating them must not disturb the scraped tasks.
    """
    path = library_dir() / BASE_FILE
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("code"):
            rows.append(row)
    return rows


def ingest_medium() -> list[dict]:
    """The generated medium-complexity programs (see mediumbuilds/)."""
    return _read_sheet(MEDIUM_FILE)


def _read_sheet(name: str) -> list[dict]:
    path = library_dir() / name
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("code"):
            rows.append(row)
    return rows


def ingest_clisets() -> list[dict]:
    """Generated multi-file CLI sets (see `clisets/`), kept in their own sheet."""
    path = library_dir() / CLI_FILE
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


def ingest_imported() -> list[dict]:
    """Multi-file tasks ingested from VACA's real exports (see appcorpus.py).

    Kept in its own sheet so `build()` never regenerates or deletes them; they
    are re-ingested explicitly because the exports they come from keep changing.
    """
    path = library_dir() / IMPORTED_FILE
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("code"):
            rows.append(row)
    return rows


def ingest_code_bible(root: Path | None = None) -> list[dict]:
    """The 38 code-bible data files; every chunk is TypeScript today."""
    root = root or vaca_root()
    directory = root / "data" / "code-bible"
    if not directory.is_dir():
        return []
    tasks: list[dict] = []
    for path in sorted(directory.glob("*.py")):
        namespace: dict = {}
        try:
            exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
        except (SyntaxError, ValueError):
            continue
        for chunk in namespace.get("CHUNKS", []) or []:
            code = chunk.get("code") or ""
            if not code.strip():
                continue
            language = (chunk.get("lang") or "typescript").lower()
            tasks.append(_task(
                origin="code-bible",
                language=language,
                title=chunk.get("name") or chunk.get("id") or path.stem,
                code=code,
                iface=chunk.get("iface") or "",
                runnable=False,  # a React component is compile-checked, not executed
                description=" — ".join(p for p in (chunk.get("when"), chunk.get("why")) if p),
                tags=list(chunk.get("tags") or []),
                category=chunk.get("category") or "",
                source=str(path.relative_to(root)),
            ))
    return tasks


def ingest_rosetta(root: Path | None = None) -> list[dict]:
    """313 complete, standard-library-only programs — the executable corpus."""
    root = root or vaca_root()
    path = root / "backend" / "src" / "knowledge" / "rosettaCorpus.json"
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    tasks: list[dict] = []
    for row in rows if isinstance(rows, list) else []:
        code = row.get("code") or ""
        if not code.strip():
            continue
        tasks.append(_task(
            origin="rosetta",
            language=(row.get("language") or "").lower(),
            title=row.get("title") or "",
            code=code,
            runnable=True,
            description=row.get("description") or "",
            tags=[t for t in (row.get("tags") or []) if isinstance(t, str)],
            category=row.get("category") or "",
            source=str(path.relative_to(root)),
        ))
    return tasks


_CURATED_SCRIPT = """
import {{ CURATED_LANGUAGE_PATTERNS }} from {module};
console.log(JSON.stringify(CURATED_LANGUAGE_PATTERNS));
"""


def ingest_curated(root: Path | None = None) -> list[dict]:
    """The 6 curated non-TS patterns, extracted by actually importing the module.

    tsx evaluates the real TypeScript, so escape sequences in the snippets are
    exactly what the app stores — a regex over the source would corrupt them.
    """
    root = root or vaca_root()
    module = root / "backend" / "src" / "knowledge" / "curatedLanguagePatterns.ts"
    tsx = root / "node_modules" / ".bin" / "tsx"
    if not module.exists():
        return []
    rows: list[dict] = []
    if tsx.exists():
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "extract.ts"
            script.write_text(_CURATED_SCRIPT.format(module=json.dumps(str(module))),
                              encoding="utf-8")
            try:
                done = subprocess.run(
                    [str(tsx), str(script)], capture_output=True, text=True,
                    timeout=90, cwd=str(root), stdin=subprocess.DEVNULL,
                )
                if done.returncode == 0 and done.stdout.strip():
                    rows = json.loads(done.stdout.strip().splitlines()[-1])
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
                rows = []
    if not rows:
        return []
    tasks: list[dict] = []
    for row in rows:
        code = row.get("code") or ""
        if not code.strip():
            continue
        tasks.append(_task(
            origin="curated",
            language=(row.get("language") or "").lower(),
            title=row.get("title") or "",
            code=code,
            runnable=True,
            description=row.get("description") or "",
            tags=list(row.get("tags") or []),
            category=row.get("category") or "",
            source=str(module.relative_to(root)),
        ))
    return tasks


def build() -> dict:
    """Ingest every source, dedupe by (language, code), write the task sheet."""
    tasks = ingest_code_bible() + ingest_rosetta() + ingest_curated()
    seen: set[str] = set()
    unique: list[dict] = []
    for task in tasks:
        key = _code_hash(task["language"], task["code"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(task)
    # Rows the growth loop proved and rows ingested from VACA's exports are part
    # of the library too; rebuilding the sources must never delete them, and the
    # index has to count them or the UI reports a total that no loader agrees
    # with.
    for task in [*load_grown(), *ingest_imported(), *ingest_base(), *ingest_medium(),
                 *ingest_clisets()]:
        key = _code_hash(task["language"], task["code"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(task)

    with tasks_path().open("w", encoding="utf-8") as handle:
        for task in unique:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")

    index = {"total": len(unique), "by_language": {}, "by_origin": {},
             "runnable": sum(1 for t in unique if t["runnable"]),
             "multi_file": sum(1 for t in unique if is_multi_file(t)),
             "vaca_root": str(vaca_root())}
    for task in unique:
        index["by_language"][task["language"]] = index["by_language"].get(task["language"], 0) + 1
        index["by_origin"][task["origin"]] = index["by_origin"].get(task["origin"], 0) + 1
    (library_dir() / INDEX_FILE).write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return index


def load_grown() -> list[dict]:
    path = grown_path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("code"):
            rows.append(row)
    return rows


def append_grown(task: dict) -> tuple[bool, str]:
    """Add a generated task only if its code is not already in the library."""
    code = task.get("code") or ""
    language = task.get("language") or ""
    if not code.strip():
        return False, "empty code"
    existing = {_code_hash(t.get("language", ""), t.get("code", ""))
                for t in load_tasks()}
    key = _code_hash(language, code)
    if key in existing:
        return False, "code already in the library"
    with grown_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(task, ensure_ascii=False) + "\n")
    return True, "added"


def load_tasks() -> list[dict]:
    """Base sources + grown rows, deduped by (language, code)."""
    rows: list[dict] = []
    path = tasks_path()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows.extend(load_grown())
    rows.extend(ingest_imported())
    rows.extend(ingest_base())
    rows.extend(ingest_medium())
    rows.extend(ingest_clisets())
    seen: set[str] = set()
    unique: list[dict] = []
    for row in rows:
        key = _code_hash(row.get("language", ""), row.get("code", ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def load_validation() -> dict[str, dict]:
    """Latest validation record per task id."""
    path = validation_path()
    latest: dict[str, dict] = {}
    if not path.exists():
        return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("id"):
            latest[row["id"]] = row
    return latest


def load_puzzle_scores() -> dict[str, dict]:
    """Per-app cleanliness scores from the puzzle scorer (`puzzles.py`).

    Ranking exemplars is the point: the app's retrieval should prefer the nodes
    that build, behave and resist a plausible edit, not merely the newest ones.
    """
    path = library_dir() / PUZZLE_FILE
    if not path.exists():
        return {}
    scores: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("task_id"):
            scores[row["task_id"]] = row
    return scores


def confirmed() -> list[dict]:
    """Only tasks whose real toolchain run passed."""
    results = load_validation()
    return [t for t in load_tasks() if results.get(t["id"], {}).get("status") == "verified"]


def stats() -> dict:
    tasks = load_tasks()
    results = load_validation()
    index = {}
    index_path = library_dir() / INDEX_FILE
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            index = {}
    by_status: dict[str, int] = {}
    by_origin: dict[str, int] = {}
    verified_by_language: dict[str, int] = {}
    for task in tasks:
        status = results.get(task["id"], {}).get("status", "unvalidated")
        by_status[status] = by_status.get(status, 0) + 1
        origin = task.get("origin", "unknown")
        by_origin[origin] = by_origin.get(origin, 0) + 1
        if status == "verified":
            lang = task["language"]
            verified_by_language[lang] = verified_by_language.get(lang, 0) + 1
    # The index on disk is written at ingest time; grown rows land afterwards,
    # so the live counts always come from the tasks actually loaded now.
    index = {**index, "total": len(tasks), "by_origin": by_origin,
             "runnable": sum(1 for t in tasks if t.get("runnable")),
             "multi_file": sum(1 for t in tasks if is_multi_file(t))}
    scores = load_puzzle_scores()
    if scores:
        index = {**index, "puzzle_scored": len(scores)}
    return {
        "index": index,
        "tasks": len(tasks),
        "by_status": by_status,
        "verified_by_language": verified_by_language,
        "confirmed": sum(verified_by_language.values()),
        "puzzle_scores": scores,
    }
