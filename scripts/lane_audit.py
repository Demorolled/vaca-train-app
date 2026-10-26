"""lane_audit — does every pool set still build with its own reference?

A pool set is only a measurement if the reference builds and runs here, today.
The PHP probe bug hid for months because nothing re-checked that the thing being
asked was the thing being built; this is the same check one level down. For each
held-out set the untouched target file is built and run, and any failure is
reported per language with the diagnostic attached.

    python scripts/lane_audit.py [--json data/autoloop/lane_audit.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainapp import autoloop, config, functionprobe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default="")
    parser.add_argument("--timeout", type=float, default=25)
    args = parser.parse_args(argv)

    state = autoloop.read_state()
    pools = autoloop._pools(state)
    tasks = {t["id"]: t for t in functionprobe.pool_candidates()}
    out: dict = {"at": autoloop.now(), "pools": {}, "failures": []}
    for pool, ids in pools.items():
        per_language: dict[str, dict] = defaultdict(
            lambda: {"sets": 0, "ok": 0, "failed": 0})
        for tid in ids:
            task = tasks.get(tid)
            if task is None:
                per_language["(missing)"]["failed"] += 1
                out["failures"].append({"pool": pool, "task_id": tid,
                                        "language": "", "error": "not resolvable"})
                continue
            target = functionprobe.target_of(task)
            language = task.get("language", "")
            slot = per_language[language]
            slot["sets"] += 1
            if target is None:
                slot["failed"] += 1
                out["failures"].append({"pool": pool, "task_id": tid,
                                        "language": language,
                                        "error": "no target file"})
                continue
            result = functionprobe.run_set(task, target["content"], args.timeout)
            if result.ok:
                slot["ok"] += 1
            else:
                slot["failed"] += 1
                out["failures"].append({
                    "pool": pool, "task_id": tid, "language": language,
                    "error": functionprobe.diagnostic(result)})
        out["pools"][pool] = dict(per_language)

    path = Path(args.json or (config.data_dir() / "autoloop" / "lane_audit.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    for pool, per_language in out["pools"].items():
        print(f"{pool}:")
        for language, slot in sorted(per_language.items(),
                                     key=lambda kv: -kv[1]["failed"]):
            print(f"  {language:11s} {slot['ok']:3d}/{slot['sets']:3d} build")
    print(f"failures: {len(out['failures'])}  wrote {path}")
    return 0 if not out["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
