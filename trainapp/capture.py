"""capture — turn a verified fix into a training row.

A correction is only worth learning from when the harness can PROVE it: the
file failed the real toolchain before the edit and passed it afterwards. Rows
are written as plain JSONL so any trainer (Unsloth, TRL, the trainer shipped
here) can consume them without conversion.

Only verified rows are appended. A failing fix attempt never reaches the
dataset — that is the whole guard against poisoning the model with guesses.

The app (VACA) runs its own proof-gated capture: `_training.json` sidecars are
folded into `verified-generations.jsonl` only after the export typechecks. Those
rows are far more interesting than a single-file fix — the instruction names the
planned sibling files, so the model sees a file in the context of the app it
belongs to. `import_vaca_rows()` copies them into their own sheet and
`export_dataset()` merges the two, so the trainer's SFT set is not blind to the
app's own verified builds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import config

SHEET_NAME = "corrections.jsonl"
APP_SHEET_NAME = "app_captures.jsonl"
SOURCE = "train-app:verified-fix"
VACA_SOURCE = "vaca:captured-verified"
VACA_CAPTURE_NAME = "verified-generations.jsonl"
MAX_OUTPUT_CHARS = 60_000
MAX_INSTRUCTION_CHARS = 4_000


def sheet_path() -> Path:
    return config.dataset_dir() / SHEET_NAME


def app_sheet_path() -> Path:
    return config.dataset_dir() / APP_SHEET_NAME


def default_vaca_capture() -> Path:
    """Where VACA writes its verified rows.

    Resolved per call rather than at import time: the path depends on `VACA_ROOT`,
    and tests (and a second checkout) point that at a scratch tree.
    """
    root = Path(os.environ.get("VACA_ROOT") or Path.home() / "Desktop" / "visual-ai-architect")
    return root.expanduser() / "training" / "dataset" / VACA_CAPTURE_NAME


def _norm(text: str) -> str:
    return (text or "").replace("\r\n", "\n").strip()


def row_key(row: dict) -> str:
    payload = f"{row.get('instruction', '')}\n{row.get('output', '')}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_sheet(path: Path) -> list[dict]:
    """JSONL sheet -> rows, skipping a truncated tail line rather than failing."""
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a truncated tail line never invalidates the sheet
        if isinstance(row, dict) and row.get("output"):
            rows.append(row)
    return rows


def load_rows() -> list[dict]:
    return _load_sheet(sheet_path())


def load_app_rows() -> list[dict]:
    return _load_sheet(app_sheet_path())


def import_vaca_rows(path: Path | str | None = None) -> dict:
    """Copy VACA's verified app-file rows into the trainer's own sheet.

    The same conservative gate as `append_row` runs on every row: VACA already
    typechecked the export, but this sheet is the trainer's evidence, so a row
    that is fenced, empty or absurdly large is refused here too. Rows are keyed
    on instruction+output, so re-running an import is free and adds nothing.
    """
    source = Path(path).expanduser() if path else default_vaca_capture()
    result = {"imported": 0, "duplicates": 0, "rejected": 0, "missing": 0,
              "path": str(source)}
    if not source.is_file():
        result["missing"] = 1
        return result

    seen = {row_key(row) for row in load_app_rows()}
    fresh: list[dict] = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            result["rejected"] += 1
            continue
        if not isinstance(row, dict):
            result["rejected"] += 1
            continue
        instruction = _norm(row.get("instruction", ""))
        output = _norm(row.get("output", ""))
        ok, _ = is_capture_worthy(instruction, output, None)
        if not ok:
            result["rejected"] += 1
            continue
        clean = {
            "instruction": instruction,
            "input": _norm(row.get("input", "")),
            "output": output,
            "source": VACA_SOURCE,
            "meta": {"origin": "vaca-export", "imported_from": str(source)},
        }
        key = row_key(clean)
        if key in seen:
            result["duplicates"] += 1
            continue
        seen.add(key)
        fresh.append(clean)

    if fresh:
        with app_sheet_path().open("a", encoding="utf-8") as handle:
            for row in fresh:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    result["imported"] = len(fresh)
    return result


KNOWLEDGE_SHEET_NAME = "app_knowledge.jsonl"

# Every sheet the old trainer left behind, and what it is. Code rows teach a
# program; knowledge rows teach the app's own design (routes, node types,
# language contracts) and would dilute a code SFT set, so they get their own
# sheet instead of being mixed in or thrown away.
VACA_SHEETS = {
    "verified-generations.jsonl": "code",
    "language-gaps.jsonl": "code",
    "train.jsonl": "auto",
    "val.jsonl": "auto",
    "test.jsonl": "auto",
    "how-vaca-works.jsonl": "knowledge",
    "languages.jsonl": "knowledge",
}

CODE_HINTS = ("def ", "function ", "class ", "import ", "#include", "fn ",
              "pub fn", "package ", "<?php", "const ", "let ", "interface ",
              "static void", "func ", "using System", "=> {", "::")


def knowledge_sheet_path() -> Path:
    return config.dataset_dir() / KNOWLEDGE_SHEET_NAME


def looks_like_code(output: str) -> bool:
    """A code row has code-shaped output; prose about the app does not.

    Deliberately conservative: the cost of filing one prose answer as code is a
    noisy training row, so a row must show real syntax (braces/semicolons or a
    declaration keyword) and must not be mostly prose sentences.
    """
    text = _norm(output)
    if len(text) < 24:
        return False
    if not any(hint in text for hint in CODE_HINTS):
        return False
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return False
    prose = sum(1 for line in lines
                if line.rstrip().endswith(".") and ";" not in line
                and "{" not in line and "=" not in line)
    return prose / len(lines) < 0.5


def import_vaca_directory(directory: Path | str | None = None) -> dict:
    """Import every sheet the old trainer left, split into code and knowledge.

    The puzzle trainer's own SFT/DPO output is **not** on disk (its round
    directory is empty), so it cannot be imported; what survives is the capture
    corpus, the language-gap fixes, the app Q&A sets and the app-shard files.
    """
    root = Path(directory).expanduser() if directory else \
        Path(os.environ.get("VACA_ROOT") or
             Path.home() / "Desktop" / "visual-ai-architect") / "training" / "dataset"
    result: dict = {"directory": str(root), "code": 0, "knowledge": 0,
                    "duplicates": 0, "rejected": 0, "missing": 0, "by_file": {}}
    if not root.is_dir():
        result["missing"] = 1
        return result

    code_seen = {row_key(row) for row in load_app_rows()}
    knowledge_seen = {row_key(row) for row in _load_sheet(knowledge_sheet_path())}
    code_rows: list[dict] = []
    knowledge_rows: list[dict] = []

    def take(row: dict, origin: str, kind: str) -> None:
        instruction = _norm(row.get("instruction", ""))
        output = _norm(row.get("output", ""))
        ok, _ = is_capture_worthy(instruction, output, None)
        if not ok:
            result["rejected"] += 1
            return
        bucket, seen = (("knowledge", knowledge_seen) if kind == "knowledge"
                        else ("code", code_seen))
        clean = {"instruction": instruction, "input": _norm(row.get("input", "")),
                 "output": output,
                 "source": VACA_SOURCE if bucket == "code" else "vaca:knowledge",
                 "meta": {"origin": "vaca-dataset", "imported_from": origin}}
        key = row_key(clean)
        if key in seen:
            result["duplicates"] += 1
            return
        seen.add(key)
        (knowledge_rows if bucket == "knowledge" else code_rows).append(clean)
        result[bucket] += 1

    for name, declared in VACA_SHEETS.items():
        path = root / name
        if not path.is_file():
            continue
        count = 0
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                result["rejected"] += 1
                continue
            kind = declared if declared != "auto" else (
                "code" if looks_like_code(row.get("output", "")) else "knowledge")
            take(row, name, kind)
            count += 1
        result["by_file"][name] = count

    # app-shards/*.txt: one JSON object per file, same row shape.
    shards = root / "app-shards"
    if shards.is_dir():
        count = 0
        for path in sorted(shards.glob("*.txt")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                result["rejected"] += 1
                continue
            if isinstance(row, dict):
                take(row, f"app-shards/{path.name}",
                     "code" if looks_like_code(row.get("output", "")) else "knowledge")
                count += 1
        result["by_file"]["app-shards"] = count

    for path, rows in ((app_sheet_path(), code_rows),
                       (knowledge_sheet_path(), knowledge_rows)):
        if not rows:
            continue
        with path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    result["code_rows"] = len(code_rows)
    result["knowledge_rows"] = len(knowledge_rows)
    return result


def is_capture_worthy(instruction: str, output: str, before: str | None) -> tuple[bool, str]:
    """Conservative gate. Returns (ok, reason-when-rejected)."""
    out = _norm(output)
    if not out:
        return False, "empty output"
    if len(out) > MAX_OUTPUT_CHARS:
        return False, f"output too large ({len(out)} chars)"
    if len(_norm(instruction)) > MAX_INSTRUCTION_CHARS:
        return False, "instruction too large"
    if out.startswith("```") and out.endswith("```"):
        return False, "output is still wrapped in a markdown fence"
    if before is not None and _norm(before) == out:
        return False, "output is identical to the broken file"
    return True, ""


def append_row(row: dict) -> tuple[bool, str]:
    """Append one JSONL row, skipping exact duplicates of instruction+output."""
    ok, reason = is_capture_worthy(row.get("instruction", ""), row.get("output", ""),
                                   row.get("meta", {}).get("before"))
    if not ok:
        return False, reason

    key = row_key(row)
    seen = {row_key(existing) for existing in load_rows()}
    if key in seen:
        return False, "already captured"

    clean = {
        "instruction": _norm(row["instruction"]),
        "input": _norm(row.get("input", "")),
        "output": _norm(row["output"]),
        "source": row.get("source", SOURCE),
        "meta": row.get("meta", {}),
    }
    clean["meta"] = {**clean["meta"], "sha256": key,
                     "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    with sheet_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(clean, ensure_ascii=False) + "\n")
    return True, "captured"


def make_fix_row(*, language: str, filename: str, platform: str, command: str,
                 exit_code: int | None, error_output: str, before: str,
                 after: str, goal: str = "", attempts: int = 1) -> dict:
    """The SFT pair: (broken file + the harness's real error) -> fixed file."""
    instruction = (
        f"Fix this {language} file so it runs cleanly. "
        "Return only the corrected file, with no markdown fence and no commentary."
    )
    input_parts = [
        f"File: {filename}",
        f"Platform: {platform}",
        f"Command: {command}",
        f"Exit code: {exit_code}",
        "Output:",
        _norm(error_output) or "(no output)",
        "",
        "Current code:",
        _norm(before),
    ]
    if goal.strip():
        input_parts.insert(0, f"Goal: {goal.strip()}")
    return {
        "instruction": instruction,
        "input": "\n".join(input_parts),
        "output": _norm(after),
        "source": SOURCE,
        "meta": {
            "language": language,
            "file": filename,
            "platform": platform,
            "exit_code": exit_code,
            "attempts": attempts,
            "before": _norm(before),
        },
    }


def stats() -> dict:
    rows = load_rows()
    app_rows = load_app_rows()
    by_language: dict[str, int] = {}
    for row in rows + app_rows:
        lang = (row.get("meta") or {}).get("language", "unknown")
        by_language[lang] = by_language.get(lang, 0) + 1
    return {
        "rows": len(rows),
        "app_rows": len(app_rows),
        "total_rows": len(rows) + len(app_rows),
        "sheet": str(sheet_path()),
        "app_sheet": str(app_sheet_path()),
        "by_language": by_language,
        "bytes": sheet_path().stat().st_size if sheet_path().exists() else 0,
    }


def export_dataset(val_ratio: float = 0.1,
                   extra_rows: list[dict] | None = None) -> dict:
    """Write train.jsonl / val.jsonl / dataset_meta.json from the sheet.

    The split is hash-based, so adding rows never reshuffles the existing
    train/val boundary — a re-export cannot silently leak a val row into train.
    `extra_rows` lets another proof-gated source (verified library builds) join
    the same split without inventing a second dataset format.
    """
    corrections = load_rows()
    app_rows = load_app_rows()
    extra_rows = list(extra_rows or [])
    # Corrections first: a fix the harness proved wins over an imported app row
    # with the same instruction+output, because it carries the error context.
    merged: dict[str, dict] = {}
    for row in corrections + app_rows + extra_rows:
        merged.setdefault(row_key(row), row)
    rows = list(merged.values())
    train: list[dict] = []
    val: list[dict] = []
    cut = max(1, round(max(val_ratio, 0.0) * 100))
    for row in rows:
        bucket = int(row_key(row)[:8], 16) % 100
        (val if bucket < cut else train).append(row)
    if not train and val:
        # A tiny sheet must never strand every row in val: nothing to train on.
        val.sort(key=row_key)
        train.append(val.pop())

    out = config.dataset_dir()
    (out / "train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in train), encoding="utf-8")
    (out / "val.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in val), encoding="utf-8")

    meta = {
        "total_examples": len(rows),
        "train_examples": len(train),
        "val_examples": len(val),
        "val_ratio": val_ratio,
        "source": SOURCE,
        "sources": {**{"corrections": len(corrections), "vaca": len(app_rows)},
                    **({"extra": len(extra_rows)} if extra_rows else {})},
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "train_path": str(out / "train.jsonl"),
        "val_path": str(out / "val.jsonl"),
    }
    (out / "dataset_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import VACA's verified app rows and export the SFT set")
    parser.add_argument("--import-vaca", nargs="?", const="", default=None,
                        metavar="PATH", help="import rows (default: VACA's dataset)")
    parser.add_argument("--export", action="store_true", help="write train/val")
    parser.add_argument("--import-all", nargs="?", const="", default=None,
                        metavar="DIR", help="import every old VACA sheet (code + knowledge)")
    parser.add_argument("--stats", action="store_true", help="print sheet counts")
    args = parser.parse_args(argv)

    acted = False
    if args.import_vaca is not None:
        print(json.dumps(import_vaca_rows(args.import_vaca or None), indent=2))
        acted = True
    if args.import_all is not None:
        print(json.dumps(import_vaca_directory(args.import_all or None), indent=2))
        acted = True
    if args.export:
        print(json.dumps(export_dataset(), indent=2))
        acted = True
    if args.stats or not acted:
        print(json.dumps(stats(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
