"""grow — generate new library tasks that beat the reference, or are discarded.

The rule is deliberately strict, because the library is only worth what it can
prove:

  1. the coder writes a candidate for a CONFIRMED task
  2. it must compile and run (real toolchain, exit 0)
  3. it must not be a duplicate of something already in the library
  4. when the reference's output is deterministic, the candidate must produce
     the same output
  5. the judge must rank the candidate STRICTLY above the reference

A tie is not a win. A "looks nicer" rewrite that the judge prefers on
versatility but which changes behaviour is rejected at step 4. Only survivors
are appended to `data/library/grown.jsonl` and get a verified validation
record, so `library.confirmed()` — and therefore tournaments and training —
picks them up like any hand-written library entry.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config, execution, judge, library, repair, tournament

JOB_LOCK = threading.RLock()
JOB: dict = {"state": "idle", "seeds": 0, "done": 0, "accepted": 0, "current": "",
             "started_at": "", "finished_at": "", "error": "", "summary": {},
             "run_dir": ""}
_THREAD: threading.Thread | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _status_file() -> Path:
    return config.data_dir() / "grow.status.json"


def status() -> dict:
    with JOB_LOCK:
        snapshot = dict(JOB)
    if snapshot.get("state") == "idle":
        path = _status_file()
        if path.exists():
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
                if saved.get("state") in ("done", "failed"):
                    snapshot = {**snapshot, **saved}
            except (OSError, json.JSONDecodeError):
                pass
    return snapshot


def _publish(**update) -> None:
    with JOB_LOCK:
        JOB.update(update)
        payload = dict(JOB)
    try:
        _status_file().write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _normalize(text: str) -> str:
    return " ".join((text or "").split())


def _run(task: dict, code: str, timeout_s: float) -> dict:
    return tournament._run_code(task, code, timeout_s, repeats=1)


def measurable_improvement(candidate: dict, reference: dict, decision: dict,
                           size_slack: float = 0.10, speed_slack: float = 0.10,
                           speed_floor_ms: int = 50) -> tuple[bool, str]:
    """A judge win alone is not enough: the numbers must support it.

    Rejects a build that regressed a measured dimension badly, and rejects a
    "win" with no measured improvement at all (the judge contradicted itself)
    or one whose own dimensions favour the reference.
    """
    ref_bytes = max(1, int(reference.get("bytes") or 0))
    cand_bytes = int(candidate.get("bytes") or 0)
    ref_ms = int(reference.get("runtime_ms") or 0)
    cand_ms = int(candidate.get("runtime_ms") or 0)

    if cand_bytes > ref_bytes * (1 + size_slack):
        return False, f"size regressed: {cand_bytes} B vs {ref_bytes} B"
    allowed_ms = max(ref_ms * (1 + speed_slack), ref_ms + speed_floor_ms)
    if cand_ms > allowed_ms:
        return False, f"runtime regressed: {cand_ms} ms vs {ref_ms} ms"

    smaller = cand_bytes < ref_bytes
    faster = ref_ms > 0 and cand_ms < ref_ms * (1 - speed_slack)
    if not (smaller or faster):
        return False, f"no measured improvement ({cand_bytes} B/{cand_ms} ms vs {ref_bytes} B/{ref_ms} ms)"

    dimensions = {str(k): str(v).upper() for k, v in (decision.get("dimensions") or {}).items()}
    if dimensions and not any(v == "B" for v in dimensions.values()):
        return False, "verdict contradicts its own dimensions"
    return True, "smaller" if smaller else "faster"


def _verification_record(task: dict, grown: dict, result: dict, seed_id: str) -> dict:
    return {
        "id": task["id"],
        "language": task["language"],
        "status": "verified",
        "checked_at": _now(),
        "duration_ms": result.get("runtime_ms", 0),
        "command": result.get("command", ""),
        "exit_code": result.get("exit_code", 0),
        "stdout": (result.get("stdout") or "")[-1000:],
        "stderr": "",
        "error": "",
        "note": f"grown: judged better than {seed_id} ({grown['style']} style)",
    }


def _append_verification(record: dict) -> None:
    with library.validation_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _grown_task(task: dict, style: str, code: str, result: dict, decision: dict,
                reference: dict) -> dict:
    seed_slug = task["id"].split("/")[-1]
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()[:8]
    return {
        "id": f"grown/{seed_slug}-{style}-{digest}",
        "origin": "grown",
        "language": task["language"],
        "title": f"{task['title']} — {style} rewrite",
        "description": task.get("description", ""),
        "code": code,
        "iface": "",
        "tags": [*(task.get("tags") or []), "grown", style],
        "category": "grown",
        "runnable": True,
        "source": f"seed:{task['id']}",
        "seed_id": task["id"],
        "style": style,
        "provenance": {
            "bytes": len(code.encode("utf-8")),
            "reference_bytes": len(task["code"].encode("utf-8")),
            "runtime_ms": result.get("runtime_ms", 0),
            "reference_runtime_ms": reference.get("runtime_ms", 0),
            "verdict": {k: decision.get(k) for k in ("winner", "reason", "dimensions", "source")},
            "generated_at": _now(),
        },
    }


def expand(seed_count: int, styles: list[str], timeout_s: float = 20,
           coder=None, judge_fn=None, seed_ids: list[str] | None = None) -> dict:
    """Grow the library from up to `seed_count` confirmed tasks.

    `seed_ids` pins the exact seeds, which is what makes two coders comparable:
    the same tasks, styles and judge, with only the weights changed.
    """
    coder = coder or repair.OllamaClient()
    judge_fn = judge_fn or judge.compare

    confirmed = {t["id"] for t in library.confirmed()}
    # Growth restyles a single program into new idioms; a file set has no single
    # program to restyle, so scaffold tasks are never seeds here.
    seeds = [t for t in library.load_tasks()
             if t["id"] in confirmed and t.get("runnable")
             and t.get("language") in execution.TOOLCHAINS
             and not library.is_multi_file(t)]
    if seed_ids:
        by_id = {t["id"]: t for t in seeds}
        seeds = [by_id[s] for s in seed_ids if s in by_id]
    seeds = seeds[: max(0, seed_count)]
    if not seeds:
        _publish(state="failed", error="no confirmed runnable tasks — validate the library first",
                 finished_at=_now())
        return status()

    run_dir = config.data_dir() / "grow" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    _publish(state="running", seeds=len(seeds), done=0, accepted=0, current="",
             error="", started_at=_now(), finished_at="", summary={},
             run_dir=str(run_dir))

    rejected = {"invalid": 0, "identical": 0, "behavior_mismatch": 0, "tie": 0,
                "lost": 0, "no_improvement": 0, "duplicate": 0, "judge_error": 0,
                "coder_failed": 0}
    accepted: list[dict] = []
    decisions_path = run_dir / "decisions.jsonl"

    with decisions_path.open("w", encoding="utf-8") as handle:
        for index, seed in enumerate(seeds, start=1):
            reference = _run(seed, seed["code"], timeout_s)
            second = _run(seed, seed["code"], timeout_s)
            deterministic = _normalize(reference.get("stdout", "")) == _normalize(second.get("stdout", ""))
            reference_stdout = _normalize(reference.get("stdout", ""))
            reference_variant = {
                "style": "reference",
                "code": seed["code"],
                "bytes": len(seed["code"].encode("utf-8")),
                "runtime_ms": reference.get("runtime_ms", 0),
                "valid": bool(reference.get("valid")),
                "stdout_match": True,
            }

            for style in styles:
                _publish(current=f"{seed['language']}: {seed['title'][:40]} ({style})")
                entry = {"seed": seed["id"], "style": style, "at": _now()}
                try:
                    code = repair.extract_code(coder.complete(
                        tournament._style_prompt(seed, style)))
                except Exception as err:
                    rejected["coder_failed"] += 1
                    handle.write(json.dumps({**entry, "accepted": False,
                                             "reason": f"coder failed: {err}"[:300]}) + "\n")
                    continue

                if not code.strip() or code.strip() == seed["code"].strip():
                    rejected["identical"] += 1
                    handle.write(json.dumps({**entry, "accepted": False,
                                             "reason": "identical to the reference"}) + "\n")
                    continue

                result = _run(seed, code, timeout_s)
                if not result.get("valid"):
                    rejected["invalid"] += 1
                    handle.write(json.dumps({**entry, "accepted": False,
                                             "reason": f"did not compile/run: {result.get('error') or result.get('stderr','')[:200]}"}) + "\n")
                    continue

                if deterministic and _normalize(result.get("stdout", "")) != reference_stdout:
                    rejected["behavior_mismatch"] += 1
                    handle.write(json.dumps({**entry, "accepted": False,
                                             "reason": "output differs from the deterministic reference"}) + "\n")
                    continue

                candidate = {
                    "style": style,
                    "code": code,
                    "bytes": len(code.encode("utf-8")),
                    "runtime_ms": result.get("runtime_ms", 0),
                    "valid": True,
                    "stdout_match": _normalize(result.get("stdout", "")) == reference_stdout,
                }
                decision = judge_fn(seed, seed["code"], reference_variant, candidate)
                winner = decision.get("winner", "")
                if not winner:
                    rejected["judge_error"] += 1
                    handle.write(json.dumps({**entry, "accepted": False,
                                             "reason": decision.get("error", "no verdict")}) + "\n")
                    continue
                if winner == "tie":
                    rejected["tie"] += 1
                    handle.write(json.dumps({**entry, "accepted": False,
                                             "reason": decision.get("reason", "tie")}) + "\n")
                    continue
                if winner != "B":
                    rejected["lost"] += 1
                    handle.write(json.dumps({**entry, "accepted": False,
                                             "reason": decision.get("reason", "reference won")}) + "\n")
                    continue

                better, why = measurable_improvement(candidate, reference_variant, decision)
                if not better:
                    rejected["no_improvement"] += 1
                    handle.write(json.dumps({**entry, "accepted": False,
                                             "reason": f"judge said B but {why}"}) + "\n")
                    continue

                grown = _grown_task(seed, style, code, result, decision, reference)
                grown["provenance"]["improvement"] = why
                added, reason = library.append_grown(grown)
                if not added:
                    rejected["duplicate"] += 1
                    handle.write(json.dumps({**entry, "accepted": False, "reason": reason}) + "\n")
                    continue
                _append_verification(_verification_record(grown, grown, result, seed["id"]))
                accepted.append({
                    "id": grown["id"], "seed": seed["id"], "language": seed["language"],
                    "style": style, "bytes": grown["provenance"]["bytes"],
                    "reference_bytes": grown["provenance"]["reference_bytes"],
                    "runtime_ms": grown["provenance"]["runtime_ms"],
                    "reference_runtime_ms": grown["provenance"]["reference_runtime_ms"],
                    "improvement": why,
                    "reason": decision.get("reason", ""),
                })
                handle.write(json.dumps({**entry, "accepted": True,
                                         "task": grown["id"],
                                         "reason": decision.get("reason", "")}) + "\n")
            _publish(done=index, accepted=len(accepted))

    summary = {
        "seeds": len(seeds),
        "candidates": len(seeds) * len(styles),
        "accepted": len(accepted),
        "rejected": rejected,
        "accepted_tasks": accepted,
        "avg_bytes": round(sum(a["bytes"] for a in accepted) / len(accepted)) if accepted else 0,
        "avg_reference_bytes": round(sum(a["reference_bytes"] for a in accepted) / len(accepted)) if accepted else 0,
        "finished_at": _now(),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    _publish(state="done", finished_at=_now(), current="", accepted=len(accepted),
             summary=summary)
    return status()


def start(seed_count: int, styles: list[str] | None = None,
          timeout_s: float | None = None, seed_ids: list[str] | None = None) -> dict:
    global _THREAD
    with JOB_LOCK:
        if JOB.get("state") == "running":
            return {**status(), "error": "a growth run is already in progress"}
        confirmed = {t["id"] for t in library.confirmed()}
        runnable = [t for t in library.load_tasks()
                    if t["id"] in confirmed and t.get("runnable")
                    and not library.is_multi_file(t)]
        if not runnable:
            return {**status(), "error": "no confirmed runnable tasks — validate the library first"}
        chosen_styles = styles or ["terse", "idiomatic", "fast"]
        JOB.update(state="running", error="", summary={})
    _THREAD = threading.Thread(
        target=expand,
        args=(int(seed_count), list(chosen_styles),
              float(timeout_s or config.load()["tournament"]["run_timeout_s"]),
              None, None, list(seed_ids) if seed_ids else None),
        daemon=True,
    )
    _THREAD.start()
    return status()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Grow the library with judged, verified rewrites")
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--styles", default="terse,idiomatic,fast")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--seed-ids", default="",
                        help="comma-separated seed ids, to pin a comparison run")
    args = parser.parse_args(argv)
    styles = [s.strip() for s in args.styles.split(",") if s.strip()]
    seed_ids = [s.strip() for s in args.seed_ids.split(",") if s.strip()]
    result = expand(args.seeds, styles, args.timeout, seed_ids=seed_ids)
    print(json.dumps({k: result.get(k) for k in
                      ("state", "seeds", "done", "accepted", "summary", "error")}, indent=2))
    return 0 if result.get("state") == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
