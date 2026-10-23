"""Score arms on the family-held-out pool: whole programs the split keeps out.

Usage: python3 scripts/eval_family.py base night5 night5nm night5ctl40

`base` maps to the untouched model; every other name is
`data/models/<name>/adapter`. Arms are scored one at a time so only one model
is resident.
"""
import json
import sys
from pathlib import Path

from trainapp import config, functioneval, functionprobe
from trainapp.localcoder import LocalCoder

OUT = Path("data/functioneval/family")


def adapter_for(name: str) -> str:
    return "" if name == "base" else f"data/models/{name}/adapter"


pool = functioneval.held_out_tasks(by_family=True)
families = {}
for task in pool:
    families.setdefault(functioneval.family_of(task), []).append(task["id"])
print(f"{len(pool)} set(s) from {len(families)} held-out families", flush=True)
print("families:", sorted(families)[:12], flush=True)

model = config.load()["training"]["model"]
result = {"held_out": [t["id"] for t in pool], "families": families,
          "generated_at": functioneval._now(), "arms": {}, "rows": {}}
for name in sys.argv[1:]:
    coder = LocalCoder(model, adapter=adapter_for(name))
    try:
        scored = functioneval.score(coder, pool, 25)
    finally:
        coder.close()
    result["arms"][name] = scored["stats"]
    result["rows"][name] = scored["rows"]
    print(name, json.dumps(scored["stats"]), flush=True)

    # Per-family behaviour, because the question is exactly which programs move.
    rows = {r["task_id"]: r for r in scored["rows"]}
    for family, ids in sorted(families.items()):
        hit = sum(1 for i in ids if rows[i].get("match"))
        print(f"   {hit}/{len(ids)}  {family[:66]}", flush=True)

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "eval.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
for name, rows in result["rows"].items():
    (OUT / f"{name}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
print("written to", OUT, flush=True)
