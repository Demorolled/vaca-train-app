"""Score one adapter on the fixed night4 held-out list and diff it against
the rows already stored for base / night5 / night5nm in data/functioneval/night5.
"""
import json
import sys
from pathlib import Path

from trainapp import config, functioneval, functionprobe
from trainapp.localcoder import LocalCoder

name = sys.argv[1]
adapter = sys.argv[2]
stored = Path("data/functioneval/night5")
ids = json.loads((stored / "eval.json").read_text())["held_out"]
tasks = {t["id"]: t for t in functionprobe.candidates()}
pool = [tasks[i] for i in ids if i in tasks]

model = config.load()["training"]["model"]
coder = LocalCoder(model, adapter=adapter)
try:
    scored = functioneval.score(coder, pool, 25)
finally:
    coder.close()
rows = scored["rows"]
(stored / f"{name}.jsonl").write_text(
    "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
print(name, json.dumps(scored["stats"]), flush=True)

for other in ("base", "night5"):
    path = stored / f"{other}.jsonl"
    if not path.exists():
        continue
    before = {r["task_id"]: r for r in map(json.loads, path.read_text().splitlines())}
    for field in ("compile", "match"):
        gained = [t for t, b in before.items() if not b.get(field) and
                  next(r for r in rows if r["task_id"] == t).get(field)]
        lost = [t for t, b in before.items() if b.get(field) and
                not next(r for r in rows if r["task_id"] == t).get(field)]
        print(f"  vs {other:7s} {field:8s} gained {len(gained)}, lost {len(lost)}: "
              f"{[t.split('/')[-1][-34:] for t in lost]}", flush=True)
