"""autoloop — unattended improvement cycles that judge their own progress.

One cycle is: probe the judgeable pool (a night), mine balanced near-miss pairs,
retrain SFT, run one ORPO pass over the night's verified pairs, then score the
candidate on two held-out pools and the boundary battery. `judge` decides
whether that candidate replaces the champion; `escalate` picks the next lever
when it does not.

The measurements that decide are the ones this repository learned to trust:

* **family-held-out behaviour** is primary. A task-level split leaves the
  siblings of a held-out set in training, and a near-miss pair teaches the
  family it was mined from; only whole-program hold-outs tell improvement from
  memorisation.
* **the boundary battery** is a guardrail. A round that gains behaviour while
  losing the no-fence lane is not a win — that lesson is why `probes` gates
  training at all.
* **task-held-out behaviour and compile** are tie-breakers, not evidence.

Every number lands in `data/autoloop/journal.jsonl`, the live stage in
`data/autoloop.status.json`, and a human table in `data/autoloop/report.md`.
`data/autoloop.stop` ends the run between two stages; a restart resumes the
cycle it was in.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path

from . import config, functioneval, functionprobe, nearmiss, overnight, probes, trainloop

STATE_FILE = "autoloop.state.json"
STATUS_FILE = "autoloop.status.json"
STOP_FILE = "autoloop.stop"
JOURNAL_FILE = "journal.jsonl"
REPORT_FILE = "report.md"
LOG_FILE = "autoloop.log"

# A candidate must move the primary metric by at least one task and may not
# lose more than one boundary probe: behaviour bought with the format lane is
# the failure this repository has already paid for once. A lost probe is a probe
# lost on the pooled majority of its draws, so the tolerance is spent on a lane
# that really moved, not on one answer that happened to land badly.
MIN_FAMILY_GAIN = 1
MAX_GATE_LOSS = 1
BREADTH_GAIN = 2
# A gain has to survive pairing: at 52 held-out sets, +6/-3 is p=0.51, and a
# language swap inside one family is enough to produce it.
PAIRED_ALPHA = 0.2
MIN_PAIRED_TASKS = 20
# Every held-out set is scored twice. One greedy decode per set is a single bit
# of evidence, and a verdict that turns on four of them (cycle 10: +5/-1, p=0.22)
# cannot tell a real gain from a lucky token. The draws are taken at the app's
# own sampling, so a set that passes once and fails once is recorded as such
# instead of being reduced to whichever decode came first.
EVAL_DRAWS = 2
EVAL_TEMPERATURE = 0.7
EVAL_TOP_P = 0.9
# Bump when the scoring rule changes: rows from one draw are not comparable with
# rows from two, so the champion is measured again under the new rule before it
# judges anyone.
EVAL_VERSION = 2
# Probes a candidate must fix, not merely hold, for a contract repair to count
# as a reason to keep it when the family metric cannot tell.
CONTRACT_GAIN = 2
# Bump when the held-out split changes: a frozen pool from the old rule would
# keep scoring sets the new rule says cannot be measured.
POOLS_VERSION = 3
# Each probe is generated three times and graded by strict majority, and a probe
# whose runs disagree is asked three more times before it counts either way: a
# guard that refuses a candidate on one unlucky sentence is a guard that rejects
# noise. The draws are taken at the app's own sampling (Modelfile: 0.7/0.9) —
# three greedy decodes are one answer printed three times, not three samples.
GATE_SAMPLES = 3
GATE_CONFIRM = 3
GATE_TEMPERATURE = 0.7
GATE_TOP_P = 0.9
# Bump when the way the gate is measured changes. A champion's stored total was
# measured by the old rule, so it is re-measured under the new one before it is
# used as the bar for anybody else.
GATE_VERSION = 2
# Half of train_lora's default 2e-4. A cycle that ends with fences back and the
# scaffold lane gone has spent too much update on too narrow a sheet.
TRAIN_LR = 1e-4


@dataclass
class Levers:
    """What one cycle is allowed to spend and how."""

    samples: int = 3
    max_functions: int = 3
    per_family: int = 5
    # 60 steps at half the old learning rate: a round that memorises its own
    # pairs while losing the fence lane is updating too hard, not learning too
    # little. See `TRAIN_LR`.
    sft_steps: int = 60
    # 40, not 12: on the 168-task held-out pool a 12-step pass cost 19 compile
    # tasks for 5 gained (p=0.007), while 40 steps cost 11 for 8 (p=0.65) and
    # kept the same behaviour gain. See `data/battery/wide/report.json`.
    orpo_steps: int = 40
    # The contract rehearsal that follows ORPO (see `trainloop.rehearsal_sheet`).
    # 0 turns it off, which is how the mixture A/B measures what it is worth.
    rehearsal_steps: int = 15
    night_hours: float = 1.0
    # Every candidate used to start from the base model, so no round could build
    # on the champion and the curve could only repeat itself. Compounding is the
    # default now; the gate still refuses a round that gives the contract back.
    continue_from_best: bool = True


# Ordered cheapest-first: each rung costs GPU time or wall-clock, so a plateau
# climbs the ladder instead of repeating a cycle that already failed.
#
# No rung spends more on near-miss pairs. A pair teaches the family it was mined
# from, and the primary metric holds whole families out: more pairs per family
# is the one lever the leak-free experiment showed cannot move that number. The
# training mix is fixed instead — a few demonstrations per program per language,
# see `librarysft.rows` — and the rungs buy measurement instead.
#
# Compounding (`continue_from_best`) was the last rung; it is the base now, so the
# rungs left are the ones that buy a longer look, not a different starting point.
LADDER = (
    ("samples", 4, "more samples per function: fills the hour the queue leaves"),
    ("night_hours", 1.6, "a longer night"),
    ("max_functions", 4, "every function in the target, not the largest three"),
    ("sft_steps", 120, "a longer SFT pass"),
)
BASE = Levers()


def _stored_levers(state: dict) -> Levers:
    """The levers the run had climbed to, so a restart does not drop a rung.

    A restart resumes the cycle number; resuming it on the base levers instead
    would silently undo an escalation and leave `tried` claiming a rung that
    never ran.
    """
    known = {field.name for field in fields(Levers)}
    kept = {key: value for key, value in (state.get("levers") or {}).items()
            if key in known}
    return Levers(**kept) if kept else Levers()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def loop_dir() -> Path:
    path = config.data_dir() / "autoloop"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path() -> Path:
    return loop_dir() / STATE_FILE


def status_path() -> Path:
    return config.data_dir() / STATUS_FILE


def stop_path() -> Path:
    return config.data_dir() / STOP_FILE


def read_state() -> dict:
    path = state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> dict:
    state["updated_at"] = now()
    state_path().write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def publish(**fields) -> dict:
    path = status_path()
    current: dict = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
    current.update(fields)
    current["updated_at"] = now()
    path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return current


def stop_requested() -> bool:
    return stop_path().exists()


def request_stop() -> Path:
    path = stop_path()
    path.write_text(now() + "\n", encoding="utf-8")
    return path


def journal(entry: dict) -> None:
    with (loop_dir() / JOURNAL_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def history() -> list[dict]:
    path = loop_dir() / JOURNAL_FILE
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def mcnemar(gained: int, lost: int) -> float:
    """Two-sided exact McNemar p for a paired gain/loss count."""
    n = gained + lost
    if not n:
        return 1.0
    low = min(gained, lost)
    return min(1.0, 2 * sum(math.comb(n, k) * 0.5 ** n for k in range(low + 1)))


def row_score(row: dict) -> tuple[int, int]:
    """(matches, draws) for one scored set; an old row is one draw of one bit."""
    if row.get("draws"):
        return int(row.get("matches") or 0), int(row["draws"])
    return int(bool(row.get("match"))), 1


def paired_gain(before: dict, after: dict, pool: str = "family") -> dict | None:
    """The same held-out sets scored twice: gained, lost, and the exact p.

    A count difference between two runs on 52 sets is not evidence: the same
    program in another language can carry the net on its own. The first champion
    was accepted on 15 -> 18, which turned out to be +6/-3 (p=0.51), with two
    families moving in both directions. Pairing the tasks is what tells those
    apart, so the verdict reads this whenever both arms recorded their rows.

    With two draws per set the comparison is on totals: a set counts as gained
    when the candidate matched it more often than the champion did, and lost when
    it matched it less. Sets scored under different rules are not paired at all.
    """
    left = {r["task_id"]: row_score(r)
            for r in (before.get("rows") or {}).get(pool) or []}
    right = {r["task_id"]: row_score(r)
             for r in (after.get("rows") or {}).get(pool) or []}
    ids = [tid for tid in left if tid in right and left[tid][1] == right[tid][1]]
    if len(ids) < MIN_PAIRED_TASKS:
        return None
    gained = sum(1 for tid in ids if right[tid][0] > left[tid][0])
    lost = sum(1 for tid in ids if left[tid][0] > right[tid][0])
    return {"n": len(ids), "gained": gained, "lost": lost,
            "net": gained - lost, "p": round(mcnemar(gained, lost), 3)}


def lost_lanes(before: dict, after: dict) -> str:
    """The probes a candidate lost, named by lane: `write-go (write), …`.

    The total says a probe was lost; the lane says whether it was the no-fence
    contract or a prose answer drifting, and those call for opposite responses.
    """
    passed = set(after.get("passed_ids") or [])
    lost = [pid for pid in (before.get("passed_ids") or []) if pid not in passed]
    return ", ".join(f"{pid} ({probes.LANES.get(pid, '?')})" for pid in lost)


def judge(best: dict, candidate: dict) -> tuple[bool, str]:
    """Replace the champion only on a real, guarded gain.

    Family-held-out behaviour first; the gate may lose at most one probe. A tie
    on behaviour can still be accepted as a breadth gain (two more task-level
    tasks), because compile breadth is what lets a later cycle be measured.
    """
    before = best["family"]["match"]
    after = candidate["family"]["match"]
    gate_before = best["gate"]["passed"]
    gate_after = candidate["gate"]["passed"]
    guarded = gate_after >= gate_before - MAX_GATE_LOSS
    paired = paired_gain(best, candidate)
    move = (f"family behaviour {before} -> {after} "
            f"(+{after - before})")
    if paired:
        move += (f" paired +{paired['gained']}/-{paired['lost']} "
                 f"(p={paired['p']}, n={paired['n']})")
    else:
        move += " (unpaired)"
    paired_ok = not paired or paired["p"] <= PAIRED_ALPHA
    if after - before >= MIN_FAMILY_GAIN and guarded and paired_ok:
        return True, f"{move}, gate {gate_before} -> {gate_after}"
    # A contract repair is not a capability claim, but it is a win the app needs:
    # the champion fixed the no-fence and plan lanes (4 -> 8 probes) while the
    # family metric moved inside its own noise. Keeping that trade needs the
    # breadth to be real, so it is paired, and it may not be bought with a
    # family regression.
    if guarded and gate_after - gate_before >= CONTRACT_GAIN:
        # The gate is graded per probe with three samples; it does not need a
        # behaviour pairing to be believed, and requiring one refused two
        # candidates that fixed the fence lane outright (4 -> 8, +8/-3, p=0.23).
        # What it may not do is regress behaviour: both pools must be non-negative.
        task_net = candidate["task"]["match"] - best["task"]["match"]
        family_net = paired["net"] if paired else after - before
        if family_net >= 0 and task_net >= 0:
            return True, (f"contract repaired {gate_before} -> {gate_after} "
                          f"(family {before} -> {after}, task {best['task']['match']}"
                          f" -> {candidate['task']['match']}); no regressions")

    if after == before and guarded and (
            candidate["task"]["match"] - best["task"]["match"] >= BREADTH_GAIN):
        task_paired = paired_gain(best, candidate, pool="task")
        if task_paired and task_paired["p"] > PAIRED_ALPHA:
            return False, (f"family behaviour level at {after}; task-level "
                           f"+{candidate['task']['match'] - best['task']['match']} "
                           f"is inside pairing noise (p={task_paired['p']})")
        return True, (f"family behaviour level at {after}, task-level "
                      f"{best['task']['match']} -> {candidate['task']['match']}")
    if not guarded:
        lost = lost_lanes(best["gate"], candidate["gate"])
        return False, (f"gate fell {gate_before} -> {gate_after} "
                       f"(more than {MAX_GATE_LOSS} probe(s): {lost or 'no ids recorded'})")
    if after - before >= MIN_FAMILY_GAIN and not paired_ok:
        return False, (f"{move}: gate {gate_before} -> {gate_after}, but the "
                       f"gain does not survive pairing (p > {PAIRED_ALPHA})")
    return False, (f"family behaviour {before} -> {after} is not a gain "
                   f"(needs +{MIN_FAMILY_GAIN})")


def escalate(levers: Levers, tried: list[str]) -> tuple[Levers, str, str]:
    """The next untried rung, its description, and its key ("" when spent)."""
    for field, value, note in LADDER:
        key = f"{field}={value}"
        if key in tried:
            continue
        return replace(levers, **{field: value}), note, key
    return levers, "", ""


def merge_pairs(night_pairs: list[dict], mined: list[dict],
                held: set[str]) -> list[dict]:
    """Verified pairs from the night plus the mined near misses, no leakage."""
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row in list(night_pairs) + list(mined):
        if row.get("task_id") in held:
            continue
        if not (row.get("prompt") and (row.get("chosen") or "").strip()
                and (row.get("rejected") or "").strip()):
            continue
        key = (row["prompt"], row["chosen"], row["rejected"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def metrics(match: int, attempts: int, build_failed: int | None = None) -> dict:
    """A pool's score, split into "did not build" and "built but wrong".

    The two are different problems with different fixes: Go's failures are
    `undefined: sort` (a build), Python's are tracebacks (a wrong answer), and a
    single number let the loop chase recipe changes for both. `build_failed`
    counts sets that never compiled in any draw; the rest of the misses built
    and printed something else.
    """
    out = {"match": match, "attempts": attempts,
           "rate": round(match / attempts, 3) if attempts else 0.0}
    if build_failed is not None:
        out["build_failed"] = build_failed
        out["built"] = max(0, attempts - build_failed)
        out["wrong_output"] = max(0, attempts - build_failed - match)
    return out


def merge_draws(draws: list[list[dict]]) -> tuple[list[dict], dict]:
    """One row per set carrying how many draws matched, plus the pool's counts.

    A set that passed one draw and failed the other is the half-evidence that
    makes a one-probe difference look real, so it is kept as a count rather than
    collapsed into whichever decode finished last. `match` stays "at least one
    draw", which is what a capability claim means: the model can write it.
    """
    merged: dict[str, dict] = {}
    for rows in draws:
        for row in rows:
            tid = row.get("task_id")
            if not tid:
                continue
            entry = merged.setdefault(tid, {"task_id": tid, "matches": 0,
                                            "draws": 0, "compile": False})
            if not row.get("skipped"):
                entry["draws"] += 1
            entry["compile"] = entry["compile"] or bool(row.get("compile"))
            entry["matches"] += 1 if row.get("match") else 0
    rows = [{"task_id": entry["task_id"],
             "match": entry["matches"] > 0,
             "matches": entry["matches"],
             "draws": entry["draws"],
             "compile": entry["compile"]} for entry in merged.values()]
    attempts = sum(1 for row in rows if row["draws"])
    match = sum(1 for row in rows if row["match"])
    return rows, {"match": match, "attempts": attempts}


def _took(t0: float, marks: dict[str, float]) -> dict:
    """Seconds each stage of one cycle spent, and the cycle's own wall clock.

    A cycle's cost is not one number: the night, the mining pass, the two
    training runs and the scored gate were each bought separately, and the gate
    got dearer when its probes started being repeated. Recording the split in
    the journal is what lets a later run compare rounds by price as well as by
    score.
    """
    out: dict[str, int] = {}
    last = t0
    for name, at in marks.items():
        out[name] = round(at - last)
        last = at
    out["total"] = round(last - t0)
    return out


class Backend:
    """The four expensive actions, separated so a fake can replace them."""

    def night(self, levers: Levers, log) -> dict:
        raise NotImplementedError

    def mine(self, levers: Levers, log) -> dict:
        raise NotImplementedError

    def train(self, cycle: int, levers: Levers, init: str, log) -> str:
        raise NotImplementedError

    def orpo(self, cycle: int, levers: Levers, init: str, log) -> str:
        raise NotImplementedError

    def evaluate(self, adapter: str, log) -> dict:
        raise NotImplementedError

    def gate(self, adapter: str, log) -> dict:
        raise NotImplementedError


class RealBackend(Backend):
    """The actual pipeline: ollama, the trainer, and the two held-out pools."""

    def __init__(self, pools: dict | None = None,
                 all_languages: bool = False, mix: str = "all",
                 with_buildfix: bool = False) -> None:
        self.log_path = loop_dir() / LOG_FILE
        self.pools = pools or {}
        # Off by default: a cycle trains on the five lanes. The lane-cut
        # experiment turns it on to train on the corpus it had before the cut
        # while still being judged on the same held-out sets.
        self.all_languages = all_languages
        # `mix="programs"` trains on whole programs only (no plan or repair
        # rows); the mix A/B uses it and nothing else changes.
        self.mix = mix
        # `with_buildfix` adds repair rows mined from the night's build
        # failures; the build-fix A/B turns it on and nothing else changes.
        self.with_buildfix = with_buildfix

    # -- helpers ---------------------------------------------------------
    def _note(self, message: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{now()} {message}\n")
        publish(stage_note=message)

    def _ollama(self, stop: bool) -> None:
        """Free the VRAM the coder holds before torch, warm it before a night."""
        model = config.load().get("llm", {}).get("model", "")
        if not model:
            return
        try:
            if stop:
                subprocess.run(["ollama", "stop", model], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=90)
            else:
                subprocess.Popen(["ollama", "run", model, "ok"],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as err:
            self._note(f"ollama {err}")

    def _train(self, argv: list[str], log) -> int:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n$ {' '.join(argv)}\n")
        env = {**os.environ, "CUDA_VISIBLE_DEVICES": "0",
               "PYTHONPATH": str(config.APP_ROOT),
               "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}
        with self.log_path.open("a", encoding="utf-8") as handle:
            return subprocess.run(argv, cwd=str(config.APP_ROOT), env=env,
                                  stdout=handle, stderr=subprocess.STDOUT).returncode

    def _base_model(self) -> str:
        return config.load().get("training", {}).get(
            "model", "Qwen/Qwen2.5-Coder-1.5B-Instruct")

    def _pairs_file(self, held: set[str]) -> Path:
        """Night pairs plus mined near misses, no tournament rows.

        The generic tournament sheet costs the no-fence lane (7/10 -> 3/10 on
        the battery), so it stays out of a cycle that is judged on the gate.
        """
        night = overnight.load_export()
        rows = merge_pairs(night["pairs"], [], held)
        train, val = trainloop._split(rows, 0.1)
        if not val and train:
            val = [train.pop()]
        out = config.dataset_dir()
        for name, data in (("auto_pairs_train.jsonl", train),
                           ("auto_pairs_val.jsonl", val)):
            (out / name).write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in data),
                encoding="utf-8")
        return out / "auto_pairs_train.jsonl"

    # -- the four actions ------------------------------------------------
    def night(self, levers: Levers, log) -> dict:
        self._ollama(stop=False)
        # Cold sets first: an hour reaches a prefix of the pool, and the pool is
        # read from disk the same way every cycle, so without this the tail of
        # the library is never probed and no new family ever reaches a judgeable
        # row. See `overnight.cold_first`.
        pool = functionprobe.candidates()
        seen = overnight.coverage()
        queue = overnight.cold_first(pool)
        result = overnight.run(hours=levers.night_hours, rounds=1, tasks=queue,
                               samples=levers.samples, all_functions=True,
                               max_functions=levers.max_functions,
                               judgeable_only=True, do_export=True,
                               resume=False, client=None)
        return {"attempts": result.get("attempts", 0),
                "match": result.get("match", 0),
                "export": result.get("export") or {},
                "pool": len(pool),
                "cold": sum(1 for t in pool if t["id"] not in seen),
                "unpassed": sum(1 for t in pool
                                if t["id"] in seen and not seen[t["id"]]["match"])}

    def mine(self, levers: Levers, log) -> dict:
        mined = nearmiss.mine_night(per_family=levers.per_family,
                                    log=lambda line: self._note(line))
        counts = mined.get("counts") or {}
        return {"pairs": len(mined.get("rows") or []),
                "families": len(counts.get("families") or {})}

    def train(self, cycle: int, levers: Levers, init: str, log) -> str:
        self._ollama(stop=True)
        data = trainloop.prepare_data(by_family=True,
                                      all_languages=self.all_languages,
                                      mix=self.mix,
                                      with_buildfix=self.with_buildfix)
        self._note(f"data prepared: night_rows={data['night_rows']} "
                   f"night_pairs={data['night_pairs']} "
                   f"library_rows={data['library_rows']} plan_rows={data['plan_rows']} "
                   f"contract_rows={data['contract_rows']} "
                   f"buildfix_rows={data.get('buildfix_rows', 0)} "
                   f"buildfix_pairs={data.get('buildfix_pairs', 0)} "
                   f"holdout={data['holdout']}")
        out = config.data_dir() / "models" / f"auto{cycle}"
        argv = [sys.executable, "train_lora.py", "--mode", "sft",
                "--train", str(config.dataset_dir() / "train.jsonl"),
                "--val", str(config.dataset_dir() / "val.jsonl"),
                "--model", self._base_model(), "--out", str(out),
                "--max-steps", str(levers.sft_steps), "--lr", str(TRAIN_LR),
                "--seq-len", "1024"]
        if init:
            argv += ["--init-adapter", init]
        code = self._train(argv, log)
        if code != 0:
            raise RuntimeError(f"SFT exited {code}")
        return str(out / "adapter")

    def orpo(self, cycle: int, levers: Levers, init: str, log) -> str:
        held = functioneval.family_holdout_ids(functionprobe.candidates())
        pairs = self._pairs_file(held)
        out = config.data_dir() / "models" / f"auto{cycle}"
        argv = [sys.executable, "train_lora.py", "--mode", "orpo",
                "--pairs", str(pairs),
                "--val-pairs", str(config.dataset_dir() / "auto_pairs_val.jsonl"),
                "--model", self._base_model(), "--out", str(out),
                "--init-adapter", init, "--max-steps", str(levers.orpo_steps),
                "--lr", str(TRAIN_LR), "--seq-len", "1024"]
        code = self._train(argv, log)
        if code != 0:
            raise RuntimeError(f"ORPO exited {code}")
        if not levers.rehearsal_steps:
            return str(out / "adapter")
        # Finish on the contract, not on the preference: the pairs are what the
        # round is for, and the rehearsal is what keeps them from being bought
        # with the no-fence and plan lanes. See `trainloop.rehearsal_sheet`.
        sheet = trainloop.rehearsal_sheet(held, all_languages=self.all_languages)
        rehearsal = out / "rehearsal"
        argv = [sys.executable, "train_lora.py", "--mode", "sft",
                "--train", str(sheet), "--model", self._base_model(),
                "--out", str(rehearsal), "--init-adapter", str(out / "adapter"),
                "--max-steps", str(levers.rehearsal_steps),
                "--lr", str(TRAIN_LR), "--seq-len", "1024"]
        code = self._train(argv, log)
        if code != 0:
            raise RuntimeError(f"contract rehearsal exited {code}")
        self._note(f"contract rehearsal: {levers.rehearsal_steps} steps on {sheet.name}")
        return str(rehearsal / "adapter")

    def evaluate(self, adapter: str, log) -> dict:
        from .localcoder import LocalCoder

        self._ollama(stop=True)
        model = self._base_model()
        out: dict = {}
        for pool in ("family", "task"):
            tasks = self.pools.get(pool) or []
            draws: list[list[dict]] = []
            for draw in range(EVAL_DRAWS):
                # A fresh coder per draw: the same weights, the same prompt, a
                # second sample. Greedy here would be the same answer twice.
                coder = LocalCoder(model, adapter=adapter,
                                   temperature=EVAL_TEMPERATURE,
                                   top_p=EVAL_TOP_P) if adapter else LocalCoder(
                    model, temperature=EVAL_TEMPERATURE, top_p=EVAL_TOP_P)
                try:
                    draws.append(functioneval.score(coder, tasks, 25)["rows"])
                finally:
                    coder.close()
                self._note(f"{pool} draw {draw + 1}/{EVAL_DRAWS} scored")
            rows, stats = merge_draws(draws)
            build_failed = sum(1 for row in rows
                               if row["draws"] and not row["compile"])
            out[pool] = metrics(stats["match"], stats["attempts"], build_failed)
            # Kept so the next verdict can pair the same sets instead of
            # comparing two counts that a language swap can carry.
            out.setdefault("rows", {})[pool] = rows
        return out

    def gate(self, adapter: str, log) -> dict:
        # The battery loads the base model itself; a warm Ollama GGUF next to it
        # is two models in one card. Scoring already stops it, but the battery is
        # also called on its own to re-measure the champion, so it stops it too.
        self._ollama(stop=True)
        result = probes.evaluate(self._base_model(), adapter, samples=GATE_SAMPLES,
                                 confirm=GATE_CONFIRM, temperature=GATE_TEMPERATURE,
                                 top_p=GATE_TOP_P,
                                 log=lambda line: self._note(line))
        return {"passed": result["passed"], "total": result["total"],
                "passed_ids": result["passed_ids"],
                "lanes": probes.lane_stats(result),
                "failures": [f["id"] for f in result["failures"]],
                "rechecked": result.get("rechecked") or [],
                "version": GATE_VERSION}


class FakeBackend(Backend):
    """A deterministic stand-in: proves the policy without spending GPU time."""

    def __init__(self, improve: bool = True) -> None:
        self.improve = improve
        self.calls: list[str] = []
        self.inits: list[str] = []

    def night(self, levers, log):
        self.calls.append("night")
        return {"attempts": 100 * levers.samples, "match": 40 * levers.samples}

    def mine(self, levers, log):
        self.calls.append("mine")
        return {"pairs": 5 * levers.per_family, "families": 12}

    def train(self, cycle, levers, init, log):
        self.calls.append("train")
        self.inits.append(init)
        return f"fake/auto{cycle}/sft"

    def orpo(self, cycle, levers, init, log):
        self.calls.append("orpo")
        return f"fake/auto{cycle}/orpo"

    def evaluate(self, adapter, log):
        self.calls.append("evaluate")
        if not adapter:  # the baseline every cycle is judged against
            return {"family": metrics(14, 48), "task": metrics(9, 24)}
        cycle = int("".join(c for c in adapter.split("auto")[-1] if c.isdigit()) or 1)
        base = 14 if self.improve else 10
        return {"family": metrics(base + cycle, 48), "task": metrics(9 + cycle, 24)}

    def gate(self, adapter, log):
        self.calls.append("gate")
        return {"passed": 7, "total": 10, "failures": []}


def _pools(state: dict) -> dict:
    """The two held-out pools, frozen so cycles stay comparable — within a rule.

    The freeze is what made a restart keep scoring the old 56-set family pool
    after the split had moved to families with siblings. A versioned freeze
    keeps the comparison stable across cycles and rebuilds when the rule itself
    changes; the champion's numbers are then not comparable, so they are cleared
    and the baseline is measured again.
    """
    if state.get("pools") and state.get("pools_version") == POOLS_VERSION:
        return state["pools"]
    family = [t["id"] for t in functioneval.held_out_tasks(by_family=True)]
    task = [t["id"] for t in functioneval.held_out_tasks()]
    rebuilt = bool(state.get("pools")) or bool(state.get("best_metrics"))
    state["pools"] = {"family": family, "task": task}
    state["pools_version"] = POOLS_VERSION
    if rebuilt:
        state["best_metrics"] = None
        state["best"] = ""
    return state["pools"]


def run(cycles: int = 3, hours: float = 6.0, backend: Backend | None = None,
        levers: Levers | None = None, log=None) -> dict:
    """Run cycles until the budget, the stop file, or the ladder is spent."""
    log = log or (lambda line: None)
    state = read_state()
    pools = _pools(state)
    # Pool lookup ignores the lane cut: a frozen pool must resolve whole, or the
    # candidate is scored on fewer sets than the champion and the verdicts compare
    # two different measurements.
    tasks = {t["id"]: t for t in functionprobe.pool_candidates()}
    backend = backend or RealBackend({key: [tasks[i] for i in ids if i in tasks]
                                      for key, ids in pools.items()})
    state.setdefault("cycle", 0)
    state.setdefault("best", None)
    state.setdefault("best_metrics", None)
    state.setdefault("tried", [])
    state["levers"] = asdict(levers or _stored_levers(state))
    save_state(state)
    # A pending stop file is honoured, not cleared: an unattended loop that
    # restarts itself must not overrule the person who stopped it.
    deadline = time.monotonic() + hours * 3600 if hours > 0 else float("inf")
    publish(state="running", started_at=now(), cycle=state.get("cycle", 0),
            hours=hours, best=state.get("best"), best_metrics=state.get("best_metrics"),
            levers=state["levers"], stage="starting", pid=os.getpid())

    # The touchstone is the untouched model, measured once. Without it the
    # first candidate would win by default and a whole run could chase a
    # regression that nothing ever compared against.
    if not state.get("best_metrics"):
        publish(stage="baseline")
        log("baseline: scoring the untouched model once")
        baseline = backend.evaluate("", log)
        baseline["gate"] = backend.gate("", log)
        baseline["adapter"] = ""
        state["best"] = ""
        state["best_metrics"] = {k: baseline[k]
                                 for k in ("family", "task", "gate", "rows") if k in baseline}
        journal({"cycle": 0, "at": now(), "baseline": baseline})
        save_state(state)
    elif state.get("gate_version") != GATE_VERSION:
        # The stored gate belongs to the rule that measured it. A candidate's
        # 9/10 under sampling is not comparable to a champion's 9/10 under
        # greedy decoding, so the bar is measured again before it judges anyone.
        publish(stage="gate-baseline")
        log("gate rule changed: re-measuring the champion's battery")
        state["best_metrics"]["gate"] = backend.gate(state["best"], log)
        save_state(state)
        publish(best_metrics=state["best_metrics"])
    state["gate_version"] = GATE_VERSION
    save_state(state)

    # Same rule for the scoring itself: one row per set was one draw, and a
    # champion measured that way cannot be paired against a candidate measured
    # on two. Measuring the champion again under the new rule is the price of a
    # verdict that compares like with like.
    if state.get("best_metrics") and state.get("eval_version") != EVAL_VERSION:
        publish(stage="eval-baseline")
        log(f"scoring rule changed: re-measuring the champion on {EVAL_DRAWS} draws")
        rescored = backend.evaluate(state["best"], log)
        for key in ("family", "task", "rows"):
            if key in rescored:
                state["best_metrics"][key] = rescored[key]
        save_state(state)
        publish(best_metrics=state["best_metrics"])
    state["eval_version"] = EVAL_VERSION
    save_state(state)

    started_cycle = int(state.get("cycle", 0)) + 1
    try:
        for cycle in range(started_cycle, started_cycle + max(1, cycles)):
            if stop_requested() or time.monotonic() > deadline:
                publish(state="stopped", reason="stop file or budget")
                break
            current = Levers(**state["levers"])
            t0 = time.monotonic()
            marks: dict[str, float] = {}
            publish(cycle=cycle, stage="night", levers=asdict(current))
            log(f"cycle {cycle}: night {current.night_hours}h, "
                f"samples={current.samples}")
            night = backend.night(current, log)
            marks["night"] = time.monotonic()
            publish(night=night, stage="mine")
            mined = backend.mine(current, log)
            marks["mine"] = time.monotonic()
            publish(mined=mined, stage="train")
            init = state["best"] if (current.continue_from_best and state["best"]) else ""
            sft = backend.train(cycle, current, init, log)
            marks["sft"] = time.monotonic()
            publish(stage="orpo", adapter=sft)
            candidate = backend.orpo(cycle, current, sft, log)
            marks["orpo"] = time.monotonic()
            publish(stage="evaluate", adapter=candidate)
            scored = backend.evaluate(candidate, log)
            marks["evaluate"] = time.monotonic()
            scored["gate"] = backend.gate(candidate, log)
            marks["gate"] = time.monotonic()
            scored["adapter"] = candidate

            accepted, reason = judge(state["best_metrics"], scored)
            took = _took(t0, marks)
            log(f"cycle {cycle}: took {took['total']}s "
                + " ".join(f"{name}={value}s" for name, value in took.items()
                           if name != "total"))
            entry = {"cycle": cycle, "at": now(), "night": night, "mined": mined,
                     "candidate": scored, "accepted": accepted, "reason": reason,
                     "took": took, "levers": asdict(current)}
            journal(entry)
            state["cycle"] = cycle
            if accepted:
                state["best"] = candidate
                state["best_metrics"] = {k: scored[k] for k in
                                         ("family", "task", "gate", "rows") if k in scored}
                state["levers"] = asdict(BASE)
                state["tried"] = []
            else:
                nxt, note, key = escalate(current, state["tried"])
                if not note:
                    publish(state="done", stage="ladder-spent", best=state["best"],
                            best_metrics=state.get("best_metrics"),
                            reason="no untried lever left; growth needs new content")
                    log("ladder spent: the next gain needs new program families")
                    journal({"cycle": cycle, "at": now(), "stopped": "ladder spent"})
                    save_state(state)
                    return publish()
                state["levers"] = asdict(nxt)
                state["tried"] = state["tried"] + [key]
                log(f"cycle {cycle}: rejected ({reason}); next lever: {note}")
            save_state(state)
            publish(cycle=cycle, stage="judged", accepted=accepted,
                    reason=reason, best=state["best"], took=entry["took"],
                    best_metrics=state.get("best_metrics"))
            write_report(state, history())
            if stop_requested() or time.monotonic() > deadline:
                publish(state="stopped", reason="stop file or budget")
                break
        else:
            publish(state="done", stage="cycles-exhausted", best=state["best"],
                    best_metrics=state.get("best_metrics"))
    except Exception as err:  # an unattended loop reports, it does not hang
        publish(state="failed", error=f"{type(err).__name__}: {err}"[:400])
        journal({"at": now(), "error": f"{type(err).__name__}: {err}"[:400]})
        save_state(state)
        raise
    save_state(state)
    write_report(state, history())
    return publish()


def write_report(state: dict, rows: list[dict]) -> Path:
    """A table a person can read without opening the journal."""
    lines = ["# autoloop", "",
             f"Updated {now()} · cycle {state.get('cycle', 0)} · "
             f"best `{state.get('best')}`", ""]
    best = state.get("best_metrics") or {}
    if best:
        lines += [f"Champion: family {best['family']['match']}/{best['family']['attempts']}"
                  f" · task {best['task']['match']}/{best['task']['attempts']}"
                  f" · gate {best['gate']['passed']}/{best['gate']['total']}", ""]
    lines += ["| cycle | night match | mined | family | task | gate | verdict |",
              "|---|---|---|---|---|---|---|"]
    for row in rows:
        if "candidate" not in row:
            continue
        cand = row["candidate"]
        lines.append(
            f"| {row['cycle']} | {row.get('night', {}).get('match', '')}/"
            f"{row.get('night', {}).get('attempts', '')} | "
            f"{row.get('mined', {}).get('pairs', '')} | "
            f"{cand['family']['match']}/{cand['family']['attempts']} | "
            f"{cand['task']['match']}/{cand['task']['attempts']} | "
            f"{cand['gate']['passed']}/{cand['gate']['total']} | "
            f"{'kept' if row.get('accepted') else 'dropped'} — {row.get('reason', '')} |")
    last = next((row for row in reversed(rows) if "candidate" in row), None)
    if last:
        night = last.get("night") or {}
        if night.get("pool"):
            lines += ["", f"Night pool: {night['pool']} sets · "
                          f"{night.get('cold', 0)} never probed · "
                          f"{night.get('unpassed', 0)} probed but never passed"]
        lanes = ((last.get("candidate") or {}).get("gate") or {}).get("lanes") or {}
        if lanes:
            lines += ["Gate lanes: " + " · ".join(
                f"{lane} {slot['passed']}/{slot['total']}" for lane, slot in lanes.items())]
    path = loop_dir() / REPORT_FILE
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Unattended cycles: probe, mine, train, score, judge, escalate")
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--hours", type=float, default=6.0,
                        help="wall-clock budget for the whole run (0 = no limit)")
    parser.add_argument("--fake", action="store_true",
                        help="run the policy against a synthetic backend")
    parser.add_argument("--stop", action="store_true", help="stop a running loop")
    parser.add_argument("--status", action="store_true", help="print the status file")
    parser.add_argument("--report", action="store_true", help="print the report")
    parser.add_argument("--reset", action="store_true",
                        help="forget the champion and the frozen pools")
    args = parser.parse_args(argv)

    if args.stop:
        print(request_stop())
        return 0
    if args.status:
        path = status_path()
        print(path.read_text(encoding="utf-8") if path.exists() else "no status yet")
        return 0
    if args.report:
        path = loop_dir() / REPORT_FILE
        print(path.read_text(encoding="utf-8") if path.exists() else "no report yet")
        return 0
    if args.reset:
        state_path().unlink(missing_ok=True)
        stop_path().unlink(missing_ok=True)
        print("state cleared")
        return 0

    result = run(cycles=args.cycles, hours=args.hours,
                 backend=FakeBackend() if args.fake else None,
                 log=lambda line: print(line, flush=True))
    print(json.dumps({k: result.get(k) for k in
                      ("state", "cycle", "best", "reason", "error")}, indent=2))
    return 0 if result.get("state") in ("done", "stopped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
