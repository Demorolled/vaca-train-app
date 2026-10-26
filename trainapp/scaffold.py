"""scaffold — copy the layout reasoning other connections already worked out.

VACA has more than one connection: `llm` answers and draws nodes, `builder`
plans and writes whole apps, `judge` ranks two builds. Point `builder` at
another endpoint and the same briefs get built by a different model, captured
side by side in `data/builder/pool.jsonl`, labelled by model.

What that pool holds that nothing else does is the *scaffolding reasoning*: for
one brief, which files a model decided a Go or TypeScript app needs, what it
made the entry, how it said the program is invoked, which config file it
believed the lane required, and the words it used to justify the layout. The
plan JSON records the decisions; `plan_reasoning` and `files_reasoning` record
the thinking behind them.

This module copies that reasoning out of the pool and into the prompt the next
builder reads, so a layout one connected model worked out is available to the
next one without any weights being touched. Copy, not distill: nothing here
becomes a training row — it becomes prompt text, and it is attributed to the
model that produced it so a wrong convention can be traced and dropped.

The pool is the only source. A language no connection has built yet has no
section, and the prompt is exactly what it was before.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config

# Extensions that are a project's *configuration*, not its source. This is the
# half of a scaffold the file set itself cannot tell you it needs: a lane that
# builds through a generated .csproj does not want one shipped, and a lane that
# refuses Cargo.toml needs to know that before it writes one.
CONFIG_NAMES = {
    "go.mod", "go.sum", "package.json", "package-lock.json", "tsconfig.json",
    "cargo.toml", "cargo.lock", "cmakelists.txt", "makefile", "pom.xml",
    "build.gradle", "build.gradle.kts", "settings.gradle", "requirements.txt",
    "pyproject.toml", "gemfile", "composer.json", "swift package.swift",
}
CONFIG_SUFFIXES = (".csproj", ".sln", ".fsproj", ".vbproj", ".cabal", ".props")

MAX_MODELS = 4
MAX_REASONING = 420
MAX_LAYOUT = 12


def is_config(path: str) -> bool:
    name = Path(path).name.lower()
    return name in CONFIG_NAMES or name.endswith(CONFIG_SUFFIXES)


def pool_path() -> Path:
    return config.data_dir() / "builder" / "pool.jsonl"


def cache_path() -> Path:
    return config.data_dir() / "builder" / "scaffold.json"


def load_records(path: Path | None = None) -> list[dict]:
    """Every record in the pool; a half-written line never takes the app down."""
    path = path or pool_path()
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _plan(attempt: dict) -> dict:
    """The plan JSON as that attempt stated it (parsed by the builder's reader)."""
    from . import builder

    plan = builder.parse_plan(attempt.get("plan_reply") or "")
    return plan if isinstance(plan, dict) else {}


def _settled(record: dict) -> dict:
    """The attempt worth copying: the one that built, else the last one made."""
    attempts = [a for a in (record.get("attempts") or []) if isinstance(a, dict)]
    if not attempts:
        return {}
    for attempt in reversed(attempts):
        if (attempt.get("build") or {}).get("ok"):
            return attempt
    return attempts[-1]


def _prose(text: str, limit: int = MAX_REASONING) -> str:
    """One line of a model's own words, whitespace collapsed and bounded."""
    flat = " ".join((text or "").split())
    return flat[:limit].rstrip()


def short_command(command: str) -> str:
    """A build command with its paths trimmed to names, or '' when useless.

    A plan's `run` is what the model *believes* a user would type; the recorded
    build command is what the harness actually executed. They disagree often
    enough to matter — the 7B planned `tsc && node dist/index.js` for a lane
    that typechecks without emitting and runs with `tsx` — so the executed
    command is kept beside it as evidence. A command that is the harness's own
    scratch binary (`.node-bin`, `.node.jar`) says nothing and is dropped.
    """
    raw = (command or "").split()
    if not raw:
        return ""
    # Only the program is cut to its name; a relative argument is the layout
    # being described (`src/index.ts`), so stripping it would lose the fact.
    tokens = [Path(raw[0]).name]
    if tokens[0].startswith("."):
        return ""
    tokens += [Path(t).name if t.startswith("/") else t for t in raw[1:]]
    return " ".join(tokens)[:120]


def _layout(record: dict) -> list[str]:
    """`path (purpose)` per planned file, in the order the model planned them."""
    attempt = _settled(record)
    plan = _plan(attempt)
    purposes = {str(f.get("path", "")): str(f.get("purpose", "")).strip()
                for f in (plan.get("files") or []) if isinstance(f, dict)}
    paths = [str(f.get("path", "")) for f in (record.get("files") or [])
             if isinstance(f, dict)] or list(purposes)
    out: list[str] = []
    for path in paths[:MAX_LAYOUT]:
        purpose = purposes.get(path, "")
        out.append(f"{path} — {purpose}" if purpose else path)
    return out


def note(record: dict) -> dict:
    """What one record contributes: layout, invocation, config, and its words."""
    attempt = _settled(record)
    plan = _plan(attempt)
    files = record.get("files") or []
    paths = [str(f.get("path", "")) for f in files if isinstance(f, dict)]
    entry = str(plan.get("entry") or "").strip()
    return {
        "model": record.get("label") or record.get("model") or "?",
        "language": (record.get("task") or {}).get("language", ""),
        "brief": (record.get("task") or {}).get("brief", ""),
        "built": bool(record.get("ok")),
        "layout": _layout(record),
        "entry": entry,
        "run": str(plan.get("run") or "").strip(),
        "harness": short_command((record.get("build") or {}).get("command") or ""),
        "config": [p for p in paths if is_config(p)],
        "reasoning": _prose(
            " ".join(str(plan.get("plan") or "").split())
            or attempt.get("plan_reasoning") or ""),
    }


def notes(records: list[dict] | None = None) -> dict[str, list[dict]]:
    """Per language, one note per model: its most recent build wins.

    One note per model, not per app: three Python apps from two models are two
    layouts to copy from, and repeating one model's file list four times would
    drown the other connection out. Within a model, a later build replaces an
    earlier one — it is what that model does now, under whatever conventions
    the prompt already carried — and a build always beats a failure, so a model
    that broke once and then built is described by the build.
    """
    records = load_records() if records is None else records
    best: dict[tuple[str, str], dict] = {}
    for record in records:
        row = note(record)
        language = row["language"]
        if not language or not row["layout"]:
            continue
        key = (language, row["model"])
        current = best.get(key)
        if current is None or row["built"] or not current["built"]:
            best[key] = row
    out: dict[str, list[dict]] = {}
    for (language, _), row in best.items():
        out.setdefault(language, []).append(row)
    for rows in out.values():
        rows.sort(key=lambda r: (not r["built"], r["model"]))
    return out


def section(language: str, pool: dict[str, list[dict]] | None = None,
            limit: int = MAX_MODELS) -> str:
    """The copied scaffolding conventions for one language, or ''.

    Reads as a fact sheet, not as a transcript: each line is the shape a
    connected model actually shipped, with the model named so a convention that
    does not build can be attributed and ignored next time.
    """
    rows = (pool if pool is not None else notes()).get(language) or []
    if not rows:
        return ""
    lines: list[str] = []
    for row in rows[:limit]:
        state = "built" if row["built"] else "did not build"
        head = f"- {row['model']} ({state}): " + " | ".join(row["layout"])
        lines.append(head)
        facts = []
        if row["entry"]:
            facts.append(f"entry {row['entry']}")
        if row["run"]:
            facts.append(f"run `{row['run']}`")
        harness = row.get("harness") or ""
        if harness and harness != row["run"]:
            facts.append(f"the harness ran `{harness}`")
        if row["config"]:
            facts.append("ships " + ", ".join(row["config"]))
        if facts:
            lines.append("  " + "; ".join(facts))
        if row["reasoning"]:
            lines.append(f"  it said: \"{row['reasoning']}\"")
    return "\n".join(lines)


def prompt_block(language: str, pool: dict[str, list[dict]] | None = None) -> str:
    """The section as it is pasted into a plan prompt; '' when there is none."""
    body = section(language, pool)
    if not body:
        return ""
    return ("\nOther connected models have already laid out " + language +
            " apps. Follow the conventions that built; ignore the ones that did "
            "not, and name a config file only when the layout includes one:\n"
            + body + "\n")


def write(dest: Path | None = None) -> dict:
    """Snapshot the copied conventions, so the prompt can be read without the pool."""
    dest = dest or cache_path()
    pool = notes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(pool, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return {"path": str(dest), "languages": sorted(pool),
            "notes": sum(len(rows) for rows in pool.values())}


def read(path: Path | None = None) -> dict[str, list[dict]]:
    path = path or cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def summary() -> dict:
    """Per language: how many connections contributed, and how many built."""
    pool = notes()
    return {language: {"models": len(rows),
                       "built": sum(1 for r in rows if r["built"]),
                       "config": sorted({c for r in rows for c in r["config"]})}
            for language, rows in sorted(pool.items())}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Copy scaffolding reasoning from the builder pool into prompt text")
    parser.add_argument("--language", default="", help="print one language's section")
    parser.add_argument("--write", action="store_true", help="snapshot to data/builder/scaffold.json")
    args = parser.parse_args(argv)

    if args.write:
        print(json.dumps(write(), indent=2))
    if args.language:
        print(prompt_block(args.language) or f"no {args.language} apps in the pool yet")
        return 0
    print(json.dumps(summary(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
