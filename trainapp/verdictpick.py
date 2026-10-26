"""verdictpick — QA verdicts as training rows, labelled by the toolchain.

The QA seat is the one seat whose opinion the gate can check. `orchestra.qa_node`
records both what QA said (`status`, `errors`, `scope`, `files`) and what the
toolchain then proved (`build_ok`, `output_ok`, `matches`), so a finished run is
a *labelled* example: the code, the prompt the seat was given, and the verdict a
careful reviewer would have returned.

The rule is deliberately narrow, because a verdict row is only worth what its
label is worth:

* the build failed — the label is FAILED, with or without an expected output,
  because a run that did not run is a failure by itself.
* the build passed but `matches` is None — nothing was compared, so nothing is
  proved. No row. A verdict echoed from an unchecked build would teach guessing
  with confidence.
* the build passed and printed something other than the contract — FAILED,
  carrying the expected/actual pair the gate recorded.
* the build passed and its output matched — PASSED. A QA that said FAILED here
  overruled a verified build; `qa_node` already calls that `advisory`, and that
  pair is the most valuable row this module produces.

The gate can only certify the contract it was handed, so one more check comes
before any of that: if the requirement itself implies a different output
(`"the sum of 2 and 3"` derives `5`) and the copy graded the run against
something else, the run proved nothing about the reviewer and the copy is
refused. A build that passed a contract nobody should have written is not
labelled PASSED just because the two numbers matched each other.

Only orchestra copies are read (`data/band/<stamp>/<requirement>/`): a builder
copy has no QA prompt in it, so there is nothing to teach from. Only the *last*
pass carries a toolchain label — the per-pass `attempt-N/files` exist, but the
build result recorded in the copy belongs to the final pass, and labelling an
earlier attempt with it would be an invented label.

The prompt is rebuilt from the constants the seat is given at run time
(`orchestra.QA_SYSTEM`, `orchestra.QA_ASK`, `orchestra._gate_note`), so a
training row and an eval prompt are the same string rather than two that drift.

    python3 -m trainapp.verdictpick            # what is on disk, and the labels
    python3 -m trainapp.verdictpick --write    # library/qa_sft.jsonl + qa_pairs.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from . import expect, harvest, library, orchestra

SOURCE = "band:qa"
SFT_FILE = "qa_sft.jsonl"
PAIR_FILE = "qa_pairs.jsonl"


# ── reading a copy ─────────────────────────────────────────────────────────

def _json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def blueprint_of(run: dict) -> dict:
    """The copy's own blueprint, which holds the exercise fields harvest drops."""
    saved = _json(Path(str(run.get("path") or "")) / "blueprint.json")
    if saved:
        return saved
    planned = (run.get("blueprint") or {}).get("files") or []
    return {"entry": (run.get("blueprint") or {}).get("entry", ""),
            "project_manifest": {str(f.get("path", "")): str(f.get("purpose", ""))
                                 for f in planned if f.get("path")}}


def _gate_note(bp: dict) -> str:
    """The note the seat actually saw, built by the seat's own function.

    A stand-in board is enough: `_gate_note` reads three attributes and nothing
    else. Reusing it is the point — a copy of that text here would be a second
    version of the contract, free to drift from the one the seat is graded on.
    """
    board = SimpleNamespace(run_cmd=str(bp.get("run") or ""),
                            inputs=dict(bp.get("inputs") or {}),
                            expected_stdout=str(bp.get("expected_stdout") or ""))
    return orchestra._gate_note(board)


def prompt_for(run: dict) -> str:
    """The exact QA prompt for this copy's final pass."""
    bp = blueprint_of(run)
    language = run.get("language") or "python"
    files = run.get("files") or []
    code = "\n\n".join(orchestra._block(f["path"], f["content"], language)
                       for f in files)
    manifest = bp.get("project_manifest") or {}
    if not manifest:
        manifest = {str(f.get("path", "")): "" for f in files}
    blueprint = "\n".join(f"- {path} — {purpose or 'no purpose stated'}"
                          for path, purpose in manifest.items())
    return orchestra.QA_ASK.format(
        requirement=run.get("requirement") or "",
        language=language,
        blueprint=blueprint or "(no blueprint)",
        code=code[:24000],
        gate=_gate_note(bp),
    )


# ── the label ──────────────────────────────────────────────────────────────

def refusal_reason(run: dict) -> str:
    """Why this copy cannot be labelled, or "" when it can.

    `contract` is the interesting one: the gate compared the run against an
    expectation the requirement itself contradicts, which is the self-agreement
    failure the whole pipeline is built to refuse.
    """
    build = run.get("build") or {}
    bp = blueprint_of(run)
    want = str(bp.get("expected_stdout") or "").strip()
    requirement = str(run.get("requirement") or "")
    if want:
        derived = str(expect.derive(requirement).get("expected") or "").strip()
        if derived and derived != want:
            return (f"contract: the requirement derives {derived!r} but the run "
                    f"was graded against {want!r}")
    if not bool(build.get("ok")):
        return ""  # a run that did not run is a failure on its own
    if build.get("matches") is None:
        return "unchecked: the build ran but nothing was compared"
    return ""


def label_for(run: dict) -> dict | None:
    """The verdict the toolchain justifies, or None when it proved nothing."""
    if refusal_reason(run):
        return None
    build = run.get("build") or {}
    ok = bool(build.get("ok"))
    matched = build.get("matches")
    if ok and matched is None:
        # It ran, but nobody said what it had to print, so no verdict is proved.
        return None
    if ok and matched is True:
        return {"status": "PASSED", "errors": [], "scope": "code", "files": []}
    error = str(build.get("error") or "").strip() or "the run failed"
    paths = [str(f.get("path", "")) for f in (run.get("files") or [])]
    blamed = orchestra._blame_from_output(error, paths)
    return {"status": "FAILED", "errors": [error], "scope": "code",
            "files": [blamed] if blamed else []}


def agrees(recorded: dict, label: dict) -> bool:
    """Did the seat reach the verdict the toolchain justifies?

    Status is the decision the loop acts on — a FAILED that should have been
    PASSED rewrites a working file, and the reverse ships a broken one — so the
    two are compared on status. The blamed file is graded separately, in the
    row's `meta.blamed_ok`, because a right status with the wrong file is still
    a usable row.
    """
    return str(recorded.get("status") or "").upper() == label["status"]


def _recorded(run: dict) -> dict:
    """The final pass's verdict, stripped of the harness's own columns.

    `build_ok` / `output_ok` / `advisory` are notes the harness added beside the
    verdict. A rejected side of a pair has to look like something the model
    could have said, so they are removed here rather than taught as prose.
    """
    verdicts = run.get("qa") or []
    if not verdicts:
        return {}
    last = verdicts[-1]
    return {"status": str(last.get("status") or "").upper(),
            "errors": [str(e) for e in (last.get("errors") or [])],
            "scope": str(last.get("scope") or "code"),
            "files": [str(p) for p in (last.get("files") or [])]}


# ── rows ───────────────────────────────────────────────────────────────────

def _labeled() -> list[tuple[dict, dict, dict]]:
    """(run, label, recorded verdict) for every copy whose build proved something."""
    out: list[tuple[dict, dict, dict]] = []
    for run in harvest.all_runs():
        if run.get("kind") != "orchestra":
            continue
        label = label_for(run)
        if label is None:
            continue
        out.append((run, label, _recorded(run)))
    return out


def rows(limit: int = 0) -> list[dict]:
    """One SFT row per labelled run: the seat's prompt, the toolchain's verdict."""
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for run, label, recorded in _labeled():
        prompt = prompt_for(run)
        answer = json.dumps(label, ensure_ascii=False)
        key = (prompt, answer)
        if key in seen:
            continue
        seen.add(key)
        build = run.get("build") or {}
        meta = {
            "run": str(run.get("path") or ""), "model": str(run.get("model") or ""),
            "language": str(run.get("language") or ""),
            "status": label["status"],
            "build_ok": bool(build.get("ok")), "matches": build.get("matches"),
            "passes": int(run.get("attempts") or 0),
            "label_from": "toolchain",
        }
        if recorded:
            meta["agrees"] = agrees(recorded, label)
            meta["advisory"] = bool((run.get("qa") or [])[-1].get("advisory"))
            blamed = label["files"]
            meta["blamed_ok"] = (not blamed
                                 or bool(set(blamed) & set(recorded.get("files") or [])))
        out.append({"system": orchestra.QA_SYSTEM, "instruction": prompt,
                    "input": "", "output": answer, "source": SOURCE,
                    "meta": meta})
        if limit and len(out) >= limit:
            break
    return out


def pairs(limit: int = 0) -> list[dict]:
    """Preference pairs where the seat's verdict disagreed with the toolchain.

    Both directions are here, and they are not the same lesson:

    * QA said FAILED over a verified build — the reviewer invented a requirement
      no other seat was given, which is the drift this seat is famous for.
    * QA said PASSED over a build that failed or printed the wrong thing — the
      reviewer missed the one thing the gate caught.
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for run, label, recorded in _labeled():
        if not recorded or agrees(recorded, label):
            continue
        prompt = prompt_for(run)
        chosen = json.dumps(label, ensure_ascii=False)
        rejected = json.dumps(recorded, ensure_ascii=False)
        if chosen == rejected or (prompt, rejected) in seen:
            continue
        seen.add((prompt, rejected))
        why = ("overruled a verified build" if label["status"] == "PASSED"
               else "passed a build the gate rejected")
        out.append({"system": orchestra.QA_SYSTEM, "prompt": prompt,
                    "chosen": chosen, "rejected": rejected,
                    "meta": {"kind": "qa_pair", "why": why,
                             "run": str(run.get("path") or ""),
                             "language": str(run.get("language") or ""),
                             "label_from": "toolchain"}})
        if limit and len(out) >= limit:
            break
    return out


def stats() -> dict:
    """What the copies on disk support, including what they refuse to label."""
    runs = [r for r in harvest.all_runs() if r.get("kind") == "orchestra"]
    labeled = _labeled()
    refused: dict[str, int] = {}
    for run in runs:
        if label_for(run) is not None:
            continue
        reason = refusal_reason(run).split(":")[0] or "unknown"
        refused[reason] = refused.get(reason, 0) + 1
    agree = sum(1 for _run, label, rec in labeled if rec and agrees(rec, label))
    advisory = sum(1 for run, _label, _rec in labeled
                   if (run.get("qa") or [])[-1].get("advisory"))
    by_status: dict[str, int] = {}
    for _run, label, _rec in labeled:
        by_status[label["status"]] = by_status.get(label["status"], 0) + 1
    return {"runs": len(runs), "labelled": len(labeled),
            "unlabelled_unchecked": refused.get("unchecked", 0),
            "refused_contract": refused.get("contract", 0),
            "refused": refused,
            "agreed": agree, "disagreed": len(labeled) - agree,
            "advisory": advisory, "by_status": by_status,
            "sft_rows": len(rows()), "pairs": len(pairs())}


# ── sheets ─────────────────────────────────────────────────────────────────

def sft_path() -> Path:
    return library.library_dir() / SFT_FILE


def pair_path() -> Path:
    return library.library_dir() / PAIR_FILE


def write() -> dict:
    """Rewrite both sheets from the copies on disk.

    Rewritten, not appended: the rows are a pure function of the runs, so a
    second call cannot duplicate a run and a deleted run disappears from the
    sheet instead of lingering in it.
    """
    sft, pair_rows = rows(), pairs()
    sft_path().write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                  for r in sft), encoding="utf-8")
    pair_path().write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                   for r in pair_rows), encoding="utf-8")
    return {"sft": str(sft_path()), "sft_rows": len(sft),
            "pairs": str(pair_path()), "pair_rows": len(pair_rows)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QA verdict rows labelled by the toolchain")
    parser.add_argument("--write", action="store_true",
                        help="write library/qa_sft.jsonl and qa_pairs.jsonl")
    parser.add_argument("--json", action="store_true", help="print the stats as JSON")
    parser.add_argument("--show", type=int, default=0,
                        help="print the first N rows instead of the summary")
    args = parser.parse_args(argv)

    summary = stats()
    if args.write:
        summary["written"] = write()
    if args.show:
        for row in rows(limit=args.show):
            print(json.dumps({"meta": row["meta"],
                              "output": row["output"],
                              "prompt_head": row["instruction"][:400]}, indent=2))
        return 0
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0
    print(f"verdictpick: {summary['runs']} orchestra run(s), "
          f"{summary['labelled']} labelled, {summary['refused']} refused")
    print(f"  agreed {summary['agreed']} · disagreed {summary['disagreed']} "
          f"· advisory {summary['advisory']} · {summary['by_status']}")
    print(f"  rows {summary['sft_rows']} · pairs {summary['pairs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
