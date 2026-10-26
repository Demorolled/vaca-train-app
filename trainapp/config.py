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
    # Who does what. Every connection below is a named endpoint; a role picks
    # one. `coder` answers and draws nodes, `builder` plans and writes whole
    # apps, `judge` ranks two builds. Swapping a role's connection is one entry
    # here — no code path changes, and nothing else in the app needs to know
    # which model ended up in which seat.
    "roles": {
        "coder": "llm",
        "builder": "builder",
        "judge": "judge",
    },
    # The band: every connection below is a player, switched on or off here and
    # seated by `roles`. The leader runs the builds, and every build it runs is
    # copied whole to data/builds/ (see trainapp/band.py). Adding a player is a
    # config write, so a band can be any set of models on any number of hosts.
    "band": {
        "leader": "llm",
        "copy_builds": True,
    },
    "llm": {
        # Ollama is what the agent box already runs; any OpenAI-compatible
        # endpoint can be used by changing "kind".
        "kind": "ollama",
        "url": "http://127.0.0.1:11434",
        "model": "qwen2.5-coder-14b-uncensored-q4:latest",
        "timeout_s": 300,
        "num_ctx": 16384,
        "enabled": True,
    },
    "builder": {
        # The second connection. `llm` (above) stays the coder that answers and
        # draws nodes; this one is the larger model that does the work: it plans
        # an app, writes every file, and repairs what the toolchain rejects.
        # Anything it produces is captured to data/builder/pool.jsonl, labelled
        # by model, so two models can be compared on the same series.
        # `kind: ollama` uses the native chat API, which is the only one that
        # hands back the model's own thinking text for the pool.
        "kind": "ollama",
        "url": "http://100.121.154.124:11434/v1",
        "model": "qwen3-coder:30b",
        "timeout_s": 600,
        "max_tokens": 6000,
        "temperature": 0.2,
        "attempts": 3,
        # Ask a thinking model to expose its reasoning in the reply. Coding
        # models (qwen3-coder) ignore it; a reasoning model fills the field and
        # then the pool holds both the thought and the artifact.
        "think": False,
        "enabled": True,
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
        "enabled": True,
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


def roles() -> dict[str, str]:
    """role -> connection name, with the defaults filled in."""
    return dict(load().get("roles") or {})


def connections() -> dict[str, dict]:
    """Every named endpoint: everything in the config except the bookkeeping."""
    cfg = load()
    skip = {"roles", "band", "training", "tournament"}
    return {name: value for name, value in cfg.items()
            if isinstance(value, dict) and name not in skip
            and (value.get("url") or value.get("model"))}


def connection(role: str) -> dict:
    """The settings for a role's connection, or the role's name as fallback.

    Unknown roles raise rather than silently defaulting: a typo in a role name
    should not quietly send the build to the chat model.
    """
    name = roles().get(role)
    if not name:
        raise KeyError(f"no connection assigned to role {role!r}; "
                       f"known roles: {', '.join(sorted(roles()))}")
    settings = (load().get(name) or {})
    if not settings:
        raise KeyError(f"role {role!r} points at {name!r}, which is not configured")
    return {"role": role, "name": name, **settings}


def assign(role: str, name: str) -> dict:
    """Point a role at another connection; returns the new mapping."""
    settings = load().get(name) or {}
    if not settings:
        raise KeyError(f"no connection named {name!r}")
    if settings.get("enabled") is False:
        raise KeyError(f"connection {name!r} is switched off; switch it on before seating it")
    if role not in roles():
        raise KeyError(f"unknown role {role!r}")
    merged = save({"roles": {role: name}})
    return dict(merged.get("roles") or {})


def forget(name: str) -> dict:
    """Hang up a player: drop its block from the config file.

    Only connections the user added can leave. The three bundled ones come back
    from DEFAULTS on the next load, so removing them would be a lie — switch
    them off instead.
    """
    if name in DEFAULTS or name in ("roles", "band", "training", "tournament"):
        raise KeyError(f"{name!r} is not a player you added; switch it off instead")
    raw: dict = {}
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            raw = saved if isinstance(saved, dict) else {}
        except (OSError, json.JSONDecodeError):
            raw = {}
    if name not in raw:
        raise KeyError(f"no connection named {name!r}")
    raw.pop(name)
    CONFIG_PATH.write_text(json.dumps(_deep_merge(DEFAULTS, raw), indent=2) + "\n",
                           encoding="utf-8")
    return load()
