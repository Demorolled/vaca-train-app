"""seatplay — play a sheet against a player, and bank what it got wrong.

A sheet proves nothing until a model has been made to answer it. This is the
puzzle trainer's `play_*` loop, kept for the seats instead of for a puzzle: hand
each row to a player, score the reply against the row's own label, and write the
misses back as preference pairs.

Scoring follows the answer shape the row was built for:

* `qa` — the reply must parse as JSON and its `status` must match the label the
  toolchain justified.
* `plan` — the reply must carry `PLAN: <letter>` and the letter must match.

A reply that cannot be read at all is counted separately from a wrong answer:
prose when JSON was asked for is a contract failure, and a confident wrong
verdict is not the same defect. Neither is a row.

Nothing here is invented. A correct answer writes no row — the sheet already
holds the correct one — and a miss becomes a pair with the sheet's label as
`chosen` and the model's own text as `rejected`. The loop keeps no model state
and no difficulty ladder: pacing belongs to `trainapp.battery`, which measures a
candidate on held-out tasks, not to the thing that generates its data.

    python3 -m trainapp.seatplay --kind qa --dry-run     # what it would play
    python3 -m trainapp.seatplay --kind qa --limit 5     # play five, bank misses
    python3 -m trainapp.seatplay --sheet my_rows.jsonl --player ollama
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from . import config

QA_STATUSES = ("PASSED", "FAILED")
PLAN_LINE = re.compile(r"PLAN\s*:\s*([A-Za-z])")


def _json_object(text: str) -> dict | None:
    """The first JSON object in a reply, fenced or not — the seat's own parser."""
    body = (text or "").strip()
    start = body.find("{")
    end = body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(body[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def kind_of(row: dict) -> str:
    """Which answer shape this row was built for."""
    meta = row.get("meta") or {}
    source = str(row.get("source") or "")
    if source.endswith(":qa") or "status" in meta and "answer" not in meta:
        return "qa"
    if ":plan" in source or meta.get("answer"):
        return "plan"
    if str(row.get("output") or "").startswith("PLAN:"):
        return "plan"
    return "qa"


def score(row: dict, reply: str) -> dict:
    """Did the reply match the row's label, and how far off was it if not."""
    kind = kind_of(row)
    text = (reply or "").strip()
    if kind == "plan":
        match = PLAN_LINE.search(text.upper())
        if not match:
            return {"correct": False, "parsed": False, "got": text[:200],
                    "why": "no PLAN: <letter> in the reply"}
        got = match.group(1).upper()
        want = str((row.get("meta") or {}).get("answer")
                   or str(row.get("output", "")).split(":")[-1]).strip().upper()
        return {"correct": got == want, "parsed": True, "got": got,
                "why": "" if got == want else f"picked {got}, the answer is {want}"}
    verdict = _json_object(text)
    if verdict is None:
        return {"correct": False, "parsed": False, "got": text[:200],
                "why": "the reply was not JSON"}
    got = str(verdict.get("status") or "").upper()
    want = str((row.get("meta") or {}).get("status") or "").upper()
    if not want:
        want_json = _json_object(str(row.get("output") or ""))
        want = str((want_json or {}).get("status") or "").upper()
    return {"correct": got == want, "parsed": got in QA_STATUSES,
            "got": got or text[:200],
            "why": "" if got == want else f"said {got or 'nothing'}, the gate says {want}"}


def play(rows: list[dict], chat, limit: int = 0,
         progress=None) -> dict:
    """Serve every row to the player, score it, and collect the misses as pairs."""
    played = correct = wrong = unparsed = 0
    by_kind: dict[str, dict] = {}
    pairs: list[dict] = []
    for row in rows:
        if limit and played >= limit:
            break
        kind = kind_of(row)
        try:
            reply = chat.ask(row.get("system") or "", row.get("instruction") or "",
                             json_object=(kind == "qa"), temperature=0.0)
        except Exception as err:  # a dead player must report, not crash the loop
            return {"error": f"{type(err).__name__}: {err}", "played": played,
                    "correct": correct, "wrong": wrong, "unparsed": unparsed,
                    "by_kind": by_kind, "pairs": pairs}
        text = str((reply or {}).get("content") or "")
        result = score(row, text)
        played += 1
        bucket = by_kind.setdefault(kind, {"played": 0, "correct": 0, "wrong": 0,
                                           "unparsed": 0})
        bucket["played"] += 1
        if result["correct"]:
            correct += 1
            bucket["correct"] += 1
        elif not result["parsed"]:
            unparsed += 1
            bucket["unparsed"] += 1
        else:
            wrong += 1
            bucket["wrong"] += 1
            meta = dict(row.get("meta") or {})
            meta.update({"kind": "seat_miss", "seat": kind, "why": result["why"]})
            pairs.append({"system": row.get("system") or "",
                          "prompt": row.get("instruction") or "",
                          "chosen": str(row.get("output") or ""),
                          "rejected": text.strip()[:4000],
                          "meta": meta})
        if progress:
            progress(played, result)
    accuracy = round(correct / played, 4) if played else 0.0
    return {"played": played, "correct": correct, "wrong": wrong,
            "unparsed": unparsed, "accuracy": accuracy, "by_kind": by_kind,
            "pairs": pairs}


def sheet_rows(kind: str, limit: int = 0) -> list[dict]:
    """The rows a `--kind` names, built fresh from what is on disk."""
    from . import planpick, verdictpick  # local: each pulls its own sources

    if kind == "qa":
        return verdictpick.rows(limit=limit)
    if kind == "plan":
        return planpick.rows(limit=limit)
    raise ValueError(f"unknown sheet kind: {kind}")


def load_sheet(path: str | Path) -> list[dict]:
    rows: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("instruction"):
            rows.append(row)
    return rows


def pairs_path() -> Path:
    return config.dataset_dir() / "seat_miss_pairs.jsonl"


def write_pairs(pairs: list[dict], path: str | Path | None = None) -> Path:
    target = Path(path) if path else pairs_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n"
                              for p in pairs), encoding="utf-8")
    return target


def inventory(rows: list[dict]) -> dict:
    """What a run would play, without a player — labels, kinds, sources."""
    by_kind: dict[str, int] = {}
    for row in rows:
        kind = kind_of(row)
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {"rows": len(rows), "by_kind": by_kind,
            "answerable": sum(1 for row in rows
                              if str(row.get("output") or "").strip())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Play seat rows against a player and bank the misses")
    parser.add_argument("--kind", choices=("qa", "plan"), default="qa",
                        help="which sheet to build when --sheet is not given")
    parser.add_argument("--sheet", default="", help="a rows jsonl to play instead")
    parser.add_argument("--player", default="",
                        help="band player to use; the leader when empty")
    parser.add_argument("--limit", type=int, default=0, help="stop after N rows")
    parser.add_argument("--dry-run", action="store_true",
                        help="report the sheet without calling a model")
    parser.add_argument("--out", default="", help="where to write the miss pairs")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rows = (load_sheet(args.sheet) if args.sheet
            else sheet_rows(args.kind, limit=args.limit))
    if args.dry_run:
        report = inventory(rows)
        print(json.dumps(report, indent=2) if args.json else
              f"seatplay: {report['rows']} row(s) available, "
              f"{report['by_kind']}, {report['answerable']} with a label")
        return 0

    from . import builder  # local: only a real play needs the chat client

    chat = builder.chat_for(args.player)
    report = play(rows, chat, limit=args.limit)
    if report.get("error"):
        print(f"seatplay: player failed — {report['error']}")
        return 1
    written = write_pairs(report["pairs"], args.out or None)
    summary = {k: report[k] for k in ("played", "correct", "wrong", "unparsed",
                                      "accuracy", "by_kind")}
    summary["pairs"] = len(report["pairs"])
    summary["pairs_path"] = str(written)
    print(json.dumps(summary, indent=2) if args.json else
          f"seatplay: {report['played']} played · {report['correct']} correct · "
          f"{report['wrong']} wrong · {report['unparsed']} unreadable "
          f"→ {report['accuracy']:.0%}; {len(report['pairs'])} pair(s) to {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
