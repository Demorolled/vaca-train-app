#!/usr/bin/env bash
# Start the train app.  ./run.sh [--port 8137] [--host 127.0.0.1] [--open]
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

OPEN=0
ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--open" ]; then OPEN=1; else ARGS+=("$arg"); fi
done

PORT=8137
for i in "${!ARGS[@]}"; do
  if [ "${ARGS[$i]}" = "--port" ] && [ $((i + 1)) -lt ${#ARGS[@]} ]; then
    PORT="${ARGS[$((i + 1))]}"
  fi
done

python3 -m trainapp.server "${ARGS[@]}" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM

if [ "$OPEN" = "1" ]; then
  for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
      xdg-open "http://127.0.0.1:${PORT}/" >/dev/null 2>&1 || true
      break
    fi
    sleep 0.2
  done
fi

wait "$SERVER_PID"
