"""Score base, night5 and night5-orpo on the same 24 held-out sets.

The held-out list is read from night4's evaluation rather than recomputed, so
the three arms face exactly the tasks night4 faced: a recomputed list grows
whenever the night makes another set "known" and the comparison stops being
paired.
"""
import json
from pathlib import Path

from trainapp import config, functioneval, functionprobe
from trainapp.localcoder import LocalCoder

ids = json.loads(Path("data/functioneval/night4/eval.json").read_text())["held_out"]
tasks = {t["id"]: t for t in functionprobe.candidates()}
pool = [tasks[i] for i in ids if i in tasks]
missing = [i for i in ids if i not in tasks]
print(f"{len(pool)} held-out set(s) of {len(ids)} (missing {len(missing)})", flush=True)

model = config.load()["training"]["model"]
arms = [("base", ""), ("night5", "data/models/night5/adapter"),
        ("night5nm", "data/models/night5nm/adapter")]
result = {"generated_at": functioneval._now(), "held_out": [t["id"] for t in pool],
          "arms": {}, "rows": {}}
for name, adapter in arms:
    coder = LocalCoder(model, adapter=adapter) if adapter else LocalCoder(model)
    try:
        scored = functioneval.score(coder, pool, 25)
    finally:
        coder.close()
    result["arms"][name] = scored["stats"]
    result["rows"][name] = scored["rows"]
    print(name, json.dumps(scored["stats"]), flush=True)

out = Path("data/functioneval/night5")
out.mkdir(parents=True, exist_ok=True)
(out / "eval.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
for name, rows in result["rows"].items():
    (out / f"{name}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

print("\npaired changes against base:", flush=True)
base_rows = result["rows"]["base"]
for name in ("night5", "night5nm"):
    other = {r["task_id"]: r for r in result["rows"][name]}
    for field in ("compile", "match"):
        gained = [b["task_id"] for b in base_rows
                  if not b.get(field) and other[b["task_id"]].get(field)]
        lost = [b["task_id"] for b in base_rows
                if b.get(field) and not other[b["task_id"]].get(field)]
        print(f"  {name:11s} {field:8s} gained {len(gained)}, lost {len(lost)}",
              flush=True)
        print(f"    lost: {[t.split('/')[-1][-42:] for t in lost]}", flush=True)
