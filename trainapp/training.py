"""training — export the dataset and run the LoRA job where the GPUs are.

Training is the one part of this app that does not happen locally by default:
the harness and the desktop have no VRAM to spare, and the agent box already
has the trainer venv. `backend: "agent"` copies the dataset + trainer over and
runs it under ssh; `backend: "local"` runs the same trainer here.

The job is tracked in one process-wide slot (a single training run at a time),
with its log on disk so a restart can still show the last run's output.
"""
from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import capture, config, preferences

JOB_LOCK = threading.RLock()  # status() is called from inside locked sections
JOB: dict = {
    "state": "idle",          # idle | running | done | failed | stopped
    "backend": "",
    "mode": "sft",
    "model": "",
    "started_at": "",
    "finished_at": "",
    "log": "",
    "command": "",
    "pid": None,
    "exit_code": None,
    "error": "",
}
_PROC: subprocess.Popen | None = None


def _trainer_path() -> Path:
    return config.APP_ROOT / "train_lora.py"


def dataset_ready() -> bool:
    return (config.dataset_dir() / "train.jsonl").exists()


def ensure_dataset(mode: str = "sft") -> dict:
    """Export before every run so training always sees the latest data."""
    if mode == "orpo":
        meta = preferences.export_pairs()
        if meta["train_pairs"] == 0:
            raise RuntimeError(
                "no preference pairs yet — run a style tournament first"
            )
        return meta
    meta = capture.export_dataset()
    if meta["train_examples"] == 0:
        raise RuntimeError(
            "dataset is empty — fix a failing node first (only verified fixes are captured)"
        )
    return meta


def build_local_command(cfg: dict, meta: dict, out_dir: Path,
                        mode: str = "sft") -> list[str]:
    settings = cfg["training"]
    argv = [
        sys.executable, str(_trainer_path()),
        "--model", settings["model"],
        "--max-steps", str(settings["max_steps"]),
        "--out", str(out_dir),
    ]
    if mode == "orpo":
        argv += ["--mode", "orpo", "--pairs", meta["train_path"],
                 "--val-pairs", meta["val_path"]]
    else:
        argv += ["--train", meta["train_path"], "--val", meta["val_path"]]
    return argv


def build_agent_script(cfg: dict, meta: dict, mode: str = "sft") -> str:
    """The single bash script the agent box receives: copy, then run.

    Kept as a pure string builder so the ssh/scp shape is testable without a
    reachable host. The remote venv trains; nothing is installed remotely.
    """
    settings = cfg["training"]
    agent = settings["agent"]
    remote_dir = agent["remote_dir"]
    remote_out = settings["out_dir"]
    host = f"{agent['user']}@{agent['host']}"
    scp_target = f"{host}:{remote_dir}/"
    src_files = [meta["train_path"], meta["val_path"], str(_trainer_path())]
    quoted_src = " ".join(shlex.quote(p) for p in src_files)
    remote_argv = [
        shlex.quote(agent["python"]), "train_lora.py",
        "--model", shlex.quote(settings["model"]),
        "--max-steps", str(settings["max_steps"]),
        "--out", shlex.quote(str(Path(remote_out))),
    ]
    if mode == "orpo":
        remote_argv += ["--mode", "orpo",
                        "--pairs", shlex.quote(Path(meta["train_path"]).name),
                        "--val-pairs", shlex.quote(Path(meta["val_path"]).name)]
    else:
        remote_argv += ["--train", shlex.quote(Path(meta["train_path"]).name),
                        "--val", shlex.quote(Path(meta["val_path"]).name)]
    remote_cmd = " && ".join([
        f"mkdir -p {shlex.quote(remote_dir)}",
        f"cd {shlex.quote(remote_dir)}",
        " ".join(remote_argv),
    ])
    return "\n".join([
        "set -euo pipefail",
        f"ssh -o BatchMode=yes -o ConnectTimeout=10 {shlex.quote(host)} "
        f"'mkdir -p {remote_dir}'",
        f"scp -o BatchMode=yes -o ConnectTimeout=10 {quoted_src} {scp_target}",
        f"ssh -o BatchMode=yes -o ConnectTimeout=10 {shlex.quote(host)} "
        f"{shlex.quote(remote_cmd)}",
    ])


def _log_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return config.runs_dir() / f"train-{stamp}.log"


def _watch(proc: subprocess.Popen, log_path: Path) -> None:
    code = proc.wait()
    with JOB_LOCK:
        JOB["exit_code"] = code
        JOB["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if JOB["state"] == "stopped":
            pass
        elif code == 0:
            JOB["state"] = "done"
        else:
            JOB["state"] = "failed"
            JOB["error"] = f"trainer exited {code} — see {log_path}"
        JOB["pid"] = None


def start(backend: str | None = None, model: str | None = None,
          max_steps: int | None = None, mode: str | None = None) -> dict:
    """Kick off one training run. Returns the job snapshot (never raises)."""
    global _PROC
    with JOB_LOCK:
        if _PROC is not None and _PROC.poll() is None:
            return {**status(), "error": "a training run is already in progress"}

        cfg = config.load()
        settings = cfg["training"]
        if backend:
            settings["backend"] = backend
        if model:
            settings["model"] = model
        if max_steps:
            settings["max_steps"] = int(max_steps)
        if mode:
            settings["mode"] = mode
        run_mode = settings.get("mode", "sft")

        try:
            meta = ensure_dataset(run_mode)
        except RuntimeError as err:
            return {**status(), "error": str(err)}

        out_dir = config.data_dir() / "models" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = _log_path()

        if settings["backend"] == "agent":
            script = build_agent_script(cfg, meta, run_mode)
            argv = ["bash", "-c", script]
            shown = script.replace("\n", " ; ")[:2000]
        else:
            argv = build_local_command(cfg, meta, out_dir, run_mode)
            shown = " ".join(shlex.quote(a) for a in argv)

        log_handle = log_path.open("w", encoding="utf-8")
        log_handle.write(f"# {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n")
        log_handle.write(f"# backend={settings['backend']} model={settings['model']}\n")
        log_handle.write(f"# command: {shown}\n\n")
        log_handle.flush()
        try:
            proc = subprocess.Popen(
                argv, stdout=log_handle, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True,
                cwd=str(config.APP_ROOT),
            )
        except OSError as err:
            log_handle.write(f"\nlaunch failed: {err}\n")
            log_handle.close()
            JOB.update(state="failed", error=str(err), log=str(log_path),
                       finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            return {**status(), "error": str(err)}

        _PROC = proc
        JOB.update({
            "state": "running",
            "backend": settings["backend"],
            "mode": run_mode,
            "model": settings["model"],
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "finished_at": "",
            "log": str(log_path),
            "command": shown,
            "pid": proc.pid,
            "exit_code": None,
            "error": "",
        })
        threading.Thread(target=_watch, args=(proc, log_path), daemon=True).start()
        return status()


def stop() -> dict:
    global _PROC
    proc = _PROC
    if proc is None or proc.poll() is not None:
        return {**status(), "error": "no training run is active"}
    with JOB_LOCK:
        JOB["state"] = "stopped"
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        proc.terminate()
    return status()


def tail(lines: int = 40) -> str:
    log = JOB.get("log")
    if not log or not Path(log).exists():
        return ""
    text = Path(log).read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(text[-lines:])


def status() -> dict:
    with JOB_LOCK:
        snap = dict(JOB)
    snap["tail"] = tail()
    snap["dataset"] = capture.stats()
    snap["pairs"] = preferences.stats()
    return snap


def recent_runs(limit: int = 10) -> list[dict]:
    files = sorted(config.runs_dir().glob("train-*.log"), reverse=True)[:limit]
    return [{"log": str(p), "bytes": p.stat().st_size,
             "modified": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
             .isoformat(timespec="seconds")} for p in files]
