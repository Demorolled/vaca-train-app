"""buildfix_gen — manufacture build-repair rows from the trainable side.

Breaks one working function per ask at a time, builds the set, and keeps only
the failures the toolchain actually reports. Writes `data/buildfix/`, which
`trainapp.buildfix.rows()` then reads alongside the night's real failures.

    python scripts/buildfix_gen.py [--limit 200] [--per-function 2]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainapp import buildfix  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--per-function", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=25)
    args = parser.parse_args(argv)

    summary = buildfix.generate(limit=args.limit,
                                per_function=args.per_function,
                                timeout_s=args.timeout,
                                log=lambda line: print(line, flush=True))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["rows"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
