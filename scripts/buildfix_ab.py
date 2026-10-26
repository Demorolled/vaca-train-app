"""buildfix_ab — one cycle with the night's build failures turned into rows.

The held-out families that never build cannot be trained on; the shapes they fail
on can. This adds `trainapp.buildfix` to the recipe — the compiler's complaint
and the library's working function for the same ask, plus a preference pair with
that function chosen over the broken reply — and changes nothing else: same
champion start, same levers, same held-out pools, same battery.

    python scripts/buildfix_ab.py [--out data/autoloop/buildfix_ab.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainapp import autoloop, buildfix, config, functionprobe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    parser.add_argument("--cycle", type=int, default=92,
                        help="model directory to write (data/models/autoN)")
    args = parser.parse_args(argv)

    stats = buildfix.stats()
    print(f"buildfix_ab: {stats['rows']} repair rows, {stats['pairs']} pairs "
          f"from {stats['attempts']} recorded attempts {stats['by_reason']}",
          flush=True)

    state = autoloop.read_state()
    pools = autoloop._pools(state)
    tasks = {t["id"]: t for t in functionprobe.pool_candidates()}
    backend = autoloop.RealBackend(
        {key: [tasks[i] for i in ids if i in tasks] for key, ids in pools.items()},
        with_buildfix=True)
    levers = autoloop.Levers()
    log = lambda line: print(line, flush=True)  # noqa: E731

    init = state.get("best") or ""
    print(f"buildfix_ab: champion={init or '(base)'} levers={levers}", flush=True)
    sft = backend.train(args.cycle, levers, init, log)
    candidate = backend.orpo(args.cycle, levers, sft, log)
    scored = backend.evaluate(candidate, log)
    scored["gate"] = backend.gate(candidate, log)
    scored["adapter"] = candidate

    best = state.get("best_metrics") or {}
    accepted, reason = autoloop.judge(best, scored)
    out = {"at": autoloop.now(), "with_buildfix": True, "init": init,
           "buildfix": stats, "levers": autoloop.asdict(levers),
           "candidate": scored,
           "champion": {"family": (best.get("family") or {}),
                        "task": (best.get("task") or {}),
                        "gate": (best.get("gate") or {})},
           "judged": {"accepted": accepted, "reason": reason}}
    path = Path(args.out or (config.data_dir() / "autoloop" / "buildfix_ab.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"family": scored["family"], "task": scored["task"],
                      "gate": {k: scored["gate"][k] for k in
                               ("passed", "total", "failures")},
                      "judged": out["judged"]}, indent=2), flush=True)
    print(f"buildfix_ab: wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
