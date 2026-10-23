#!/usr/bin/env bash
# Move the training box onto the five-lane corpus, but only once the running
# cycle has produced its verdict: rebuilding the library mid-cycle would change
# the pool under a measurement that already has a baseline.
set -euo pipefail
cd "$HOME/vaca-train-app/vaca-train-app"
exec >>data/autoloop/deploy.log 2>&1
echo "== deploy watcher $(date -u +%FT%TZ) =="

verdict() {
  python3 - <<'PY'
import json
import sys
rows = [json.loads(line) for line in open("data/autoloop/journal.jsonl") if line.strip()]
sys.exit(0 if any(row.get("cycle") == 4 and "accepted" in row for row in rows) else 1)
PY
}

for _ in $(seq 1 180); do
  if verdict; then break; fi
  sleep 60
done
if ! verdict; then
  echo "no cycle-4 verdict after three hours; not deploying"
  exit 1
fi

echo "cycle 4 has a verdict; stopping the loop"
systemctl --user stop vaca-autoloop.service || true

echo "rebuilding the library on the five lanes"
python3 -m trainapp.clisets --build

echo "validating every cli set without a verified record"
python3 - <<'PY'
from trainapp import functionprobe, functioneval, library, validate

validation = library.load_validation()
todo = [task for task in library.load_tasks(all_languages=True)
        if task.get("origin") == "cli-set"
        and (validation.get(task["id"]) or {}).get("status") != "verified"]
print("validating", len(todo), "cli sets")
summary = validate.run(todo, jobs=4, timeout_s=30)
print("verified", summary.get("verified"), "failed", summary.get("failed"))

pool = functionprobe.candidates()
families: dict[str, int] = {}
for task in pool:
    key = functioneval.family_of(task)
    families[key] = families.get(key, 0) + 1
scored = {key: count for key, count in families.items() if count >= 2}
print("pool", len(pool), "families", len(scored), "scored sets", sum(scored.values()))
PY

echo "starting the loop on the five-lane corpus"
systemctl --user start vaca-autoloop.service
echo "== deploy done $(date -u +%FT%TZ) =="
