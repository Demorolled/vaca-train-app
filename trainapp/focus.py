"""focus — the five language lanes this project trains, measures and grows.

The cut is deliberate and narrow: JavaScript/TypeScript, Python, Java, Go and C
are the languages that carry the internet (browser, server, enterprise back
ends) and operating-system work (Linux is C, Android is Java). A 1.5B coder
trained on everything had its gradient spread across eleven languages and was
never asked to be good at any of them.

Nothing is deleted by this module. The corpora keep every row they were built
with; `library.load_tasks(all_languages=True)` still returns the whole sheet.
What changes is the scope of the questions the model is asked, so the pool, the
gate and the growth loop all measure the same five lanes.

Reversing the cut is an edit to `LANES` and a rebuild of the library index.
"""
from __future__ import annotations

# One lane may cover more than one identifier: TypeScript and JavaScript are
# the same job on the same platform, so a family's siblings can be either and
# still count as separate demonstrations of one program.
LANES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("JavaScript/TypeScript", ("javascript", "typescript")),
    ("Python", ("python",)),
    ("Java", ("java",)),
    ("Go", ("go",)),
    ("C", ("c",)),
)

# Spellings the corpus and prompts use for the same lane.
ALIASES = {
    "ts": "typescript",
    "tsx": "typescript",
    "js": "javascript",
    "jsx": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
    "py": "python",
    "golang": "go",
    "c99": "c",
    "c11": "c",
}

LANGUAGES: tuple[str, ...] = tuple(
    language for _, languages in LANES for language in languages)

_LANE_OF = {language: name for name, languages in LANES for language in languages}

# Present in the corpora, no longer trained on. Named so a report can say what
# the cut costs rather than leaving it unexplained.
DROPPED = ("php", "ruby", "csharp", "cpp", "rust", "kotlin", "swift")


def canonical(language: str) -> str:
    """The corpus's own spelling of a language name."""
    value = (language or "").strip().lower()
    return ALIASES.get(value, value)


def lane(language: str) -> str:
    """The lane a language belongs to, or "" when it is outside the focus."""
    return _LANE_OF.get(canonical(language), "")


def lanes() -> list[str]:
    return [name for name, _ in LANES]


def in_focus(language: str) -> bool:
    return canonical(language) in _LANE_OF


def keep(tasks: list[dict]) -> list[dict]:
    """Rows in the five lanes, in their original order."""
    return [task for task in tasks if in_focus(task.get("language", ""))]


def dropped(tasks: list[dict]) -> list[dict]:
    """Rows outside the focus. Kept for counting, never trained on."""
    return [task for task in tasks if not in_focus(task.get("language", ""))]


def stats(tasks: list[dict]) -> dict:
    """Per-lane counts plus what the cut left out, for a status sheet."""
    counts: dict[str, int] = {name: 0 for name in lanes()}
    for task in tasks:
        name = lane(task.get("language", ""))
        if name:
            counts[name] += 1
    outside: dict[str, int] = {}
    for task in dropped(tasks):
        language = canonical(task.get("language", "")) or "unknown"
        outside[language] = outside.get(language, 0) + 1
    return {
        "lanes": counts,
        "kept": len(tasks) - len(dropped(tasks)),
        "total": len(tasks),
        "outside": dict(sorted(outside.items(), key=lambda kv: -kv[1])),
    }


def describe() -> str:
    return ", ".join(f"{name} ({', '.join(languages)})"
                     for name, languages in LANES)
