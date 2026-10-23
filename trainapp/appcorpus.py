"""appcorpus — VACA's real exports, as multi-file library tasks.

Every other ingest in `library.py` is a *snippet*: one file, judged alone. That
cannot teach or measure scaffolding, because a scaffold is exactly the thing one
file cannot show — a module imports a sibling that must exist, a launcher needs
a class another file declares, two files must not define the same symbol.

VACA already has 500+ real exports under `backend/exports/*/_training.json`,
each with the user request, the planned file list, and the verified files that
were built. This module turns each export into ONE task: the whole file set plus
a `target` — the file a model is asked to write while the others are supplied as
context. `code` stays the target's reference implementation so dedupe, sizing
and the existing prompts keep working, and `files`/`target` mark it as a set.

Nothing is invented: a task is only as good as the export it came from, and
`validate.py` still has to build the set before the task joins the confirmed
library.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from . import library

SOURCE_SUFFIXES = {
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript",
    ".py": "python",
    ".go": "go",
    ".rs": "rust",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
}

# Directories inside an export that are not part of the shipped app: drafts,
# installed packages, build output.
SKIP_DIRS = {"_first-drafts", "node_modules", "dist", "out", "obj", "bin",
             ".git", ".next"}


def exports_root(root: Path | None = None) -> Path:
    return (root or library.vaca_root()) / "backend" / "exports"


def sidecars(root: Path | None = None) -> list[Path]:
    directory = exports_root(root)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*/_training.json"))


def _skipped(relative: Path) -> bool:
    return any(part in SKIP_DIRS for part in relative.parts)


def _collect(export_dir: Path, declared: list[str]) -> list[dict]:
    """The export's own source files, read from disk, drafts and builds excluded."""
    files: list[dict] = []
    seen: set[str] = set()
    for raw in declared:
        relative = Path(str(raw).replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts or _skipped(relative):
            continue
        path = export_dir / relative
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not content.strip():
            continue
        key = relative.as_posix()
        if key in seen:
            continue
        seen.add(key)
        files.append({"path": key, "content": content})
    return files


def task_from_export(sidecar: Path, root: Path | None = None) -> dict | None:
    """One export → one multi-file task, or None when nothing usable is left."""
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict):
        return None

    files = _collect(sidecar.parent, list(meta.get("files") or []))
    files = [f for f in files if Path(f["path"]).suffix.lower() in SOURCE_SUFFIXES]
    if not files:
        return None
    by_path = {f["path"]: f for f in files}

    # A header is compile context, never the file a model should be asked to
    # write: it has no build of its own, so it would only ever validate as a
    # component. Prefer a real translation unit and fall back to a header only
    # when the export has nothing else.
    headers = {".h", ".hpp"}
    planned = [str((p or {}).get("path") or "").replace("\\", "/")
               for p in meta.get("planFiles") or []]
    candidates = [c for c in planned if c in by_path] or sorted(by_path)
    body = [c for c in candidates if Path(c).suffix.lower() not in headers]
    target = (body or candidates)[0]

    language = SOURCE_SUFFIXES[Path(target).suffix.lower()]
    request = str(meta.get("request") or "").strip()
    title = f"{request[:70].strip() or sidecar.parent.name} — {Path(target).name}"
    base = root or library.vaca_root()
    try:
        source = str(sidecar.relative_to(base))
    except ValueError:
        source = str(sidecar)
    return library._task(
        origin="vaca-export",
        language=language,
        title=title,
        code=by_path[target]["content"],
        runnable=True,
        description=request,
        tags=["scaffold", language],
        category="scaffold",
        source=source,
        files=files,
        target=target,
    )


def load_tasks(root: Path | None = None, limit: int = 0) -> list[dict]:
    tasks: list[dict] = []
    seen: set[str] = set()
    for sidecar in sidecars(root):
        task = task_from_export(sidecar, root)
        if not task or task["id"] in seen:
            continue
        seen.add(task["id"])
        tasks.append(task)
        if limit and len(tasks) >= limit:
            break
    return tasks


def ingest(root: Path | None = None, limit: int = 0) -> dict:
    """Rewrite the imported sheet. Never raises: one bad export is skipped."""
    tasks = load_tasks(root, limit)
    by_language: dict[str, int] = {}
    for task in tasks:
        by_language[task["language"]] = by_language.get(task["language"], 0) + 1

    out = library.library_dir() / library.IMPORTED_FILE
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
    return {"tasks": len(tasks), "by_language": by_language, "path": str(out)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest VACA's exports as multi-file scaffold tasks")
    parser.add_argument("--root", default="", help="VACA checkout (default: library.vaca_root())")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser() if args.root else None
    if args.dry_run:
        tasks = load_tasks(root, args.limit)
        print(json.dumps({
            "tasks": len(tasks),
            "sidecars": len(sidecars(root)),
            "multi_file": sum(1 for t in tasks if t.get("files")),
            "by_language": {lang: sum(1 for t in tasks if t["language"] == lang)
                            for lang in sorted({t["language"] for t in tasks})},
        }, indent=2))
        return 0
    print(json.dumps(ingest(root, args.limit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
