"""puzzles — the app's own discrimination test, ported from the puzzle trainer.

The VACA Puzzle-RAG trainer on the agent box turned exports into puzzles and made
a *model* play them: correct node vs a subtle mutation vs a same-purpose chunk
from another app, with rewards for leaner-and-faster rewrites. That design is
worth keeping; the player is not. Here the player is the **builder itself**.

Scoring a node needs no model:

  1. chunk the app into nodes (functions in JS/TS, Python, Go, Rust, Java and
     C#, plus CSS rules and HTML blocks) and classify each node's purpose,
     exactly as the trainer does;
  2. build three candidates for the node — the real one, a subtle mutation, and
     a same-purpose node from a different app;
  3. substitute each candidate into the app and build the whole set;
  4. the real node that *fails* to build is a defect in the export; a mutation
     that builds *and* keeps the app's behaviour is a weak puzzle (the change was
     semantically inert); a mutation caught by the compiler or by the output is
     a strong one.

The reward shape is the trainer's, minus the chat: correct build, preserved
behaviour, fewer bytes, fewer milliseconds. What comes out is a per-node
cleanliness score that ranks library exemplars — the thing the app's
`libraryContext` retrieval should prefer — so "faster, smaller, cleaner" is
measured rather than asserted.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import adherence, config, execution

# ─── Node model ──────────────────────────────────────────────────────────────

PURPOSES = (
    "database", "ui-render", "game-logic", "event-handler", "state",
    "styling", "layout", "input", "output", "util",
)

PURPOSE_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("database", re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE TABLE|query|"
                            r"sqlite|localStorage|indexedDB|fetch\(|axios|prisma)\b", re.I)),
    ("event-handler", re.compile(r"\baddEventListener|onclick|onchange|onkey|"
                                 r"handle[A-Z]\w*\(|\bon[A-Z]\w+\s*=")),
    ("input", re.compile(r"\b(keydown|keyup|keypress|submit|change)\b|"
                         r"\bprompt\(|\breadline|\binput\(|\bscanln|\bcin\s*>>|"
                         r"\bScanner\(", re.I)),
    ("output", re.compile(r"\bconsole\.(log|warn|error)|print\(|alert\(|\bemit\(|"
                          r"\bfmt\.Print|\bprintln!|\bSystem\.out\.print|"
                          r"\bConsole\.Write|\bprintf\(")),
    ("ui-render", re.compile(r"\b(innerHTML|createElement|appendChild|render\w*|"
                             r"querySelector|getElementById|classList|textContent|"
                             r"return\s*<|React\.createElement|useState)\b")),
    ("styling", re.compile(r"^\s*[.#@\w][^{}]*\{[^}]*\b(color|background|margin|"
                           r"padding|font|display|flex|grid|border|width|height)\s*:",
                           re.M | re.I)),
    ("layout", re.compile(r"^\s*<(html|head|body|main|header|footer|section|div|nav|"
                          r"form|ul|table)\b", re.M | re.I)),
    ("state", re.compile(r"\b(this\.\w+\s*=|let\s+\w+\s*=|const\s+\w+\s*=|var\s+\w+\s*=|"
                         r"state\s*=|set[A-Z]\w*\(|:=|\blet\s+mut\b|"
                         r"\bvar\s+\w+\s*[:=])|\bself\.\w+\s*=")),
    ("game-logic", re.compile(r"\bfor\s*\(|\bwhile\s*\(|if\s*\(|\bswitch\s*\(|"
                              r"Math\.|return\b|\bfor\s+\w+|\bwhile\s+\w|"
                              r"\bmatch\s+\w")),
)

MUTATION_OPS = (
    ("comparison", re.compile(r"<=|>=|===|!==|==|!=|<|>"),
     lambda m: {"<=": "<", ">=": ">", "===": "!==", "!==": "===", "==": "!=",
                "!=": "==", "<": "<=", ">": ">="}[m.group(0)]),
    ("boolean", re.compile(r"&&|\|\||\btrue\b|\bfalse\b|\b!\(|\b!\w"),
     lambda m: {"&&": "||", "||": "&&", "true": "false", "false": "true"}.get(
         m.group(0), m.group(0))),
    ("off-by-one", re.compile(r"\+\s*1\b|-\s*1\b|\[0\]|\[\s*1\s*\]"),
     lambda m: {"+1": "+ 2", "-1": "- 2", "[0]": "[1]", "[ 1 ]": "[0]"}.get(
         re.sub(r"\s+", "", m.group(0)), m.group(0))),
    ("api", re.compile(r"\bpush\b|\bpop\b|\bshift\b|\bunshift\b|Math\.max|Math\.min|"
                       r"querySelector\b|querySelectorAll\b|\.length\b|\.slice\b"),
     lambda m: {"push": "pop", "pop": "push", "shift": "unshift", "unshift": "shift",
                "Math.max": "Math.min", "Math.min": "Math.max",
                "querySelector": "querySelectorAll",
                "querySelectorAll": "querySelector", ".length": ".size",
                ".slice": ".splice"}.get(m.group(0), m.group(0))),
)

MIN_NODE = 30
MAX_NODE = 1600
GLOBAL_SKIP = re.compile(r"^\s*(import|export\s+type|use strict|//|/\*|\"use )", re.M)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def classify_purpose(code: str, kind: str = "") -> str:
    """The node's job, by the same ordered keyword rules the trainer used."""
    if kind == "css-rule":
        return "styling"
    if kind in ("html-block", "layout"):
        return "layout"
    for purpose, pattern in PURPOSE_RULES:
        if pattern.search(code):
            return purpose
    return "util"


class Node(dict):
    """A slice of a file: its code plus the span it occupies in that file."""

    def __init__(self, path: str, start: int, end: int, code: str, kind: str) -> None:
        super().__init__(path=path, start=start, end=end, code=code, kind=kind,
                         purpose=classify_purpose(code, kind),
                         id=f"{path}:{start}-{end}")

    @property
    def path(self) -> str:  # type: ignore[override]
        return self["path"]

    @property
    def code(self) -> str:  # type: ignore[override]
        return self["code"]


def _match_brace(text: str, open_index: int) -> int:
    """Index just past the brace matching `text[open_index] == '{'`."""
    depth = 0
    index = open_index
    in_string = ""
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "\\":
                index += 2
                continue
            if char == in_string:
                in_string = ""
        elif char in "\"'`":
            in_string = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return -1


_FUNCTION_STARTS = (
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\w*\s*\(", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?\(", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?\w+\s*=>", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+\w+", re.M),
)

_CSS_RULE = re.compile(r"^\s*([.#@\w][^{};]*)\{", re.M)


def _block_nodes(path: str, text: str, starts, matcher=_match_brace) -> list[Node]:
    nodes: list[Node] = []
    for pattern in starts:
        for match in pattern.finditer(text):
            open_index = text.find("{", match.end())
            if open_index < 0:
                continue
            # A declaration with no body (`fn f(&self);` in a trait, an abstract
            # Java method) ends at its `;`. Without this guard the next `{` in
            # the file — some unrelated block much later — would be taken as
            # this node's body and the span would point at the wrong text.
            semicolon = text.find(";", match.end(), open_index)
            if semicolon >= 0:
                continue
            close = matcher(text, open_index)
            if close < 0:
                continue
            code = text[match.start():close]
            code = code.strip("\n")
            if MIN_NODE <= len(code) <= MAX_NODE:
                nodes.append(Node(path, match.start(), close, code, "block"))
    return nodes


def _css_nodes(path: str, text: str) -> list[Node]:
    nodes: list[Node] = []
    for match in _CSS_RULE.finditer(text):
        open_index = text.find("{", match.end() - 1)
        close = _match_brace(text, open_index)
        if close < 0:
            continue
        code = text[match.start():close]
        if MIN_NODE <= len(code.strip()) <= MAX_NODE:
            nodes.append(Node(path, match.start(), close, code, "css-rule"))
    return nodes


def _html_nodes(path: str, text: str) -> list[Node]:
    nodes: list[Node] = []
    pattern = re.compile(r"^\s*<(header|nav|main|section|form|table|ul|div)\b", re.M | re.I)
    for match in pattern.finditer(text):
        tag = match.group(1).lower()
        close_match = re.search(rf"</{tag}>\s*$", text[match.end():], re.M | re.I)
        if not close_match:
            continue
        end = match.end() + close_match.end()
        code = text[match.start():end]
        if MIN_NODE <= len(code.strip()) <= MAX_NODE:
            nodes.append(Node(path, match.start(), end, code, "html-block"))
    return nodes


_PY_DEF = re.compile(r"^\s*(?:async\s+)?def\s+\w+|^\s*class\s+\w+", re.M)


# ─── Compiled languages ──────────────────────────────────────────────────────
# Go, Rust, Java and C# all delimit a function with braces, so the same span
# machinery works once each language's declaration shape is recognised. Only
# functions and methods become nodes: a `class`/`impl`/`namespace` body would
# swallow every method inside it, and the surviving node would be too big to
# score (and too big to splice safely).

_GO_FUNC = re.compile(r"^func\s+(?:\([^)]*\)\s*)?\w+\s*\(", re.M)

_RUST_FN = re.compile(
    r"^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?(?:const[ \t]+)?(?:async[ \t]+)?"
    r"(?:unsafe[ \t]+)?(?:extern[ \t]+\"[^\"]*\"[ \t]+)?fn[ \t]+\w+", re.M)

_JAVA_MEMBER = re.compile(
    r"^[ \t]*(?:@[A-Za-z_]\w*(?:\([^)]*\))?[ \t]*\r?\n[ \t]*)*"
    r"(?:(?:public|protected|private|static|final|abstract|synchronized|native|"
    r"default|strictfp)[ \t]+)+"
    r"(?:<[^>]*>[ \t]+)?[\w.$<>\[\], ?]+[ \t]+\w+[ \t]*\(", re.M)

_JAVA_CTOR = re.compile(
    r"^[ \t]*[a-z]+[ \t]+([A-Z]\w*)[ \t]*\([^)]*\)"
    r"[ \t]*(?:throws[ \t]+[\w., \t]+)?(?=[ \t]*\{)", re.M)

_CSHARP_MEMBER = re.compile(
    r"^[ \t]*(?:\[[^\]]*\][ \t]*\r?\n[ \t]*)*"
    r"(?:(?:public|private|protected|internal|static|async|virtual|override|"
    r"sealed|abstract|partial|extern|unsafe|new)[ \t]+)+"
    r"[\w.<>\[\], ?]+[ \t]+\w+[ \t]*\(", re.M)


def _match_brace_rust(text: str, open_index: int) -> int:
    """Brace matcher that knows Rust's strings, comments and lifetimes.

    `_match_brace` treats every `'` as the start of a string, so a `&'a str`
    parameter would swallow the rest of the file and the node would be dropped.
    Here a `'` opens a character literal only when it closes within a few
    characters; otherwise it is a lifetime and the scan continues.
    """
    depth = 0
    index = open_index
    in_string = ""
    in_char = False
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "\\":
                index += 2
                continue
            if char == in_string:
                in_string = ""
        elif in_char:
            if char == "\\":
                index += 2
                continue
            if char == "'":
                in_char = False
        elif text.startswith("//", index):
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline
            continue
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
            continue
        elif char == '"':
            in_string = char
        elif char == "'":
            if text.find("'", index + 1, index + 6) > 0:
                in_char = True
            else:
                index += 1
                continue
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return -1


def _python_nodes(path: str, text: str) -> list[Node]:
    matches = list(_PY_DEF.finditer(text))
    nodes: list[Node] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        code = text[match.start():end].rstrip("\n")
        if MIN_NODE <= len(code) <= MAX_NODE:
            nodes.append(Node(path, match.start(), match.start() + len(code), code, "block"))
    return nodes


def chunk_file(path: str, text: str) -> list[Node]:
    """Semantic nodes of one file; empty when nothing is safely splittable."""
    suffix = Path(path).suffix.lower()
    if suffix == ".css":
        return _css_nodes(path, text)
    if suffix in (".html", ".htm"):
        return _html_nodes(path, text)
    if suffix == ".py":
        return _python_nodes(path, text)
    if suffix == ".go":
        return _block_nodes(path, text, (_GO_FUNC,))
    if suffix == ".rs":
        return _block_nodes(path, text, (_RUST_FN,), matcher=_match_brace_rust)
    if suffix == ".java":
        return _block_nodes(path, text, (_JAVA_MEMBER, _JAVA_CTOR))
    if suffix == ".cs":
        return _block_nodes(path, text, (_CSHARP_MEMBER,))
    if suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        nodes = _block_nodes(path, text, _FUNCTION_STARTS)
        # A `function f(){}` inside a class/object literal is a nested match; keep
        # the outermost node only, or the same bytes count twice.
        kept: list[Node] = []
        for node in sorted(nodes, key=lambda n: (n["start"], -n["end"])):
            if kept and node["start"] < kept[-1]["end"]:
                continue
            kept.append(node)
        return kept
    return []


def chunk_app(files: list[dict]) -> list[Node]:
    nodes: list[Node] = []
    for entry in files or []:
        path = entry.get("path", "")
        nodes.extend(chunk_file(path, entry.get("content", "")))
    return nodes


# ─── Fakes ───────────────────────────────────────────────────────────────────

def subtle_mutation(code: str, rng: random.Random | None = None) -> tuple[str, str] | None:
    """One small, plausible change: (mutated, operation-name).

    Returns None when no operator applies — a decoy that is identical to the
    truth is worse than no puzzle at all.
    """
    rng = rng or random.Random(0)
    ops = list(MUTATION_OPS)
    rng.shuffle(ops)
    for name, pattern, replace in ops:
        matches = list(pattern.finditer(code))
        if not matches:
            continue
        # Skip operators that would fire inside a string or a comment: those
        # mutations are not "subtle", they are just noise.
        candidates = [m for m in matches if replace(m) != m.group(0)]
        if not candidates:
            continue
        match = candidates[rng.randrange(len(candidates))]
        mutated = code[:match.start()] + replace(match) + code[match.end():]
        if mutated != code:
            return mutated, name
    return None


LANGUAGE_BY_SUFFIX = {
    ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
    ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".py": "python", ".css": "css", ".html": "html", ".htm": "html",
    ".go": "go", ".rs": "rust", ".java": "java", ".cs": "csharp",
}


def language_of(path: str) -> str:
    return LANGUAGE_BY_SUFFIX.get(Path(path).suffix.lower(), "")


class NodeIndex:
    """Same-purpose nodes across apps — the cross-app decoy pool.

    A decoy must come from the same language: a JavaScript node dropped into a
    TypeScript set fails to compile for reasons that have nothing to do with the
    puzzle, which would score every decoy as "caught" for free.
    """

    def __init__(self, tasks: list[dict]) -> None:
        self.by_purpose: dict[str, list[tuple[str, Node, str]]] = {}
        for task in tasks:
            for node in chunk_app(task.get("files") or []):
                self.by_purpose.setdefault(node["purpose"], []).append(
                    (task["id"], node, language_of(node["path"])))

    def decoy(self, purpose: str, *, exclude_task: str, language: str,
              exclude_code: str) -> tuple[str, Node] | None:
        for task_id, node, lang in self.by_purpose.get(purpose, []):
            if task_id == exclude_task or node["code"] == exclude_code:
                continue
            if lang != language:
                continue
            return task_id, node
        return None

    def stats(self) -> dict[str, int]:
        return {purpose: len(nodes) for purpose, nodes in sorted(self.by_purpose.items())}


def build_puzzle(node: Node, index: NodeIndex, *, task_id: str,
                 language: str) -> dict | None:
    """The three candidates the trainer would have shown a model."""
    mutated = subtle_mutation(node["code"], random.Random(node["id"]))
    if not mutated:
        return None
    mutant, operation = mutated
    decoy = index.decoy(node["purpose"], exclude_task=task_id, language=language,
                        exclude_code=node["code"])
    puzzle = {
        "node_id": node["id"],
        "path": node["path"],
        "kind": node["kind"],
        "purpose": node["purpose"],
        "language": language,
        "correct": node["code"],
        "mutant": mutant,
        "mutation": operation,
        "decoy": decoy[1]["code"] if decoy else "",
        "decoy_from": decoy[0] if decoy else "",
    }
    return puzzle


def _splice(text: str, node: Node, code: str) -> str:
    return text[:node["start"]] + code + text[node["end"]:]


def _build_with(task: dict, path: str, code: str, timeout_s: float) -> dict:
    """Build the set with one file's content replaced; return verdict + numbers."""
    files = [{"path": f["path"], "content": code if f["path"] == path else f["content"]}
             for f in task.get("files") or []]
    target = task.get("target", "")
    entry = target if execution.is_entry_name(target) else ""
    result = execution.run_files(files, task.get("language", ""), entry=entry,
                                 timeout_s=timeout_s)
    return {"ok": result.ok, "stdout": result.stdout, "stderr": result.stderr,
            "runtime_ms": result.duration_ms, "bytes": len(code.encode("utf-8")),
            "error": result.error}


def aggregate(rows: list[dict]) -> dict[str, dict]:
    """Per-app rollup of node scores — the library's exemplar ranking."""
    apps: dict[str, dict] = {}
    for row in rows:
        app = apps.setdefault(row["task_id"], {
            "task_id": row["task_id"], "nodes": 0, "clean": 0.0, "bytes": 0,
            "runtime_ms": 0, "caught": 0, "updated_at": row.get("scored_at", _now()),
        })
        app["nodes"] += 1
        app["clean"] += row["clean"]
        app["bytes"] += row["bytes"]
        app["runtime_ms"] += row["runtime_ms"]
        app["caught"] += 1 if row["mutant_detected"] else 0
    for app in apps.values():
        app["clean"] = round(app["clean"] / app["nodes"], 4)
        app["caught_rate"] = round(app["caught"] / app["nodes"], 4)
        app["avg_bytes"] = round(app["bytes"] / app["nodes"])
    return apps


def to_library(rows: list[dict], path: Path | None = None) -> dict:
    """Merge this run's per-app scores into the library's ranking sheet."""
    target = path or (config.data_dir() / "library" / "puzzle_scores.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    merged: dict[str, dict] = {}
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("task_id"):
                merged[row["task_id"]] = row
    merged.update(aggregate(rows))
    ordered = [merged[key] for key in sorted(merged)]
    target.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ordered),
                      encoding="utf-8")
    scored = [r for r in ordered if r["nodes"]]
    return {"path": str(target), "apps": len(ordered),
            "mean_clean": round(sum(r["clean"] for r in scored) / len(scored), 4)
            if scored else 0.0}


def score_puzzle(task: dict, node: Node, puzzle: dict, timeout_s: float = 30) -> dict:
    """Grade the three candidates by building the app, not by asking a model."""
    text = next((f["content"] for f in task["files"] if f["path"] == node["path"]), "")
    reference = _build_with(task, node["path"], text, timeout_s)
    correct = _build_with(task, node["path"], _splice(text, node, puzzle["correct"]), timeout_s)
    mutant = _build_with(task, node["path"], _splice(text, node, puzzle["mutant"]), timeout_s)
    decoy = (_build_with(task, node["path"], _splice(text, node, puzzle["decoy"]), timeout_s)
             if puzzle["decoy"] else None)

    def detected(candidate: dict | None) -> bool | None:
        if candidate is None:
            return None
        if not candidate["ok"]:
            return True  # the compiler caught it
        return candidate["stdout"] != correct["stdout"]  # behaviour caught it

    compliance = adherence.score_files(task.get("files") or [], task.get("language", ""))
    result = {
        "task_id": task["id"],
        "node_id": node["id"],
        "path": node["path"],
        "purpose": node["purpose"],
        "kind": node["kind"],
        "mutation": puzzle["mutation"],
        "builds": correct["ok"],
        "behaviour_stable": correct["stdout"] == reference["stdout"],
        "mutant_detected": detected(mutant),
        "decoy_detected": detected(decoy),
        "bytes": correct["bytes"],
        "runtime_ms": correct["runtime_ms"],
        "adherence": compliance["score"],
        "mutant_bytes": mutant["bytes"],
        "scored_at": _now(),
    }
    result["clean"] = clean_score(result)
    return result


def clean_score(result: dict) -> float:
    """0–1: does this node build, behave, and resist a plausible edit?

    A mutation that survives makes the node a *weak* exemplar: nothing about it
    is load-bearing, so copying it teaches nothing. That is why a surviving
    mutation lowers the score even though the node itself is fine.
    """
    parts = [1.0 if result.get("builds") else 0.0,
             1.0 if result.get("behaviour_stable") else 0.0,
             1.0 if result.get("mutant_detected") else 0.0,
             float(result.get("adherence") or 0.0)]
    if result.get("decoy_detected") is not None:
        parts.append(1.0 if result["decoy_detected"] else 0.0)
    return round(sum(parts) / len(parts), 4)


def run(tasks: list[dict], *, max_nodes: int = 3, timeout_s: float = 30,
        out_dir: Path | None = None, pool: list[dict] | None = None,
        log=print) -> dict:
    """Score a sample of app tasks; writes puzzles.jsonl, scores.jsonl, summary.

    `pool` is the decoy corpus. It is the whole library by default in the CLI, so
    a scored sample is not forced to draw its fakes from its own few apps.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    target_dir = out_dir or (config.data_dir() / "puzzles" / stamp)
    target_dir.mkdir(parents=True, exist_ok=True)
    index = NodeIndex(pool or tasks)
    puzzles_path = target_dir / "puzzles.jsonl"
    scores_path = target_dir / "scores.jsonl"
    rows: list[dict] = []
    built = 0
    log(f"[puzzles] {len(tasks)} apps, node index: {index.stats()}")

    with puzzles_path.open("w", encoding="utf-8") as pz, \
            scores_path.open("w", encoding="utf-8") as sc:
        for task in tasks:
            nodes = chunk_app(task.get("files") or [])[:max_nodes]
            for node in nodes:
                puzzle = build_puzzle(node, index, task_id=task["id"],
                                      language=task.get("language", ""))
                if not puzzle:
                    continue
                pz.write(json.dumps(puzzle, ensure_ascii=False) + "\n")
                row = score_puzzle(task, node, puzzle, timeout_s)
                rows.append(row)
                sc.write(json.dumps(row, ensure_ascii=False) + "\n")
                sc.flush()
                built += 1
                log(f"[puzzles] {task['language']:10s} {node['purpose']:13s} "
                    f"build={'y' if row['builds'] else 'n'} "
                    f"mutant={'caught' if row['mutant_detected'] else 'survived'} "
                    f"clean={row['clean']:.2f}")

    summary = {
        "apps": len(tasks),
        "nodes_scored": built,
        "builds": sum(1 for r in rows if r["builds"]),
        "mutants_caught": sum(1 for r in rows if r["mutant_detected"]),
        "decoys_caught": sum(1 for r in rows if r["decoy_detected"]),
        "mean_clean": round(sum(r["clean"] for r in rows) / len(rows), 4) if rows else 0.0,
        "by_purpose": {},
        "node_index": index.stats(),
        "finished_at": _now(),
        "run_dir": str(target_dir),
    }
    for row in rows:
        bucket = summary["by_purpose"].setdefault(
            row["purpose"], {"nodes": 0, "clean": 0.0, "caught": 0})
        bucket["nodes"] += 1
        bucket["clean"] += row["clean"]
        bucket["caught"] += 1 if row["mutant_detected"] else 0
    for bucket in summary["by_purpose"].values():
        bucket["clean"] = round(bucket["clean"] / bucket["nodes"], 4)
    (target_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                            encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score library nodes with the puzzle trainer's fakes")
    parser.add_argument("--tasks", type=int, default=8,
                        help="apps to walk; 0 means the whole library")
    parser.add_argument("--max-nodes", type=int, default=3, help="nodes per app")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--out", default="")
    parser.add_argument("--language", default="", help="limit to one language")
    parser.add_argument("--to-library", action="store_true",
                        help="merge the per-app scores into data/library")
    args = parser.parse_args(argv)

    from . import library

    confirmed = {t["id"] for t in library.confirmed()}
    apps = [t for t in library.load_tasks()
            if library.is_multi_file(t) and t["id"] in confirmed
            and (not args.language or t["language"] == args.language)]
    if not apps:
        print("puzzles: no confirmed multi-file tasks — ingest the exports first",
              file=sys.stderr)
        return 2
    tasks = apps if args.tasks <= 0 else apps[: args.tasks]
    summary = run(tasks, max_nodes=args.max_nodes, timeout_s=args.timeout,
                  out_dir=Path(args.out) if args.out else None, pool=apps)
    print(json.dumps({k: summary[k] for k in
                      ("apps", "nodes_scored", "builds", "mutants_caught",
                       "decoys_caught", "mean_clean")}, indent=2))
    print("run dir:", summary["run_dir"])
    if args.to_library:
        rows = [json.loads(line) for line in
                (Path(summary["run_dir"]) / "scores.jsonl").read_text(
                    encoding="utf-8").splitlines() if line.strip()]
        print("library:", json.dumps(to_library(rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
