"""plansft — file plans as SFT rows.

The boundary gate measures one thing the training sheet never taught: answer a
planning question with a plan. Every other source is a program — code in, code
out — so the only place a plan ever appeared was the probe that grades it.

The champion's plan responses looped: the same two paths written out fourteen
times, and a nine-file plan for an eight-line allowance. Nothing in the mix had
ever shown what a finished plan looks like, how many lines it has, or where it
stops. This module builds that shape from the library's own file sets — the
paths and the target are ground truth, not invented — and the role after the em
dash is filled from the path.

The rows are capped at the gate's eight-line allowance and deduped per family,
because the library holds the same project shape many times over.
"""
from __future__ import annotations

from . import library

INSTRUCTION = ("Plan the files for this project: {title}. One line per file, each in the "
               "shape <path> (<language>) — <role>. No other text, no fences, and do "
               "not repeat a line.")
MAX_LINES = 8

LANGUAGES = {
    "py": "Python", "js": "JavaScript", "ts": "TypeScript", "go": "Go", "rs": "Rust",
    "java": "Java", "rb": "Ruby", "php": "PHP", "c": "C", "h": "C", "cpp": "C++",
    "cs": "C#", "kt": "Kotlin", "swift": "Swift", "html": "HTML", "css": "CSS",
    "json": "JSON", "md": "Markdown", "toml": "TOML", "yml": "YAML", "yaml": "YAML",
}


def language_of(path: str, fallback: str = "") -> str:
    """The language a path names, else the task's own."""
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return LANGUAGES.get(suffix) or (fallback.title() if fallback else "Text")


def role_of(path: str, target: str = "") -> str:
    """What a file is for, from its name: the plan's free-text half.

    The gate judges the shape of a plan, not whether the words are good, but a
    role that ignores the path teaches nothing about the file being named.
    """
    name = path.rsplit("/", 1)[-1].lower()
    stem = name.rsplit(".", 1)[0]
    if path and path == target:
        return "entry point"
    if name.endswith((".json", ".jsonl")):
        return "data file"
    if name.endswith((".css",)):
        return "styles"
    if name.endswith(".html"):
        return "markup"
    if name.endswith((".md", ".txt", ".rst")):
        return "documentation"
    if name.endswith((".toml", ".yml", ".yaml", ".ini", ".cfg")):
        return "configuration"
    if "test" in stem or "spec" in stem:
        return "tests"
    if stem in ("main", "index", "app", "cli", "server", "game"):
        return "entry point"
    if "/" in path:
        return "helper module"
    return "module"


def _plan(task: dict) -> list[str]:
    """The lines a true plan for this task would have, or [] if too long."""
    files = [f.get("path", "") for f in (task.get("files") or []) if f.get("path")]
    language = str(task.get("language") or "")
    if not files:
        path = task.get("target") or f"main.{_suffix(language)}"
        return [f"{path} ({language_of(path, language)}) — entry point"]
    if len(files) > MAX_LINES:
        # A plan the gate would reject as over-planned teaches the wrong lesson.
        return []
    target = task.get("target") or ""
    return [f"{path} ({language_of(path, language)}) — {role_of(path, target)}"
            for path in files]


def _suffix(language: str) -> str:
    for suffix, name in LANGUAGES.items():
        if name.lower() == language.lower():
            return suffix
    return "txt"


def rows(per_plan: int = 2) -> list[dict]:
    """Distinct plans from the library's verified file sets, multi-file first.

    The library holds the same single-file plan (`main.ts (TypeScript) — entry
    point`) thousands of times; keeping it once per distinct plan, and reading
    the multi-file sets before the single-file builds, is what keeps this lane's
    rows from becoming another copy of the duplication problem.
    """
    from .functioneval import family_of  # local: keeps this module off the eval graph

    tasks = sorted(library.load_tasks(),
                   key=lambda t: (len(t.get("files") or []) == 0, str(t.get("id"))))
    seen: dict[str, int] = {}
    out: list[dict] = []
    for task in tasks:
        lines = _plan(task)
        if not lines:
            continue
        plan = "\n".join(lines)
        if seen.get(plan, 0) >= per_plan:
            continue
        title = (task.get("description") or task.get("title") or "").strip()
        if not title:
            continue
        seen[plan] = seen.get(plan, 0) + 1
        out.append({
            "instruction": INSTRUCTION.format(title=title[:300]),
            "input": "",
            "output": plan,
            "source": "library:plan",
            "meta": {"task_id": task["id"], "family": family_of(task),
                     "files": len(lines), "language": task.get("language", "")},
        })
    return out


def stats() -> dict:
    rows_ = rows()
    return {"rows": len(rows_),
            "distinct_plans": len({r["output"] for r in rows_}),
            "families": len({r["meta"]["family"] for r in rows_}),
            "one_file": sum(1 for r in rows_ if r["meta"]["files"] == 1),
            "max_files": max((r["meta"]["files"] for r in rows_), default=0)}
