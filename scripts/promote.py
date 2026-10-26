"""promote — make an adapter the champion by hand, measured on the whole pool.

The loop only replaces its champion through `judge`, which needs a paired gain
at p <= 0.2. An operator can decide a smaller but consistent gain is worth
building on, and that decision has to be recorded in the same state the loop
reads — with the adapter measured on the *widened* pool, so the next verdict
pairs against a baseline from the same sets rather than the 53 of 76 that the
lane cut left behind.

    python scripts/promote.py --adapter data/models/auto10/adapter \
        --reason "family 18/53 -> 21/53 paired +4/-1 (p=0.375), gate 8 -> 9"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainapp import autoloop, functionprobe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--reason", default="promoted by operator")
    args = parser.parse_args(argv)

    adapter = str(Path(args.adapter).resolve())
    if not Path(adapter).is_dir():
        print(f"promote: no adapter at {adapter}", file=sys.stderr)
        return 2

    state = autoloop.read_state()
    pools = autoloop._pools(state)
    tasks = {t["id"]: t for t in functionprobe.pool_candidates()}
    missing = {key: [i for i in ids if i not in tasks]
               for key, ids in pools.items()}
    backend = autoloop.RealBackend({key: [tasks[i] for i in ids if i in tasks]
                                    for key, ids in pools.items()})
    log = lambda line: print(line, flush=True)  # noqa: E731
    print(f"promote: {adapter}\n  pool family {len(backend.pools['family'])}/"
          f"{len(pools['family'])} task {len(backend.pools['task'])}/"
          f"{len(pools['task'])} unresolved {missing}", flush=True)

    previous = {"best": state.get("best"), "metrics": state.get("best_metrics")}
    scored = backend.evaluate(adapter, log)
    scored["gate"] = backend.gate(adapter, log)
    scored["adapter"] = adapter

    state["best"] = adapter
    state["best_metrics"] = {k: scored[k] for k in
                             ("family", "task", "gate", "rows") if k in scored}
    # The measurement just taken is the current rule's; without this the next
    # `run` would re-measure the champion all over again.
    state["eval_version"] = autoloop.EVAL_VERSION
    autoloop.journal({
        "at": autoloop.now(), "cycle": state.get("cycle"),
        "promoted": {"from": previous["best"], "to": adapter,
                     "reason": args.reason,
                     "was": {"family": (previous["metrics"] or {}).get("family"),
                             "gate": (previous["metrics"] or {}).get("gate")},
                     "now": {"family": scored["family"], "task": scored["task"],
                             "gate": {k: scored["gate"][k] for k in
                                      ("passed", "total", "failures")}},
                     "pool": {k: len(v) for k, v in backend.pools.items()},
                     "unresolved": missing}})
    autoloop.save_state(state)
    autoloop.write_report(state, autoloop.history())
    print(json.dumps({"best": adapter, "family": scored["family"],
                      "task": scored["task"],
                      "gate": {k: scored["gate"][k] for k in
                               ("passed", "total", "failures")}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
