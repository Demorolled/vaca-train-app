#!/usr/bin/env bash
# Start the train app on Linux (or macOS): http://127.0.0.1:8137/
# Everything else is the same `python3 -m trainapp.server` the README documents;
# this wrapper only saves typing and pins the working directory, so the data
# directory resolves to this checkout.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m trainapp.server "$@"
