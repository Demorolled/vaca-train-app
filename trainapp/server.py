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

from . import (band, builder, capture, config, execution, grow, harvest, judge,
               library, orchestra, preferences, repair, scaffold, scoreboard,
               tournament, training, validate)

STATIC_DIR = Path(__file__).resolve().parent / "static"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
MAX_BODY = 2 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _refused(err: KeyError) -> ApiError:
    """A refusal in its own words, without Python's extra layer of quoting."""
    return ApiError(400, str(err.args[0]) if err.args else str(err))


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
        for value in cfg.values():
            if isinstance(value, dict):
                value.pop("api_key", None)
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

    # Who is doing what: role -> connection, with the model behind each one.
    # Selecting a model for a role is a config write, so a whole series can be
    # built by one model and replayed by another without touching code.
    if parts == ["api", "roles"] and method == "GET":
        assigned = config.roles()
        connections = config.connections()
        return {"roles": {role: {"connection": name,
                                 "model": (connections.get(name) or {}).get("model", ""),
                                 "url": (connections.get(name) or {}).get("url", "")}
                          for role, name in assigned.items()},
                "connections": {name: {"model": value.get("model", ""),
                                       "url": value.get("url", "")}
                                for name, value in connections.items()}}
    if parts == ["api", "roles"] and method == "POST":
        role = str(payload.get("role") or "")
        name = str(payload.get("connection") or "")
        if not role or not name:
            raise ApiError(400, "role and connection are required")
        try:
            return {"roles": config.assign(role, name)}
        except KeyError as err:
            raise _refused(err) from err

    # ── band ──
    # Every connection is a player: a toggle, a seat, and a leader. Adding one
    # is a config write, so a whole band can be assembled from the UI without a
    # code path changing.
    if parts == ["api", "band"] and method == "GET":
        return band.summary()

    if parts == ["api", "band", "add"] and method == "POST":
        try:
            return band.add(
                name=str(payload.get("name") or ""),
                model=str(payload.get("model") or ""),
                url=str(payload.get("url") or ""),
                kind=str(payload.get("kind") or "openai"),
                timeout_s=float(payload.get("timeout_s") or 600),
                max_tokens=int(payload.get("max_tokens") or 6000),
                temperature=float(payload.get("temperature") or 0.2),
                think=bool(payload.get("think", False)),
                num_ctx=int(payload.get("num_ctx") or 0),
                api_key=str(payload.get("api_key") or ""),
            )
        except KeyError as err:
            raise _refused(err) from err

    if parts == ["api", "band", "toggle"] and method == "POST":
        try:
            return band.toggle(str(payload.get("name") or ""),
                               bool(payload.get("enabled", True)))
        except KeyError as err:
            raise _refused(err) from err

    if parts == ["api", "band", "seat"] and method == "POST":
        try:
            return band.seat(str(payload.get("role") or ""),
                             str(payload.get("name") or ""))
        except KeyError as err:
            raise _refused(err) from err

    if parts == ["api", "band", "leader"] and method == "POST":
        try:
            return band.set_leader(str(payload.get("name") or ""))
        except KeyError as err:
            raise _refused(err) from err

    if parts == ["api", "band", "copy"] and method == "POST":
        return band.set_copy_builds(bool(payload.get("enabled", True)))

    if parts == ["api", "band", "probe"] and method == "POST":
        try:
            return {"probe": band.probe(str(payload.get("name") or ""),
                                        timeout_s=float(payload.get("timeout_s") or 5))}
        except KeyError as err:
            raise _refused(err) from err

    if parts == ["api", "band", "remove"] and method == "POST":
        try:
            return band.remove(str(payload.get("name") or ""))
        except KeyError as err:
            raise _refused(err) from err

    # ── orchestra ──
    # Four seats build one app. The run is minutes long, so it is a job like the
    # builder's: started here, watched through its status, copied on completion.
    if parts == ["api", "orchestra", "status"] and method == "GET":
        return orchestra.status()

    if parts == ["api", "orchestra", "start"] and method == "POST":
        # `smoke`, `inputs` and `expect` are the caller's own statement of how
        # the program is exercised. They outrank the architect's blueprint, so
        # the test data is not written by the model being tested. `inputs` is a
        # mapping, or the `PATH=CONTENT` strings the CLI takes.
        raw_inputs = payload.get("inputs")
        try:
            inputs = (orchestra.parse_inputs(list(raw_inputs))
                      if isinstance(raw_inputs, list) else dict(raw_inputs or {}))
        except (TypeError, ValueError) as err:
            raise ApiError(400, str(err)) from err
        started = orchestra.start(
            requirement=str(payload.get("requirement") or ""),
            language=str(payload.get("language") or "python"),
            player=str(payload.get("player") or ""),
            attempts=int(payload.get("attempts") or orchestra.MAX_ATTEMPTS),
            smoke=str(payload.get("smoke") or ""),
            inputs=inputs,
            expect=str(payload.get("expect") or ""),
        )
        if started.get("error"):
            raise ApiError(409, started["error"])
        return started

    # ── harvest ──
    # Every finished build is evidence. This reads the copies on disk, adds the
    # verified ones to the library and writes the month's sheet.
    if parts == ["api", "harvest", "status"] and method == "GET":
        return harvest.status()

    if parts == ["api", "harvest", "run"] and method == "POST":
        return harvest.run(dry_run=bool(payload.get("dry_run", False)),
                           force=bool(payload.get("force", False)))

    if parts == ["api", "harvest", "scan"] and method == "GET":
        return harvest.scan()

    # ── builder ──
    # A build is minutes of a model's time, so the series runs on a thread and
    # the UI watches it: the pool is written after each app, which means a
    # series that is interrupted still keeps the apps it finished.
    if parts == ["api", "builder", "status"] and method == "GET":
        return {**builder.status(), "pool": builder.index(),
                "scaffold": scaffold.summary()}

    if parts == ["api", "builder", "start"] and method == "POST":
        languages = payload.get("languages") or None
        if isinstance(languages, str):
            languages = [x.strip().lower() for x in languages.split(",") if x.strip()]
        elif languages:
            languages = [str(x).strip().lower() for x in languages]
        started = builder.start(
            languages=list(languages) if languages else None,
            apps=int(payload.get("apps", 1) or 1),
            attempts=int(payload["attempts"]) if payload.get("attempts") else None,
            brief=str(payload.get("brief") or "").strip(),
            connection=str(payload.get("connection") or "").strip(),
        )
        if started.get("error"):
            raise ApiError(409, started["error"])
        return started

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
