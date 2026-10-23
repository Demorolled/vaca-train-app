"""config — paths and persisted settings for the train app.

Everything the app owns lives under APP_ROOT/data so the app is self-contained:
nodes (the files on the canvas), the corrections dataset, and run logs. Set
TRAIN_APP_DATA to point tests at a scratch directory.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_ROOT / "config.json"

DEFAULTS: dict = {
    "llm": {
        # Ollama is what the agent box already runs; any OpenAI-compatible
        # endpoint can be used by changing "kind".
        "kind": "ollama",
        "url": "http://127.0.0.1:11434",
        "model": "qwen2.5-coder-14b-uncensored-q4:latest",
        "timeout_s": 300,
        "num_ctx": 16384,
    },
    "judge": {
        # The judge is deliberately a different, much larger model than the
        # coder. The agent box serves it over the tailnet (Ollama is bound to
        # 0.0.0.0 there), so judging does not touch this desktop's VRAM.
        "url": "http://100.121.154.124:11434/v1",
        "model": "qwen3-coder:30b",
        "timeout_s": 240,
        "max_tokens": 700,
        "temperature": 0.0,
    },
    "tournament": {
        "max_tasks": 5,
        "styles": ["terse", "idiomatic", "functional", "oop", "defensive", "readable", "fast"],
        "run_timeout_s": 20,
        "repeat_runs": 3,
    },
    "training": {
        # "agent" = scp the dataset + trainer to the agent box and run it there,
        # "local" = run train_lora.py on this machine.
        "backend": "agent",
        # "sft" trains on verified rows; "orpo" trains on judged preference pairs.
        "mode": "sft",
        "model": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "max_steps": 120,
        "out_dir": "training/out/base",
        "agent": {
            "host": "llmlab-agent",
            "user": "llmlab",
            "python": "/home/llmlab/vaca-train-venv/bin/python",
            "workdir": "/home/llmlab/Desktop/visual-ai-architect",
            "remote_dir": "vaca-train-app",
        },
    },
}


def data_dir() -> Path:
    """The app's data root (created on demand)."""
    override = os.environ.get("TRAIN_APP_DATA")
    root = Path(override).expanduser() if override else APP_ROOT / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def nodes_dir() -> Path:
    path = data_dir() / "nodes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def dataset_dir() -> Path:
    path = data_dir() / "dataset"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runs_dir() -> Path:
    path = data_dir() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load() -> dict:
    """Config with defaults filled in; a corrupt file never takes the app down."""
    if not CONFIG_PATH.exists():
        return copy.deepcopy(DEFAULTS)
    try:
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(DEFAULTS)
    return _deep_merge(DEFAULTS, saved if isinstance(saved, dict) else {})


def save(patch: dict) -> dict:
    merged = _deep_merge(load(), patch)
    CONFIG_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return merged
