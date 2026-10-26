"""mix_ab — one cycle on whole programs only, judged by the same pools and gate.

The SFT sheet is 41% plan and repair/invent rows by count, and every round since
the lane cut has trained on all of it while being scored on whole held-out
programs. This leaves those two sheets out and changes nothing else — same
champion start, same levers, same held-out pools from the loop's state, same
battery — so the mix is the only variable.

    python scripts/mix_ab.py [--out data/autoloop/mix_ab.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainapp import autoloop, config, functionprobe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    parser.add_argument("--cycle", type=int, default=91,
                        help="model directory to write (data/models/autoN)")
    args = parser.parse_args(argv)

    state = autoloop.read_state()
    pools = autoloop._pools(state)
    tasks = {t["id"]: t for t in functionprobe.candidates()}
    backend = autoloop.RealBackend(
        {key: [tasks[i] for i in ids if i in tasks] for key, ids in pools.items()},
        mix="programs")
    levers = autoloop.Levers()
    log = lambda line: print(line, flush=True)  # noqa: E731

    init = state.get("best") or ""
    print(f"mix_ab: champion={init or '(base)'} mix=programs levers={levers}",
          flush=True)
    sft = backend.train(args.cycle, levers, init, log)
    candidate = backend.orpo(args.cycle, levers, sft, log)
    scored = backend.evaluate(candidate, log)
    scored["gate"] = backend.gate(candidate, log)
    scored["adapter"] = candidate

    best = state.get("best_metrics") or {}
    accepted, reason = autoloop.judge(best, scored)
    out = {"at": autoloop.now(), "mix": "programs", "init": init,
           "levers": autoloop.asdict(levers), "candidate": scored,
           "champion": {"family": (best.get("family") or {}),
                        "task": (best.get("task") or {}),
                        "gate": (best.get("gate") or {})},
           "judged": {"accepted": accepted, "reason": reason}}
    path = Path(args.out or (config.data_dir() / "autoloop" / "mix_ab.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"family": scored["family"], "task": scored["task"],
                      "gate": {k: scored["gate"][k] for k in
                               ("passed", "total", "failures", "rechecked")},
                      "judged": out["judged"]}, indent=2), flush=True)
    print(f"mix_ab: wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
