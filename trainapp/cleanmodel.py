"""cleanmodel — provenance for a model built on data this trainer can prove.

The adapters already on the box were trained before the capture gates existed:
some rounds learned from scaffold rows that were later purged, and there is no
record of which files went into which adapter. Rebuilding "better" on top of that
is guesswork, so a replacement starts from a manifest: exactly which sheets, how
many rows, and a digest of each, recorded next to the weights.

This module does not train. It answers the two questions that make a replacement
defensible:

  * what is in the new model's data, and can that be re-derived byte for byte?
  * which adapters are clean, and which are deprecated because their provenance
    is unknown?

`commands()` prints the training sequence, so the run itself stays in the
trainer (`train_lora.py`) rather than hiding in a shell history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import capture, config, preferences

REGISTRY_NAME = "registry.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def models_dir() -> Path:
    path = config.data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def registry_path() -> Path:
    return models_dir() / REGISTRY_NAME


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else ""


def _rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def sources() -> dict:
    """The sheets a clean model may learn from, with row counts and digests.

    Deliberately an allow-list: a sheet that is not named here cannot reach the
    manifest, which is what keeps a future "just add this file" from quietly
    reintroducing unproven rows.
    """
    data = config.dataset_dir()
    named = {
        "corrections": data / "corrections.jsonl",
        "train": data / "train.jsonl",
        "val": data / "val.jsonl",
        "pairs_train": data / "pairs_train.jsonl",
        "pairs_val": data / "pairs_val.jsonl",
        # The contract rehearsal is part of the recipe now, so it is part of the
        # provenance: an adapter's format lanes depend on which rows it ended on.
        "rehearsal": data / "rehearsal.jsonl",
        "vaca_captures": capture.app_sheet_path(),
    }
    return {name: {"path": str(path), "rows": _rows(path), "sha256_16": _digest(path)}
            for name, path in named.items()}


def manifest(out_dir: Path | str | None = None, *, model: str = "") -> dict:
    """Write the data manifest for a new adapter and return it."""
    target = Path(out_dir) if out_dir else models_dir() / "clean1"
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": _now(),
        "model": model or str(target.name),
        "base": config.load()["training"]["model"],
        "sources": sources(),
        "notes": [
            "Rows come only from proof-gated sheets: a correction is kept only "
            "when the toolchain failed before the edit and passed after, and a "
            "VACA capture only when its export was tsc-clean.",
            "App-knowledge rows are excluded: they describe the app, they are not code.",
        ],
    }
    (target / "data_manifest.json").write_text(json.dumps(payload, indent=2) + "\n",
                                              encoding="utf-8")
    return payload


def load_registry() -> dict:
    path = registry_path()
    if not path.exists():
        return {"models": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"models": {}}
    data.setdefault("models", {})
    return data


def save_registry(data: dict) -> None:
    registry_path().write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def register(name: str, path: str, *, status: str = "candidate", notes: str = "") -> dict:
    """Add or update an adapter entry. Unknown statuses are refused."""
    if status not in ("candidate", "clean", "deprecated"):
        raise ValueError(f"unknown status {status!r}")
    data = load_registry()
    data["models"][name] = {"name": name, "path": path, "status": status,
                            "notes": notes, "updated_at": _now()}
    save_registry(data)
    return data["models"][name]


def deprecate(name: str, reason: str) -> dict:
    existing = load_registry()["models"].get(name, {})
    path = existing.get("path") or str(models_dir() / name)
    return register(name, path, status="deprecated", notes=reason)


def clean_models() -> list[dict]:
    return [row for row in load_registry()["models"].values()
            if row.get("status") in ("clean", "candidate")]


def commands(out_dir: str = "data/models/clean1", *, steps: int = 120) -> list[str]:
    """The training sequence for a fresh adapter, in the order it must run."""
    return [
        "python3 -m trainapp.capture --export",
        'python3 -c "from trainapp import preferences; '
        'print(preferences.export_pairs())"',
        ("python3 train_lora.py --mode sft "
         f"--train data/dataset/train.jsonl --val data/dataset/val.jsonl "
         f"--model Qwen/Qwen2.5-Coder-1.5B-Instruct --out {out_dir} "
         f"--max-steps {steps}"),
        ("python3 train_lora.py --mode orpo --pairs data/dataset/pairs_train.jsonl "
         f"--val-pairs data/dataset/pairs_val.jsonl --out {out_dir}-orpo --max-steps 40"),
        ("python3 -c \"from trainapp import trainloop; "
         "print(trainloop.rehearsal_sheet())\""),
        ("python3 train_lora.py --mode sft --train data/dataset/rehearsal.jsonl "
         f"--model Qwen/Qwen2.5-Coder-1.5B-Instruct --out {out_dir}-orpo/rehearsal "
         f"--init-adapter {out_dir}-orpo/adapter --max-steps 15"),
        ("python3 -m trainapp.battery --model Qwen/Qwen2.5-Coder-1.5B-Instruct "
         f"--adapter {out_dir}/adapter --tasks 30"),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean-model manifest and registry")
    parser.add_argument("--manifest", nargs="?", const="", default=None, metavar="DIR")
    parser.add_argument("--register", nargs=2, metavar=("NAME", "PATH"))
    parser.add_argument("--status", default="candidate")
    parser.add_argument("--deprecate", nargs=2, metavar=("NAME", "REASON"))
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--commands", nargs="?", const="", default=None, metavar="DIR")
    args = parser.parse_args(argv)

    if args.manifest is not None:
        print(json.dumps(manifest(args.manifest or None), indent=2))
    if args.register:
        print(json.dumps(register(args.register[0], args.register[1],
                                  status=args.status), indent=2))
    if args.deprecate:
        print(json.dumps(deprecate(*args.deprecate), indent=2))
    if args.commands is not None:
        print("\n".join(line for line in commands(args.commands or "data/models/clean1")
                        if line))
    if args.list or not any((args.manifest is not None, args.register,
                             args.deprecate, args.commands is not None)):
        print(json.dumps(load_registry(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
