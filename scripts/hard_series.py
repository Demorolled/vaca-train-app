"""Run harder briefs through the running VACA app, one build at a time.

The builds go through the app's own API (`POST /api/builder/start`), not around
it, so this exercises the route the UI uses: the series job publishes progress,
writes the pool after each app, and rewrites the scaffold snapshot with it.

    python -m scripts.hard_series --base http://127.0.0.1:8137

Each brief is deliberately a step up from the single-file apps: several files
that must agree on an interface, real state, and an entry that has to import
its siblings. Anything a model gets wrong is what the pool is for.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BRIEFS = [
    {
        "language": "python",
        "brief": "A Python CLI todo manager in at least three files: a Task model, a "
                 "JSON store that loads and saves tasks in a file next to the script, "
                 "and an entry point with subcommands add <text>, list and done <id>. "
                 "No third-party dependencies.",
    },
    {
        "language": "go",
        "brief": "A Go program in two files in package main: one file defines a Stack "
                 "type with Push, Pop and Len methods and a Reverse helper, the other "
                 "has main() which reverses a hardcoded slice of names and prints each "
                 "on its own line. Standard library only.",
    },
    {
        "language": "typescript",
        "brief": "A Node TypeScript program in three files: a Store class that holds "
                 "items with an id and a name, a formatter module that renders them as "
                 "'<id>: <name>' lines, and an entry point that builds a hardcoded list "
                 "and prints it. No dependencies.",
    },
]


def call(base: str, path: str, body: dict | None = None, method: str = "GET") -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base.rstrip("/") + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        return {"error": err.read().decode()[:300], "status": err.code}


def wait(base: str, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = call(base, "/api/builder/status")
        if state.get("state") != "running":
            return state
        print(f"  … {state.get('done')}/{state.get('apps')} {state.get('current', '')}",
              flush=True)
        time.sleep(10)
    return {"state": "timeout", "error": f"no finish within {timeout_s:.0f}s"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Harder builds through the VACA app")
    parser.add_argument("--base", default="http://127.0.0.1:8137")
    parser.add_argument("--connection", default="builder2")
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args(argv)

    for index, spec in enumerate(BRIEFS, start=1):
        print(f"\n[{index}/{len(BRIEFS)}] {spec['language']}: {spec['brief'][:80]}...",
              flush=True)
        started = call(args.base, "/api/builder/start", {
            "brief": spec["brief"], "languages": spec["language"], "apps": 1,
            "attempts": args.attempts, "connection": args.connection,
        }, method="POST")
        if started.get("error"):
            print(f"  refused: {started['error']}", flush=True)
            continue
        final = wait(args.base, args.timeout)
        for record in final.get("records") or []:
            print(f"  {'ok' if record['ok'] else 'FAILED'} runs={record['runs']} "
                  f"files={record['files']} conventions={record['conventions']} "
                  f"added={record['added']}", flush=True)
        if final.get("error"):
            print(f"  error: {final['error']}", flush=True)
        print(f"  scaffold: {json.dumps(final.get('scaffold') or {}, sort_keys=True)}",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
