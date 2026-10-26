"""trainloop — one clean SFT pass, then ORPO rounds that stop on held-out gain.

A round is: re-export the proof-gated sheets (verified corrections, VACA app
rows, verified base/medium builds) and every judged pair (tournament verdicts
plus caught puzzle mutations), train a new adapter on top of the previous one,
and read the held-out preference accuracy the trainer writes to
`train_meta.json`.

The loop keeps a round only when accuracy improves by at least `MIN_GAIN`;
otherwise it stops and reports the last adapter that did. Nothing here invents
signal: a round with no new pairs trains on the same data again, so the stop
rule is what keeps the loop from overfitting indefinitely.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import (buildfix, capture, config, contractsft, functioneval, functionprobe,
               librarysft, overnight, plansft, preferences, probes, puzzlepairs,
               scaffoldsft)

MIN_GAIN = 0.005
STATUS_FILE = "trainloop.status.json"
HISTORY_FILE = "history.jsonl"
LOG_FILE = "loop.log"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def status_path() -> Path:
    return config.data_dir() / STATUS_FILE


def loop_dir() -> Path:
    path = config.data_dir() / "trainloop"
    path.mkdir(parents=True, exist_ok=True)
    return path


def publish(**fields) -> dict:
    """Merge a status update into `trainloop.status.json`."""
    path = status_path()
    current: dict = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
    current.update(fields)
    path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return current


def _pair_key(row: dict) -> str:
    return hashlib.sha256(
        (row.get("chosen", "") + "\0" + row.get("rejected", "")).encode("utf-8")
    ).hexdigest()


def _split(rows: list[dict], val_ratio: float = 0.1) -> tuple[list[dict], list[dict]]:
    """The same hash rule `preferences.export_pairs` uses, so a re-split agrees."""
    train: list[dict] = []
    val: list[dict] = []
    cut = max(1, round(max(val_ratio, 0.0) * 100))
    for row in rows:
        bucket = int(_pair_key(row)[:8], 16) % 100
        (val if bucket < cut else train).append(row)
    if not train and val:
        val.sort(key=_pair_key)
        train.append(val.pop())
    return train, val


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


# One ORPO round leaves the contract lanes worse than it found them. The pairs
# teach which of two builds is the smaller one, and a 1.5B model generalises
# that into giving up the instruction-following the app depends on: fences came
# back around every file, and a single-file plan request was answered with a
# 24-line project. Neither shows up in preference accuracy — the round that went
# 0.54 -> 0.61 scored 2/11 on the boundary probes while the SFT-only adapter it
# started from scored 10/11.
#
# The round therefore ends by rehearsing the two sheets that teach exactly the
# lanes the probes grade (`contractsft` for the refusal and the repair,
# `scaffoldsft` for writing one file to fit its siblings). A few steps at the
# same learning rate put the contract back on top of the preference gain, so the
# round can be kept instead of being refused by its own gate.
REHEARSAL_STEPS = 15
REHEARSAL_FILE = "rehearsal.jsonl"


def rehearsal_sheet(held: set[str] | None = None,
                    all_languages: bool = False) -> Path:
    """Write the contract rows a round rehearses after its preference pass.

    `held` is the same family hold-out the round's other rows obey: a contract
    row built from a held-out set teaches the files the split scores.
    """
    rows = [row for row in (contractsft.rows(all_languages=all_languages)
                            + scaffoldsft.rows(all_languages=all_languages))
            if not held or (row.get("meta") or {}).get("task_id") not in held]
    out = config.dataset_dir() / REHEARSAL_FILE
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                   encoding="utf-8")
    return out


def merge_pairs(extra_rows: list[dict], val_ratio: float = 0.1) -> dict:
    """Add puzzle rows to the tournament train/val sheets, deduped and re-split."""
    out = config.dataset_dir()
    existing = _read_jsonl(out / "pairs_train.jsonl") + _read_jsonl(out / "pairs_val.jsonl")
    seen: set[str] = set()
    rows: list[dict] = []
    for row in existing + list(extra_rows):
        key = _pair_key(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    train, val = _split(rows, val_ratio)
    (out / "pairs_train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in train), encoding="utf-8")
    (out / "pairs_val.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in val), encoding="utf-8")
    meta_path = out / "pairs_meta.json"
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
    meta.update({
        "total_pairs": len(rows),
        "train_pairs": len(train),
        "val_pairs": len(val),
        "puzzle_pairs": len(extra_rows),
        "val_ratio": val_ratio,
        "source": "tournament+puzzle:preference",
        "sources": {"tournament": len(existing), "puzzle": len(extra_rows)},
        "merged_at": _now(),
    })
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


# The tournament sheet is self-selected "winners" rather than a verified program,
# and the loop measured what it costs: the no-fence lane went 7/10 -> 3/10 when
# those rows carried the mix. It was 22% of the SFT sheet by row count.
DROPPED_SOURCES = ("tournament:winner",)


def prepare_data(by_family: bool = False, per_language: int = 3,
                 all_languages: bool = False, mix: str = "all",
                 with_buildfix: bool = False) -> dict:
    """Export SFT rows (verified builds + verified app sets) and merge pairs in.

    A finished `trainapp.overnight` run exports its passing functions and its
    same-prompt pairs here, so a night of verified generation is what the next
    round trains on instead of a second pipeline that nobody runs.

    `by_family` holds out whole program families (the fibonacci ask in every
    language) rather than single task ids. A task split leaves the siblings of
    a held-out set in training, so a family cannot be measured with it.

    `mix="programs"` leaves out the plan and contract (repair/invent) rows, so a
    round sees whole programs only. Those two sheets are 41% of the SFT rows and
    they teach a different task shape; the mix A/B turns them off to see whether
    they help or dilute the behaviour the held-out families score.

    `with_buildfix=True` adds rows mined from the night's own build failures: the
    compiler's complaint and the library's working function for the same ask.
    It is off by default so the round that measures it is the round that asks for
    it, and it obeys the same hold-out as every other source.
    """
    programs_only = mix == "programs"
    night = overnight.load_export()
    # Only behaviour-verified night rows teach: a row that merely compiled is
    # the lesson that produced format-perfect, non-working code before.
    behaviour = [r for r in night["sft"] if r.get("verified") == "behaviour"]

    held = (functioneval.family_holdout_ids(functionprobe.candidates())
            if by_family else functioneval.holdout_task_ids(behaviour))
    fresh = [r for r in behaviour if r.get("task_id") not in held]
    night_pairs = [p for p in night["pairs"]
                   if p.get("task_id") not in held]
    # Scaffold and plan rows are built from the library's multi-file sets. A row
    # for a held-out family's set teaches the very files the split is meant to
    # score, which would make the family number partly memory.
    scaffold_rows = [r for r in scaffoldsft.rows(all_languages=all_languages)
                     if (r.get("meta") or {}).get("task_id") not in held]
    library_rows = librarysft.rows(per_language=per_language,
                                   all_languages=all_languages)
    plan_rows = [r for r in ([] if programs_only else
                             plansft.rows(all_languages=all_languages))
                 if (r.get("meta") or {}).get("task_id") not in held]
    contract_rows = [r for r in ([] if programs_only else
                                 contractsft.rows(all_languages=all_languages))
                     if (r.get("meta") or {}).get("task_id") not in held]
    # Build-failure rows are held out by *family*, not by set: a repair row for
    # the ISBN checksum in Kotlin teaches the same program the pool measures in
    # Python, and an id-level hold-out would let it through.
    held_families = (functioneval.holdout_families(functionprobe.pool_candidates())
                     if with_buildfix else set())
    buildfix_rows = ([r for r in buildfix.rows()
                      if (r.get("meta") or {}).get("family") not in held_families]
                     if with_buildfix else [])
    buildfix_pairs = ([p for p in buildfix.pairs()
                       if (p.get("meta") or {}).get("family") not in held_families]
                      if with_buildfix else [])
    sft = capture.export_dataset(
        extra_rows=(library_rows + plan_rows + contract_rows + scaffold_rows
                    + fresh + buildfix_rows),
        drop_sources=DROPPED_SOURCES)
    tournament = preferences.export_pairs()
    puzzle_rows = puzzlepairs.training_rows()
    pairs = merge_pairs(puzzle_rows + night_pairs + buildfix_pairs)
    return {"sft": sft, "tournament": tournament, "pairs": pairs,
            "puzzle_pairs": len(puzzle_rows),
            "dropped_sources": list(DROPPED_SOURCES),
            "library_rows": len(library_rows),
            "plan_rows": len(plan_rows),
            "contract_rows": len(contract_rows),
            "per_language": per_language,
            "scaffold_rows": len(scaffold_rows),
            "night_rows": len(fresh),
            "night_pairs": len(night_pairs),
            "buildfix_rows": len(buildfix_rows),
            "buildfix_pairs": len(buildfix_pairs),
            "night_holdout": len(behaviour) - len(fresh),
            "holdout": "family" if by_family else "task",
            "mix": mix,
            "all_languages": all_languages,
            "night_compile_only": len(night["sft"]) - len(behaviour)}


def should_continue(history: list[dict], min_gain: float = MIN_GAIN) -> bool:
    """Keep looping only while the newest round beat the best earlier round."""
    scores = [entry.get("accuracy") for entry in history
              if isinstance(entry.get("accuracy"), (int, float))]
    if len(scores) < 2:
        return True
    return scores[-1] > max(scores[:-1]) + min_gain


def _stop_ollama(log) -> None:
    """Training needs the VRAM the coder's GGUF holds."""
    model = config.load().get("llm", {}).get("model", "")
    if not model:
        return
    try:
        subprocess.run(["ollama", "stop", model], check=False,
                       stdout=log, stderr=subprocess.STDOUT, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass


def _train(argv: list[str], log) -> int:
    log.write(f"\n$ {' '.join(argv)}\n")
    log.flush()
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "0",
           "PYTHONPATH": str(config.APP_ROOT),
           "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}
    completed = subprocess.run(argv, cwd=str(config.APP_ROOT), env=env,
                               stdout=log, stderr=subprocess.STDOUT)
    return completed.returncode


def _meta(adapter_dir: Path) -> dict:
    path = adapter_dir / "train_meta.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _probe(model: str, adapter: Path, log) -> dict | None:
    """Score the boundary battery, or None when this box cannot run it."""
    def note(message: str) -> None:
        log.write(f"{message}\n")
        log.flush()

    try:
        return probes.evaluate(model, str(adapter), log=note)
    except Exception as err:  # no transformers/torch here: train without the gate
        note(f"[{_now()}] probe gate unavailable: {type(err).__name__}: {err}")
        return None


def run(rounds: int = 2, sft_steps: int = 120, orpo_steps: int = 60,
        seq_len: int = 1024, skip_sft: bool = False, probe_gate: bool = True,
        by_family: bool = False, rehearsal_steps: int = REHEARSAL_STEPS) -> dict:
    log_path = loop_dir() / LOG_FILE
    models_dir = config.data_dir() / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    base_model = config.load().get("training", {}).get("model",
                                                       "Qwen/Qwen2.5-Coder-1.5B-Instruct")

    with log_path.open("a", encoding="utf-8") as log:
        publish(state="running", stage="data", round=0, error="", started_at=_now(),
                finished_at="", log=str(log_path), base_model=base_model)
        data = prepare_data(by_family)
        log.write(f"\n[{_now()}] data prepared: {json.dumps(data)}\n")
        log.flush()

        current = models_dir / "clean1"
        if not (current / "adapter").exists():
            if skip_sft:
                publish(state="failed", stage="sft", error="no clean1 adapter and --skip-sft")
                return publish(finished_at=_now())
            publish(stage="sft", round=0)
            _stop_ollama(log)
            rc = _train([sys.executable, "train_lora.py", "--mode", "sft",
                         "--train", str(config.dataset_dir() / "train.jsonl"),
                         "--val", str(config.dataset_dir() / "val.jsonl"),
                         "--model", base_model, "--out", str(current),
                         "--max-steps", str(sft_steps), "--seq-len", str(seq_len)], log)
            if rc != 0:
                publish(state="failed", stage="sft", error=f"SFT exited {rc}",
                        finished_at=_now())
                return publish()
            sft_meta = _meta(current)
            publish(stage="sft-done", sft_rows=sft_meta.get("train_rows"),
                    sft_val_rows=sft_meta.get("val_rows"))

        baseline_probes: dict | None = None
        if probe_gate:
            publish(stage="probes", round=0)
            _stop_ollama(log)
            baseline_probes = _probe(base_model, current / "adapter", log)
            publish(probe_baseline=probes.summary(baseline_probes) if baseline_probes else {})

        def record(row: dict) -> None:
            with (loop_dir() / HISTORY_FILE).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

        history: list[dict] = []
        best: float | None = None
        for index in range(1, max(1, rounds) + 1):
            out = models_dir / f"loop{index}"
            publish(stage="orpo", round=index, adapter=str(out),
                    history=history)
            _stop_ollama(log)
            rc = _train([sys.executable, "train_lora.py", "--mode", "orpo",
                         "--pairs", str(config.dataset_dir() / "pairs_train.jsonl"),
                         "--val-pairs", str(config.dataset_dir() / "pairs_val.jsonl"),
                         "--model", base_model, "--out", str(out),
                         "--init-adapter", str(current / "adapter"),
                         "--max-steps", str(orpo_steps), "--seq-len", str(seq_len)], log)
            meta = _meta(out)
            accuracy = (meta.get("val") or {}).get("accuracy")
            before = (meta.get("val_before") or {}).get("accuracy")
            # Preference first, contract last: the rehearsal is what lets the
            # round keep the pair gain without handing the lanes back (see
            # `rehearsal_sheet`). The accuracy above is still ORPO's own number.
            final = out
            if rc == 0 and rehearsal_steps > 0:
                held = functioneval.family_holdout_ids(functionprobe.candidates())
                sheet = rehearsal_sheet(held)
                publish(stage="rehearsal", round=index)
                rc = _train([sys.executable, "train_lora.py", "--mode", "sft",
                             "--train", str(sheet), "--model", base_model,
                             "--out", str(out / "rehearsal"),
                             "--init-adapter", str(out / "adapter"),
                             "--max-steps", str(rehearsal_steps),
                             "--seq-len", str(seq_len)], log)
                if rc == 0:
                    final = out / "rehearsal"
            entry = {"round": index, "exit": rc, "accuracy": accuracy,
                     "before": before, "adapter": str(final), "at": _now()}
            history.append(entry)
            publish(history=history, accuracy=accuracy, round=index)
            log.write(f"[{_now()}] round {index} exit={rc} accuracy={accuracy} "
                      f"before={before}\n")
            log.flush()
            if rc != 0 or accuracy is None:
                record(entry)
                publish(state="failed", error=f"round {index} produced no held-out accuracy",
                        finished_at=_now())
                return publish()
            if best is not None and not should_continue(history):
                record(entry)
                publish(state="done", stage="stopped", best_accuracy=best,
                        finished_at=_now(),
                        reason=f"round {index} did not beat {best} by {MIN_GAIN}")
                return publish()

            # Accuracy alone is why two earlier rounds were kept after they had
            # re-introduced fences and dropped the reasoning lane. A round that
            # loses a probe the baseline passed is not a win, whatever it scored.
            if baseline_probes:
                round_probes = _probe(base_model, final / "adapter", log)
                if round_probes:
                    broke = probes.regressions(baseline_probes, round_probes)
                    entry["probes"] = probes.summary(round_probes)
                    entry["probe_regressions"] = [b["id"] for b in broke]
                    publish(history=history, probe=probes.summary(round_probes))
                    log.write(f"[{_now()}] round {index} probes "
                              f"{round_probes['passed']}/{round_probes['total']} "
                              f"regressions={[b['id'] for b in broke]}\n")
                    log.flush()
                    if broke:
                        record(entry)
                        publish(state="done", stage="probe-gate", best_accuracy=best,
                                adapter=str(current), finished_at=_now(),
                                probe_regressions=broke,
                                reason=(f"round {index} regressed on "
                                        f"{', '.join(b['id'] for b in broke)}"))
                        return publish()
            record(entry)
            best = accuracy if best is None else max(best, accuracy)
            current = final

        publish(state="done", stage="rounds-exhausted", best_accuracy=best,
                finished_at=_now(), reason=f"{rounds} round(s) completed")
        return publish()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean SFT, then ORPO rounds over tournament + puzzle pairs")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--sft-steps", type=int, default=120)
    parser.add_argument("--orpo-steps", type=int, default=60)
    parser.add_argument("--seq-len", type=int, default=1024)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--family-holdout", action="store_true",
                        help="hold out whole program families, not single tasks")
    parser.add_argument("--skip-sft", action="store_true")
    parser.add_argument("--no-probe-gate", action="store_true",
                        help="keep a round on held-out accuracy alone")
    args = parser.parse_args(argv)

    if args.prepare_only:
        print(json.dumps(prepare_data(args.family_holdout), indent=2))
        return 0
    result = run(args.rounds, args.sft_steps, args.orpo_steps,
                 args.seq_len, args.skip_sft, not args.no_probe_gate,
                 args.family_holdout)
    print(json.dumps(result, indent=2))
    return 0 if result.get("state") == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
