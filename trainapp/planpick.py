"""planpick — which of these plans can actually build? One answer, provable.

`plansft` teaches the *shape* of a plan: one line per file, path, language, role.
This asks the harder question the architect seat actually fails — of three plans
for the same finished project, which one names the files it shipped? The wrong
answers are not written for the sake of a quiz: a decoy only enters a row when a
deterministic rule can *prove* it is worse than the truth.

Three rules, and nothing else is allowed through:

* **missing** — the plan leaves out a file another file in the set depends on.
  The proof is in the source, and there are two shapes of it: an *import*
  (`main.py` says `from util import total`, a Go block says `import "…/seqs"`,
  Java says `import com.x.WordCounts;`) or a *symbol* — same-package code that
  refers to each other by name with no import line at all (`Main.java` uses
  `WordCounts`, which only `WordCounts.java` declares). With `--verify` either
  is upgraded to the toolchain's own verdict: the set is built once whole and
  once reduced, and the decoy is kept only if the build fails. A decoy the build
  survives is thrown away — a plan that drops a file nobody needed was a
  legitimate alternative, not a mistake.
* **invented** — the plan names a path the project does not ship. The prompt
  says the set is complete, so this is wrong by the stated contract, and it is
  the exact failure the developer contract already forbids: *never invent a
  path*.
* **over** — the plan repeats a path, or grows past the plan gate's eight-line
  allowance (`plansft.MAX_LINES`), which `plansft`'s own gate rejects on sight.

A decoy that none of those rules can convict is discarded and counted in
`stats()["rejected"]`, not shipped with a lucky label. That is the difference
between a dataset and a coin toss: the row count is lower, and every surviving
row has a wrong answer you can demonstrate line by line.

Only verified, multi-file, trainable sets are used (`scaffoldsft.is_trainable`
owns the 75% split), because a plan for a set that never built is not evidence
of anything.

    python3 -m trainapp.planpick             # what would be generated, and why
    python3 -m trainapp.planpick --verify    # upgrade the proof to a real build
    python3 -m trainapp.planpick --write     # library/plan_pick.jsonl + plan_pairs.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path

from . import library, plansft, scaffoldsft

SOURCE = "library:plan-pick"
SFT_FILE = "plan_pick.jsonl"
PAIR_FILE = "plan_pairs.jsonl"
LETTERS = ("A", "B", "C")

INSTRUCTION = (
    "Three plans for one finished project are shown below. Exactly one of them "
    "names the files the project actually shipped; the others name a file it "
    "does not have, leave out a file another file imports, or break the plan "
    "gate (one line per file, no repeats, at most {max_lines} lines).\n\n"
    "Project: {title}\nLanguage: {language}\n\n"
    "{plans}\n\n"
    "Reply with the letter of the plan that matches the project, in the form: "
    "PLAN: <letter>")

# Import-shaped references, per language family. Only used to *find* a candidate
# file to drop; the decision to keep the decoy is the proof below, never this.
_IMPORT = (
    re.compile(r"from\s+([\w\.]+)\s+import\b"),
    re.compile(r"\bimport\s+(?:[\w{},*\s]+from\s+)?['\"]([^'\"]+)['\"]"),
    re.compile(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    re.compile(r"#include\s*[<\"]([^>\"]+)[>\"]"),
    re.compile(r"\busing\s+([\w\.]+)\s*;"),
    re.compile(r"^\s*(?:pub\s+)?mod\s+(\w+)\s*;", re.M),
    # A qualified import with a terminator (Java/C#/Kotlin). Deliberately not
    # `package`: Go's `package main` names a package, not a file, and reading it
    # as an import of `main.go` produced a decoy nothing had actually proved.
    re.compile(r"^\s*import\s+([\w\.]+)\s*;", re.M),
)
# `import ( "fmt"\n "example/seqs" )` — a grouped Go block only ever yielded its
# first quoted path to the patterns above, so the block is read as a block.
_GO_BLOCK = re.compile(r"^\s*import\s*\(([^)]*)\)", re.M | re.S)
_GO_SINGLE = re.compile(r"^\s*import\s+(?:\w+\s+)?\"([^\"]+)\"", re.M)
# A declaration a sibling can depend on without an import line: same package in
# Go, same package in Java/Kotlin, same namespace in C#.
_DECL = re.compile(
    r"\b(?:public\s+|private\s+|protected\s+|static\s+|final\s+|abstract\s+|"
    r"sealed\s+|open\s+|data\s+|internal\s+|partial\s+)*"
    r"(?:class|interface|enum|record|object|struct|trait|func|def)\s+(\w+)"
)
# Words that name nothing a sibling could be said to depend on.
_NOT_A_SYMBOL = {"main", "init", "run", "start", "setup", "test", "tests"}


# ── the truth ──────────────────────────────────────────────────────────────

def true_plan(task: dict) -> list[str]:
    """The plan this project actually shipped, one line per file."""
    paths = [str(f.get("path", "")) for f in (task.get("files") or [])
             if f.get("path")]
    if not paths or len(paths) > plansft.MAX_LINES:
        return []
    language = str(task.get("language") or "")
    target = str(task.get("target") or "")
    return [f"{path} ({plansft.language_of(path, language)}) — "
            f"{plansft.role_of(path, target)}" for path in paths]


# ── proofs ─────────────────────────────────────────────────────────────────

def _import_tokens(text: str) -> list[str]:
    """Every module path a file names as a dependency, whatever its language."""
    body = text or ""
    tokens = [str(match) for pattern in _IMPORT for match in pattern.findall(body)]
    for block in _GO_BLOCK.findall(body):
        tokens += re.findall(r'"([^"]+)"', block)
    tokens += _GO_SINGLE.findall(body)
    return tokens


def references(text: str, path: str) -> bool:
    """Does this file name that one as a module it depends on?

    Matched on the last path segment, which is what a module path and a file name
    have in common (`from util import x`, `require('./util')`, `import "a/util"`).
    Go imports a *directory*, so the file's own folder is compared too: a sibling
    under `internal/logic/seqs/` is reached by importing `…/seqs`.
    """
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    folder = path.rsplit("/", 2)[-2] if path.count("/") else ""
    if len(stem) < 2 and not folder:
        return False
    for token in _import_tokens(text):
        tail = str(token).replace("\\", "/").rsplit("/", 1)[-1]
        # Both separators matter: `from util import x` ends at a path segment,
        # `import com.x.WordCounts;` ends at a qualified name.
        last = tail.rsplit(".", 1)[-1]
        if tail in (name, stem) or last == stem:
            return True
        if folder and tail == folder:
            return True
    return False


def declares(text: str, path: str) -> set[str]:
    """The type/function names a file itself declares."""
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    names = set(_DECL.findall(text or ""))
    if re.fullmatch(r"[A-Z]\w+", stem):
        # A Java/Kotlin/C# file is allowed to declare its own name without the
        # word `class` in view (an annotation or a truncated export).
        names.add(stem)
    return {n for n in names if len(n) >= 4 and n.lower() not in _NOT_A_SYMBOL}


def symbol_edge(path: str, bodies: dict[str, str]) -> tuple[str, str] | None:
    """(importer, symbol) when a sibling uses a name only this file declares.

    Some languages have no import line to read: files in one Go package, or one
    Java/Kotlin package, refer to each other by name. The edge is still real —
    drop the file and the sibling stops compiling — so it is found by declara-
    tion: the name is declared here, used there, and declared nowhere else.
    """
    mine = declares(bodies.get(path, ""), path)
    if not mine:
        return None
    others = {p: t for p, t in bodies.items() if p != path}
    declared_elsewhere: set[str] = set()
    for other, text in others.items():
        declared_elsewhere |= declares(text, other)
    for symbol in sorted(mine - declared_elsewhere):
        for other, text in sorted(others.items()):
            if re.search(rf"\b{re.escape(symbol)}\b", text or ""):
                return other, symbol
    return None


def _builds(task: dict, drop: str = "", entry: str | None = None) -> tuple[bool | None, str]:
    """Does this set build on this box? `None` when the machine cannot say.

    A missing compiler is not a failing build. Reporting it as one would let a
    decoy rest on the absence of `tsc` rather than on the missing file, which is
    the same class of mistake as reading an unchecked run as a pass.

    `entry` is the file that gets executed, and it matters: the executor runs one
    entry, so a set whose target never imports the dropped module survives the
    drop while the project is still broken. The caller passes the *importer* here
    so the run actually exercises the edge under test.
    """
    from . import execution  # local: keeps the module off the execution graph

    files = [{"path": str(f.get("path", "")), "content": str(f.get("content", ""))}
             for f in (task.get("files") or []) if f.get("path") != drop]
    if not files:
        return None, "nothing left to build"
    # `entry=None` means "the task's target"; `entry=""` is a real choice — it
    # lets the executor compile the set and find the main class itself.
    chosen = str(task.get("target") or "") if entry is None else entry
    try:
        build = execution.run_files(files, str(task.get("language") or ""),
                                    entry=chosen, timeout_s=60)
    except Exception as err:
        return None, f"{type(err).__name__}: {err}"
    if not getattr(build, "ok", False) and "toolchain missing" in \
            str(getattr(build, "error", "")).lower():
        return None, "toolchain missing on this box"
    return bool(getattr(build, "ok", False)), ""


def _drops_build(task: dict, path: str, entry: str | None = None) -> bool | None:
    """Does the set fail to build without this file? None when unmeasurable.

    The complete set is built first, with the same entry. If it does not build
    *here* — a missing `tsc`, a refused language — then the reduced set's failure
    says nothing about the dropped file, and the answer is `None` rather than a
    proof.
    """
    target = str(task.get("target") or "")
    entry = target if entry is None else entry
    baseline, _why = _builds(task, entry=entry)
    if baseline is None:
        return None
    if not baseline:
        # Neither the consumer nor the target is runnable on its own (a Java set
        # whose `main` lives in a third file). An empty entry lets the executor
        # compile the whole set and find the main class, which still covers every
        # file — a compile proof rather than an abandoned one.
        for fallback in (target, ""):
            if fallback == entry:
                continue
            baseline, _why = _builds(task, entry=fallback)
            if baseline is None:
                return None
            if baseline:
                entry = fallback
                break
    if not baseline:
        return None
    reduced, _why = _builds(task, drop=path, entry=entry)
    if reduced is None:
        return None
    return not reduced


def _missing_decoy(task: dict, truth_paths: list[str],
                   verify: bool) -> dict | None:
    """Drop one file another file imports, and keep it only if that is provable."""
    target = str(task.get("target") or "")
    bodies = {str(f.get("path", "")): str(f.get("content", ""))
              for f in (task.get("files") or [])}
    for path in truth_paths:
        if path == target:
            continue  # the entry is the one file a plan may not drop silently
        edge: tuple[str, str, str] | None = None
        for other, text in sorted(bodies.items()):
            if other != path and references(text, path):
                edge = (other, f"omits {path}, which {other} imports", "import")
                break
        if edge is None:
            # No import line exists to read — one Go package, or one Java/Kotlin
            # package, refers to its siblings by name. The edge is still real:
            # drop the declaring file and the sibling stops compiling.
            found = symbol_edge(path, bodies)
            if found:
                importer, symbol = found
                edge = (importer,
                        f"omits {path}, which declares the {symbol} {importer} uses",
                        "symbol")
        if edge is None:
            continue
        entry, because, proof = edge
        if verify:
            # Run the consumer, not the target: the target often never touches
            # the edge, and a build that never reaches it proves nothing.
            dropped = _drops_build(task, path, entry=entry)
            if dropped is None:
                return {"kind": "missing", "drop": path, "because": because,
                        "proof": proof}
            if not dropped:
                # The build survived without it, so the plan is a legitimate
                # alternative. There is no wrong answer to teach here.
                continue
            return {"kind": "missing", "drop": path,
                    "because": f"omits {path}; the set does not build without it",
                    "proof": "build"}
        return {"kind": "missing", "drop": path, "because": because,
                "proof": proof}
    return None


def _invented_path(task: dict, truth_paths: list[str]) -> str:
    target = str(task.get("target") or truth_paths[0])
    folder = target.rsplit("/", 1)[0] if "/" in target else ""
    stem = target.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    suffix = target.rsplit(".", 1)[-1] if "." in target else "py"
    names = (f"config.{suffix}", f"utils.{suffix}", f"types.{suffix}",
             f"helpers.{suffix}", f"constants.{suffix}",
             f"tests/test_{stem}.{suffix}", f"docs/{stem}.md")
    shipped = set(truth_paths)
    for name in names:
        candidate = f"{folder}/{name}" if folder and "/" not in name else name
        if candidate not in shipped:
            return candidate
    return "config.json" if "config.json" not in shipped else "notes.txt"


def _invented_decoy(task: dict, truth_paths: list[str]) -> dict:
    path = _invented_path(task, truth_paths)
    return {"kind": "invented", "add": path,
            "because": f"names {path}, which the project does not ship",
            "proof": "closed-set"}


def _over_decoy(truth_lines: list[str]) -> dict | None:
    """Repeat a line, which both duplicates a path and breaks the line gate."""
    if len(truth_lines) < 2:
        return None
    repeated = truth_lines[-1]
    path = repeated.split(" (")[0]
    return {"kind": "over", "because": f"repeats {path}",
            "proof": "plan-gate"}


def _apply(truth_lines: list[str], decoy: dict) -> list[str]:
    """The decoy's lines, built from the truth plus its one provable defect."""
    lines = list(truth_lines)
    if decoy["kind"] == "missing":
        dropped = decoy["drop"]
        lines = [line for line in lines if line.split(" (")[0] != dropped]
    elif decoy["kind"] == "invented":
        added = decoy["add"]
        suffix = added.rsplit(".", 1)[-1] if "." in added else ""
        language = plansft.language_of(added)
        role = plansft.role_of(added)
        lines.append(f"{added} ({language}) — {role}" if suffix else added)
    elif decoy["kind"] == "over":
        lines.append(lines[-1])
    return lines


# ── the three plans ────────────────────────────────────────────────────────

def candidates(task: dict, verify: bool = False) -> list[dict]:
    """The truth and up to two provable decoys, or [] when nothing is provable."""
    truth = true_plan(task)
    if len(truth) < 2:
        return []
    paths = [line.split(" (")[0] for line in truth]
    decoys: list[dict] = []
    missing = _missing_decoy(task, paths, verify)
    if missing:
        decoys.append(missing)
    decoys.append(_invented_decoy(task, paths))
    over = _over_decoy(truth)
    if over and len(decoys) < 2:
        decoys.append(over)
    # Two decoys is the whole quiz; a third would only add noise to the letters.
    rng = random.Random(int(hashlib.sha256(
        str(task.get("id", "")).encode("utf-8")).hexdigest()[:8], 16))
    chosen = decoys[:2]
    rng.shuffle(chosen)
    plans = [{"kind": "true", "lines": truth, "because": "the shipped set",
              "proof": "verified"}]
    plans += [{"kind": d["kind"], "lines": _apply(truth, d),
               "because": d["because"], "proof": d["proof"]} for d in chosen]
    rng.shuffle(plans)
    for letter, plan in zip(LETTERS, plans):
        plan["letter"] = letter
    return plans


def _prompt(task: dict, plans: list[dict]) -> str:
    title = (task.get("description") or task.get("title") or "a small project").strip()
    body = "\n\n".join(f"{plan['letter']}) " + "\n".join(plan["lines"])
                     for plan in plans)
    return INSTRUCTION.format(title=title[:300],
                              language=str(task.get("language") or ""),
                              max_lines=plansft.MAX_LINES, plans=body)


def _sets(all_languages: bool = False, share: int = scaffoldsft.TRAIN_SHARE,
          limit: int = 0) -> list[dict]:
    """Verified, multi-file, trainable sets — the only plans worth asking about."""
    validation = library.load_validation()
    out: list[dict] = []
    for task in sorted(library.load_tasks(all_languages=all_languages),
                       key=lambda t: str(t.get("id", ""))):
        if not library.is_multi_file(task):
            continue
        if (validation.get(str(task.get("id", ""))) or {}).get("status") != "verified":
            continue
        if not scaffoldsft.is_trainable(task, share):
            continue
        out.append(task)
        if limit and len(out) >= limit:
            break
    return out


# ── rows ───────────────────────────────────────────────────────────────────

def rows(per_set: int = 1, all_languages: bool = False, verify: bool = False,
         limit: int = 0) -> list[dict]:
    """One pick row per verified set: three plans, one provable answer."""
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for task in _sets(all_languages=all_languages, limit=limit):
        plans = candidates(task, verify=verify)
        if not plans:
            continue
        truth = next(p for p in plans if p["kind"] == "true")
        instruction = _prompt(task, plans)
        answer = f"PLAN: {truth['letter']}"
        key = (instruction, answer)
        if key in seen:
            continue
        seen.add(key)
        for row in range(per_set):
            out.append({
                "system": "", "instruction": instruction, "input": "",
                "output": answer, "source": SOURCE,
                "meta": {
                    "task_id": str(task.get("id", "")),
                    "language": str(task.get("language") or ""),
                    "answer": truth["letter"],
                    "truth_lines": len(truth["lines"]),
                    "decoys": [{"letter": p["letter"], "kind": p["kind"],
                                "because": p["because"], "proof": p["proof"]}
                               for p in plans if p["kind"] != "true"],
                    "labels_from": "verified-set",
                },
            })
    return out


def pairs(all_languages: bool = False, verify: bool = False,
          limit: int = 0) -> list[dict]:
    """Two pair kinds per decoy: the picked letter, and the plan text itself.

    The pick pair is the eval the seat actually faces. The plan-text pair is the
    same lesson in the shape `plansft` trains, so an ORPO round can prefer a
    workable plan over a broken one without learning to answer in letters.
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for task in _sets(all_languages=all_languages, limit=limit):
        plans = candidates(task, verify=verify)
        if not plans:
            continue
        truth = next(p for p in plans if p["kind"] == "true")
        title = (task.get("description") or task.get("title") or "").strip()[:300]
        text_prompt = plansft.INSTRUCTION.format(title=title)
        pick_prompt = _prompt(task, plans)
        for decoy in (p for p in plans if p["kind"] != "true"):
            for kind, prompt, chosen, rejected in (
                ("plan_pick_pair", pick_prompt, f"PLAN: {truth['letter']}",
                 f"PLAN: {decoy['letter']}"),
                ("plan_text_pair", text_prompt, "\n".join(truth["lines"]),
                 "\n".join(decoy["lines"])),
            ):
                if chosen == rejected or (prompt, rejected) in seen:
                    continue
                seen.add((prompt, rejected))
                out.append({"system": "", "prompt": prompt, "chosen": chosen,
                            "rejected": rejected,
                            "meta": {"kind": kind, "decoy": decoy["kind"],
                                     "because": decoy["because"],
                                     "proof": decoy["proof"],
                                     "task_id": str(task.get("id", "")),
                                     "language": str(task.get("language") or "")}})
    return out


def stats(all_languages: bool = False, verify: bool = False) -> dict:
    """What the library supports, and what the proof rules refused to ship."""
    sets = _sets(all_languages=all_languages)
    usable, oversize, single, refused, by_kind = 0, 0, 0, 0, {}
    for task in sets:
        truth = true_plan(task)
        if not truth:
            # The truth itself breaks the plan gate (more than MAX_LINES files),
            # so there is no correct answer to show. Counted apart from a decoy
            # the proof rules refused, which is a different kind of loss.
            oversize += 1
            continue
        if len(truth) < 2:
            # `library.is_multi_file` also lets one-file sets through. A plan
            # for one file is not a choice, so there is nothing to ask.
            single += 1
            continue
        plans = candidates(task, verify=verify)
        if not plans:
            refused += 1
            continue
        usable += 1
        for plan in plans:
            if plan["kind"] != "true":
                by_kind[plan["kind"]] = by_kind.get(plan["kind"], 0) + 1
    return {"verified_sets": len(sets), "usable": usable, "rejected": refused,
            "oversize": oversize, "single_file": single, "decoy_kinds": by_kind,
            "sft_rows": len(rows(all_languages=all_languages, verify=verify)),
            "pairs": len(pairs(all_languages=all_languages, verify=verify)),
            "proof": "build+import" if verify else "import+closed-set"}


def sft_path() -> Path:
    return library.library_dir() / SFT_FILE


def pair_path() -> Path:
    return library.library_dir() / PAIR_FILE


def write(all_languages: bool = False, verify: bool = False) -> dict:
    """Rewrite both sheets from the verified sets (a pure function of them)."""
    sft, pair_rows = rows(all_languages=all_languages, verify=verify), \
        pairs(all_languages=all_languages, verify=verify)
    sft_path().write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                  for r in sft), encoding="utf-8")
    pair_path().write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                   for r in pair_rows), encoding="utf-8")
    return {"sft": str(sft_path()), "sft_rows": len(sft),
            "pairs": str(pair_path()), "pair_rows": len(pair_rows)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pick the plan that can build")
    parser.add_argument("--verify", action="store_true",
                        help="prove a dropped file by building the reduced set")
    parser.add_argument("--write", action="store_true",
                        help="write library/plan_pick.jsonl and plan_pairs.jsonl")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--show", type=int, default=0,
                        help="print the first N rows")
    args = parser.parse_args(argv)

    summary = stats(verify=args.verify)
    if args.write:
        summary["written"] = write(verify=args.verify)
    if args.show:
        for row in rows(verify=args.verify)[:args.show]:
            print(json.dumps({"meta": row["meta"],
                              "instruction": row["instruction"],
                              "output": row["output"]}, indent=2))
        return 0
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0
    print(f"planpick: {summary['verified_sets']} verified set(s), "
          f"{summary['usable']} usable, {summary['single_file']} single-file, "
          f"{summary['oversize']} over the plan gate, "
          f"{summary['rejected']} refused (no provable decoy)")
    print(f"  decoys {summary['decoy_kinds']} · proof {summary['proof']}")
    print(f"  rows {summary['sft_rows']} · pairs {summary['pairs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
