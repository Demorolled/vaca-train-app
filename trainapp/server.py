"""server — the harness API and the canvas UI, on the standard library only.

    python3 -m trainapp.server [--port 8137] [--host 127.0.0.1]

No framework, no venv, no network dependency: the app has to start on the
desktop and on the agent box exactly the same way.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import posixpath
import re
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import (capture, config, execution, grow, judge, library, preferences,
               repair, scoreboard, tournament, training, validate)

STATIC_DIR = Path(__file__).resolve().parent / "static"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
MAX_BODY = 2 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# ── nodes ─────────────────────────────────────────────────────────────────────

def _node_path(name: str) -> Path:
    if not NAME_RE.match(name or ""):
        raise ApiError(400, "invalid node name (letters, digits, dot, dash, underscore)")
    path = (config.nodes_dir() / name).resolve()
    if path.parent != config.nodes_dir().resolve():
        raise ApiError(400, "node path escapes the nodes directory")
    return path


def list_nodes() -> list[dict]:
    nodes = []
    for path in sorted(config.nodes_dir().iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        stat = path.stat()
        nodes.append({
            "name": path.name,
            "language": execution.detect_language(path.name),
            "bytes": stat.st_size,
            "modified": int(stat.st_mtime),
        })
    return nodes


def create_node(payload: dict) -> dict:
    name = str(payload.get("name", "")).strip()
    if not execution.detect_language(name):
        raise ApiError(400, f"unknown language for {name!r}; supported extensions: "
                            + ", ".join(sorted(execution.EXTENSION_INDEX)))
    path = _node_path(name)
    if path.exists():
        raise ApiError(409, f"node {name!r} already exists")
    path.write_text(str(payload.get("code", "")), encoding="utf-8")
    return {"name": name, "language": execution.detect_language(name)}


def read_node(name: str) -> dict:
    path = _node_path(name)
    if not path.is_file():
        raise ApiError(404, f"no node {name!r}")
    return {
        "name": name,
        "language": execution.detect_language(name),
        "code": path.read_text(encoding="utf-8"),
    }


def write_node(name: str, payload: dict) -> dict:
    path = _node_path(name)
    if not path.is_file():
        raise ApiError(404, f"no node {name!r}")
    path.write_text(str(payload.get("code", "")), encoding="utf-8")
    return {"name": name, "saved": True}


def delete_node(name: str) -> dict:
    path = _node_path(name)
    if not path.is_file():
        raise ApiError(404, f"no node {name!r}")
    path.unlink()
    return {"name": name, "deleted": True}


# ── router ────────────────────────────────────────────────────────────────────

def route(method: str, path: str, payload: dict) -> dict:
    parts = [unquote(p) for p in path.strip("/").split("/") if p]

    if parts == ["api", "health"] and method == "GET":
        return {"ok": True, "app": "train-app", "platform": execution.PLATFORM_LABEL}

    if parts == ["api", "toolchains"] and method == "GET":
        return {"toolchains": execution.probe_all()}

    if parts == ["api", "config"] and method == "GET":
        cfg = config.load()
        cfg["llm"].pop("api_key", None)
        return {"config": cfg}

    if parts == ["api", "config"] and method == "POST":
        return {"config": config.save(payload)}

    if parts == ["api", "nodes"]:
        if method == "GET":
            return {"nodes": list_nodes()}
        if method == "POST":
            return create_node(payload)

    if len(parts) == 3 and parts[:2] == ["api", "nodes"]:
        name = parts[2]
        if method == "GET":
            return read_node(name)
        if method == "PUT":
            return write_node(name, payload)
        if method == "DELETE":
            return delete_node(name)

    if len(parts) == 4 and parts[:2] == ["api", "nodes"]:
        name, action = parts[2], parts[3]
        node = read_node(name)
        if action == "run" and method == "POST":
            result = execution.run_node(_node_path(name),
                                        node["language"],
                                        timeout_s=float(payload.get("timeout_s", 60)))
            return {"run": result.as_dict()}
        if action == "fix" and method == "POST":
            return repair.fix_node(
                _node_path(name),
                goal=str(payload.get("goal", "")),
                max_attempts=max(1, min(5, int(payload.get("max_attempts", 3)))),
                timeout_s=float(payload.get("timeout_s", 60)),
            )

    if parts == ["api", "dataset"] and method == "GET":
        return {**capture.stats(), "pairs": preferences.stats()}

    if parts == ["api", "dataset", "export"] and method == "POST":
        return capture.export_dataset()

    if parts == ["api", "train", "status"] and method == "GET":
        return training.status()

    if parts == ["api", "train", "start"] and method == "POST":
        job = training.start(
            backend=payload.get("backend"),
            model=payload.get("model"),
            max_steps=payload.get("max_steps"),
            mode=payload.get("mode"),
        )
        if job.get("error"):
            raise ApiError(409, job["error"])
        return job

    if parts == ["api", "train", "stop"] and method == "POST":
        return training.stop()

    if parts == ["api", "runs"] and method == "GET":
        return {"runs": training.recent_runs()}

    # ── library / validation / tournament ──
    if parts == ["api", "library"] and method == "GET":
        return {"library": library.stats(), "judge": judge.health()}

    if parts == ["api", "library", "build"] and method == "POST":
        return {"index": library.build()}

    if parts == ["api", "library", "validate"] and method == "POST":
        languages = payload.get("languages") or None
        if isinstance(languages, str):
            languages = {x.strip().lower() for x in languages.split(",") if x.strip()}
        return validate.start_background(
            languages=set(languages) if languages else None,
            limit=int(payload.get("limit", 0)),
            jobs=int(payload.get("jobs", 4)),
            timeout_s=float(payload.get("timeout_s", 20)),
            skip_typescript=bool(payload.get("skip_typescript", False)),
        )

    if parts == ["api", "library", "validate", "status"] and method == "GET":
        return validate.status()

    if parts == ["api", "library", "grow"] and method == "POST":
        started = grow.start(
            seed_count=int(payload.get("seeds", 3)),
            styles=payload.get("styles") or None,
            timeout_s=payload.get("timeout_s"),
        )
        if started.get("error"):
            raise ApiError(409, started["error"])
        return started

    if parts == ["api", "library", "grow", "status"] and method == "GET":
        return grow.status()

    if parts == ["api", "tournament", "status"] and method == "GET":
        return tournament.status()

    if parts == ["api", "tournament", "start"] and method == "POST":
        languages = payload.get("languages") or None
        if isinstance(languages, str):
            languages = {x.strip().lower() for x in languages.split(",") if x.strip()}
        started = tournament.start(
            max_tasks=payload.get("max_tasks"),
            styles=payload.get("styles") or None,
            languages=set(languages) if languages else None,
        )
        if started.get("error"):
            raise ApiError(409, started["error"])
        return started

    if parts == ["api", "judge", "health"] and method == "GET":
        return judge.health()

    if parts == ["api", "scoreboard"] and method == "GET":
        return scoreboard.summary()

    raise ApiError(404, f"no route {method} {path}")


class Handler(BaseHTTPRequestHandler):
    server_version = "train-app/0.1"

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        if "/api/" in (self.path or ""):
            super().log_message(fmt, *args)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str) -> None:
        # `/scoreboard` is the page, `scoreboard.html` is the file.
        if path in ("/scoreboard", "/scoreboard/"):
            path = "/scoreboard.html"
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        rel = posixpath.normpath(rel)
        if rel.startswith(".."):
            self._send_json(400, {"error": "bad path"})
            return
        target = (STATIC_DIR / rel).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            self._send_json(404, {"error": "not found"})
            return
        data = target.read_bytes()
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") else mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_payload(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(413, "request body too large")
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "body must be JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "body must be a JSON object")
        return data

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/"):
                payload = self._read_payload() if method in ("POST", "PUT") else {}
                self._send_json(HTTPStatus.OK, route(method, parsed.path, payload))
            elif method == "GET":
                self._serve_static(parsed.path)
            else:
                self._send_json(405, {"error": "method not allowed"})
        except ApiError as err:
            self._send_json(err.status, {"error": err.message})
        except Exception as err:  # a handler bug must not kill the server
            traceback.print_exc()
            self._send_json(500, {"error": f"{type(err).__name__}: {err}"})

    def do_GET(self) -> None:      # noqa: N802 (http.server naming)
        self._handle("GET")

    def do_POST(self) -> None:     # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:      # noqa: N802
        self._handle("PUT")

    def do_DELETE(self) -> None:   # noqa: N802
        self._handle("DELETE")


def build_server(host: str = "127.0.0.1", port: int = 8137) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train app harness")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8137)
    args = parser.parse_args()
    server = build_server(args.host, args.port)
    print(f"train-app on http://{args.host}:{args.port}/  (data: {config.data_dir()})",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
