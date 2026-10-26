"""Run a short builder series against a connection and snapshot the conventions.

Each app is written to the pool the moment it finishes, and the scaffold
snapshot is rewritten straight after it — so the file exists after every build,
not only at the end of the series.

    python -m scripts.local_series --connection builder2 --apps 3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trainapp import builder, config, scaffold  # noqa: E402

# Small, self-contained briefs: a model that fits in 12 GB should be asked for
# an app it can finish, and every one of these prints something a build can be
# checked against.
SPECS = [
    {"id": "small/01-fib", "language": "python",
     "brief": "A Python CLI in two files: a module that returns the first 20 "
              "Fibonacci numbers as a list, and an entry point that prints them "
              "one per line. No arguments, no dependencies."},
    {"id": "small/02-wordcount", "language": "go",
     "brief": "A Go program that counts the words in a hardcoded sentence, then "
              "prints the count and the longest word. Standard library only."},
    {"id": "small/03-reverse", "language": "javascript",
     "brief": "A Node ESM program in two files: a module exporting reverseWords(text), "
              "and an entry that prints the result for a hardcoded sentence. "
              "No dependencies."},
    # The two lanes whose scaffold is a *config file*: whatever the model decides
    # to ship here is what the harness refuses or generates, so the pool records
    # the convention rather than a guess about it.
    {"id": "small/04-typescript", "language": "typescript",
     "brief": "A Node TypeScript program in two files: a module exporting "
              "wordCount(text): number, and an entry that prints the count for a "
              "hardcoded sentence. No dependencies."},
    {"id": "small/05-rust", "language": "rust",
     "brief": "A Rust program that prints the first 10 prime numbers, one per line. "
              "Standard library only."},
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Short local builder series")
    parser.add_argument("--connection", default="builder2",
                        help="a named connection in config.json")
    parser.add_argument("--apps", type=int, default=0, help="limit (0 = all specs)")
    parser.add_argument("--languages", default="",
                        help="comma-separated lanes to run, e.g. typescript,rust")
    parser.add_argument("--attempts", type=int, default=2)
    args = parser.parse_args(argv)

    cfg = config.connection("builder")
    named = config.connections().get(args.connection) or {}
    chat = builder.Chat(url=named.get("url", ""), model=named.get("model", ""),
                        max_tokens=named.get("max_tokens") or cfg.get("max_tokens"),
                        timeout_s=named.get("timeout_s") or cfg.get("timeout_s"),
                        num_ctx=named.get("num_ctx"), think=False)
    print(f"builder: {chat.model} at {chat.url} · ctx {chat.num_ctx or 'server default'}"
          f" · attempts {args.attempts}", flush=True)

    wanted = {x.strip().lower() for x in args.languages.split(",") if x.strip()}
    specs = [s for s in SPECS if not wanted or s["language"] in wanted]
    specs = specs[:args.apps] if args.apps else specs
    for spec in specs:
        print(f"\n[{spec['id']}] {spec['language']}: {spec['brief'][:70]}...", flush=True)
        record = builder.build_app(spec, chat=chat, attempts=args.attempts,
                                   log=lambda line: print(line, flush=True))
        written = builder.write_pool([record])
        snapshot = scaffold.write()
        print(f"  ok={record['ok']} runs={record['runs']} files="
              f"{[f.get('path') for f in (record.get('files') or [])]}", flush=True)
        print(f"  pool +{written['added']} · scaffold snapshot "
              f"{snapshot['notes']} notes over {snapshot['languages']}", flush=True)
    print(json.dumps(scaffold.summary(), indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
