"""How much of the near-miss gain is the fibonacci family, and how big is the
non-fibonacci pool a family split would have to work with?"""
import collections
import json
import re
from pathlib import Path

from trainapp import functionprobe, overnight

ROOT = Path("data/functioneval/night5")


def read(name: str) -> list[dict]:
    return [json.loads(line) for line in
            (ROOT / f"{name}.jsonl").read_text().splitlines()]


def family(task_id: str) -> str:
    if "fibonacci" in task_id:
        return "fibonacci"
    slug = re.sub(r"^(a|an|the)-", "", task_id.split("/")[-1])
    return slug.split("-cli-set-")[0].split("-program-")[0][:34]


ARMS = ("base", "night5", "night5nm", "night5ctl40")
rows = {name: read(name) for name in ARMS}
print("arm           fib    non-fib   families matched")
for name in ARMS:
    fib = [r for r in rows[name] if family(r["task_id"]) == "fibonacci"]
    other = [r for r in rows[name] if family(r["task_id"]) != "fibonacci"]
    match_fib = sum(1 for r in fib if r["match"])
    match_other = sum(1 for r in other if r["match"])
    fams = {family(r["task_id"]) for r in other if r["match"]}
    print(f"{name:12s} {match_fib}/{len(fib):<5} {match_other}/{len(other):<5} "
          f"{len(fams)}")

print("\nnon-fibonacci tasks, by arm:")
names = sorted({family(r["task_id"]) for r in rows["base"]
                if family(r["task_id"]) != "fibonacci"})
lookup = {name: {r["task_id"]: r for r in rows[name]} for name in ARMS}
for task in sorted(rows["base"], key=lambda r: family(r["task_id"])):
    if family(task["task_id"]) == "fibonacci":
        continue
    marks = "".join("1" if lookup[a][task["task_id"]]["match"] else "."
                    for a in ARMS)
    print(f"  {marks}  {task['language']:11s} {family(task['task_id'])}")

night = overnight.load_export()
known = {r["task_id"] for r in night["sft"] if r.get("verified") == "behaviour"}
pool = [t for t in functionprobe.candidates() if t["id"] in known]
families = collections.Counter(family(t["id"]) for t in pool)
print(f"\njudgeable pool: {len(pool)} sets, {len(families)} families; "
      f"fibonacci {families.get('fibonacci', 0)}")
print("largest:", families.most_common(6))
print("singletons:", sum(1 for n in families.values() if n == 1))
