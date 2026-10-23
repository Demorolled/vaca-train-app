"""Reset the champion to the untouched model, with the corrected probe grading.

Run on the box: PYTHONPATH=. python scripts/revoke_champion.py
"""
import json

from trainapp import autoloop, probes


def regrade(entry: dict) -> dict:
    """Re-apply the current probe checks to the answers already on disk."""
    passed_ids, failures = [], []
    for row in entry["rows"]:
        if not row.get("scored"):
            continue
        votes = [probes.check(row["id"], a["response"])["ok"] for a in row["attempts"]]
        (passed_ids if sum(votes) * 2 > len(votes) else failures).append(row["id"])
    return {"passed": len(passed_ids), "total": len(passed_ids) + len(failures),
            "passed_ids": passed_ids,
            "lanes": probes.lane_stats({"passed_ids": passed_ids}),
            "failures": failures}


state = autoloop.read_state()
print("before:", state.get("best"), state["best_metrics"]["family"],
      state["best_metrics"]["gate"]["passed"])

journal = [json.loads(line) for line in open("data/autoloop/journal.jsonl")]
base = [entry["baseline"] for entry in journal if "baseline" in entry][-1]

entries = [json.loads(line) for line in open("data/probes/probes.jsonl")]
base_gate = [e for e in entries if "+" not in e["arm"]][-1]
base["gate"] = regrade(base_gate)
base["rows"] = {"family": [{"task_id": row["task_id"], "match": bool(row.get("match")),
                            "compile": bool(row.get("compile"))}
                           for row in map(json.loads, open("data/functioneval/family/base.jsonl"))
                           if "match" in row]}

state["best"] = ""
state["best_metrics"] = base
autoloop.save_state(state)
autoloop.journal({"at": autoloop.now(), "revoked": "auto1",
                  "reason": "family +3 did not survive pairing (+6/-3, p=0.51); "
                            "champion reset to the untouched model"})
print("after:", repr(state["best"]), base["family"], base["gate"]["passed"],
      "rows", len(base["rows"]["family"]))
