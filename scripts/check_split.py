"""Report the five sibling families and the held-out pool they produce."""
import collections

from trainapp import functioneval, functionprobe

WANT = {"binary search trace", "lru cache simulation", "isbn checksum",
        "vending change", "game of life step"}
pool = functionprobe.candidates()
fam = functioneval.family_of
rows = collections.defaultdict(list)
for task in pool:
    if fam(task) in WANT:
        rows[fam(task)].append(task.get("language"))
for name in sorted(rows):
    print(f"{name}: {len(rows[name])} judgeable sets ->", sorted(rows[name]))
print()
sizes = collections.Counter(fam(t) for t in pool)
held = functioneval.holdout_families(pool)
chosen = functioneval.held_out_tasks(pool, by_family=True)
per = collections.Counter(fam(t) for t in chosen)
print("judgeable sets", len(pool), "families", len(sizes))
print("held families", len(held), "scored sets", len(chosen))
print("sets per held family", sorted(per.values()))
print("families with >=2 sets", sum(1 for n in sizes.values() if n >= 2))
