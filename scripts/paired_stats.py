"""Paired comparison of arms on one evaluation directory.

    python3 scripts/paired_stats.py data/functioneval/family base night5 night5nm
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/functioneval/night5")


def load(name: str) -> dict[str, dict]:
    return {r["task_id"]: r for r in
            map(json.loads, (ROOT / f"{name}.jsonl").read_text().splitlines())}


names = sys.argv[2:] or ["base", "night5", "night5nm1", "night5nm",
                         "night5ctl", "night5ctl40"]
arms = {name: load(name) for name in names}
ids = list(arms[names[0]])


def mcnemar(left: str, right: str, field: str) -> str:
    gained = sum(1 for t in ids if not arms[left][t].get(field) and arms[right][t].get(field))
    lost = sum(1 for t in ids if arms[left][t].get(field) and not arms[right][t].get(field))
    n = gained + lost
    p = 1.0
    if n:
        p = min(1.0, 2 * sum(math.comb(n, k) * 0.5 ** n
                             for k in range(min(gained, lost) + 1)))
    return f"+{gained}/-{lost} p={p:.2f}"


for name in names[1:]:
    print(f"{names[0]:11s} -> {name:11s} "
          f"compile {mcnemar(names[0], name, 'compile'):22s} "
          f"behaviour {mcnemar(names[0], name, 'match')}")
print()
if len(names) > 2:
    for left in names[1:]:
        for right in names[1:]:
            if names.index(left) < names.index(right):
                print(f"{left:11s} -> {right:11s} "
                      f"behaviour {mcnemar(left, right, 'match')}")
