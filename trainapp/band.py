"""band — every connection is a player: a toggle, a seat, and a leader.

VACA started with two models: one answers, one builds. The band generalises
that to any number of connections. Each is a player with an on/off switch and
one seat (`coder`, `builder`, `judge`), declared in `config.roles` as it always
was; one player leads. The leader on this box is Qwen2.5-Coder-14B, and it is
the one that runs builds.

Nothing here hard-codes a model. `add()` writes a new named connection and the
rest of the app never learns about it: `builder.chat_for(name)` will use it,
the battery can point at it, and the UI lists it the moment it exists. That is
the whole point — a user connects whatever they run, wherever it runs, and the
harness treats it like any other player.

Two rules keep the band honest:

- A player that still holds a seat (or leads) cannot be switched off or hung
  up. Silently leaving a seat pointing at a model nobody asked for is how a
  build ends up on the wrong endpoint.
- Every build the leader runs is copied **whole** into `data/builds/<stamp>/`:
  each reply, the model's own reasoning, every attempt's file set, the final
  files, and the toolchain's words. The pool dedupes; the copy does not. A run
  can be re-read, re-scored or mined after the fact because the copy is the run.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import config

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$")
SEATS = ("coder", "builder", "judge")


# ── who is in the band ─────────────────────────────────────────────────────

def _settings() -> dict:
    return dict(config.load().get("band") or {})


def members() -> list[dict]:
    """Every named connection, with its toggle, its seats and whether it leads."""
    seats = config.roles()
    leader = _settings().get("leader", "")
    out: list[dict] = []
    for name, settings in config.connections().items():
        out.append({
            "name": name,
            "model": settings.get("model", ""),
            "url": settings.get("url", ""),
            "kind": settings.get("kind", "openai"),
            "enabled": bool(settings.get("enabled", True)),
            # Whether a key is set, never the key: this dict is what the UI reads.
            "needs_key": bool(settings.get("api_key")),
            "seats": sorted(role for role, connection in seats.items()
                            if connection == name),
            "leader": name == leader,
        })
    return out


def member(name: str) -> dict:
    """One player by name; an unknown name raises rather than guessing."""
    for entry in members():
        if entry["name"] == name:
            return entry
    raise KeyError(f"no connection named {name!r}")


def leader() -> dict:
    """The player that runs the builds, or `{}` if it is missing or switched off."""
    name = _settings().get("leader", "")
    if not name:
        return {}
    try:
        entry = member(name)
    except KeyError:
        return {}
    return entry if entry["enabled"] else {}


def set_leader(name: str) -> dict:
    entry = member(name)
    if not entry["enabled"]:
        raise KeyError(f"{name!r} is switched off; switch it on before making it "
                       f"the leader")
    config.save({"band": {"leader": name}})
    return summary()


# ── adding, seating, switching off ─────────────────────────────────────────

def add(name: str, model: str, url: str, kind: str = "openai",
        timeout_s: float = 600, max_tokens: int = 6000,
        temperature: float = 0.2, think: bool = False,
        num_ctx: int = 0, enabled: bool = True,
        api_key: str = "") -> dict:
    """Add a player: a named connection, on by default, seated nowhere.

    `kind` is the wire protocol, not the vendor: `ollama` uses the native chat
    API (the only one that also returns the thinking text), anything else is
    treated as OpenAI-compatible.

    `api_key` is optional on purpose. A local server (Ollama, LM Studio,
    llama.cpp, vLLM) needs no key, so an empty one sends no `Authorization`
    header at all; a hosted free tier that issues a key just fills this in.
    """
    name = (name or "").strip()
    kind = (kind or "openai").lower()
    if not NAME_RE.match(name):
        raise KeyError("a player's name is letters, digits, dot, dash or "
                       "underscore (and cannot start with punctuation)")
    # A relay player is a person answering a prompt by hand, so it has no
    # endpoint at all. Every socket player needs one.
    if kind != "relay" and not url.strip().lower().startswith(("http://", "https://")):
        raise KeyError("a player needs an http(s) url, e.g. "
                       "http://127.0.0.1:11434/v1 (or kind=relay for a seat "
                       "you answer by hand)")
    if not (model or "").strip():
        raise KeyError("a player needs a model name")
    if name in config.connections():
        raise KeyError(f"a connection named {name!r} already exists")
    config.save({name: {
        "kind": kind,
        "url": url.strip().rstrip("/"),
        "model": model.strip(),
        "timeout_s": float(timeout_s),
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "think": bool(think),
        "num_ctx": int(num_ctx),
        "attempts": 3,
        "enabled": bool(enabled),
        "api_key": (api_key or "").strip(),
    }})
    return summary()


def probe(name: str, timeout_s: float = 5) -> dict:
    """Ask a player whether it answers and whether it serves the model asked for.

    Both wire protocols are tried, so one button works for a raw Ollama and for
    any OpenAI-compatible server. This is the honest check behind "connected":
    a URL in the config proves nothing about a model being loaded.
    """
    entry = member(name)
    if str(entry.get("kind") or "").lower() == "relay":
        return {"name": name, "up": True, "served": True, "models": [],
                "error": "manual seat: prompts are answered by hand "
                         "(python3 -m trainapp.relay --pending)"}
    url = str(entry.get("url") or "").rstrip("/")
    settings = config.load().get(name) or {}
    key = str(settings.get("api_key") or "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    base = re.sub(r"/v1$", "", url)
    openai_url = url if url.endswith("/v1") else url + "/v1"
    last = "unreachable"
    for target in (base + "/api/tags", openai_url + "/models"):
        try:
            request = urllib.request.Request(target, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as err:
            last = f"{target}: {err}"
            continue
        # Ollama lists under `models`, an OpenAI-compatible server under `data`.
        entries = payload.get("models") or payload.get("data") or []
        models = [str(m.get("name") or m.get("id") or "") for m in entries
                  if isinstance(m, dict)]
        if not models:
            # This URL answered, but not with a model list: it is the other wire
            # protocol. Try the next one instead of claiming the model is absent.
            last = f"{target}: no model list"
            continue
        wanted = str(entry.get("model") or "")
        served = bool(models) and (wanted in models or any(
            m and wanted.startswith(m.split(":")[0]) for m in models))
        return {"name": name, "up": True, "served": served,
                "models": models[:40], "error": ""}
    return {"name": name, "up": False, "served": False, "models": [],
            "error": str(last)[:240]}


def toggle(name: str, enabled: bool = True) -> dict:
    """Switch a player on or off. A leader or a seated player is refused."""
    entry = member(name)
    if not enabled and entry["leader"]:
        raise KeyError(f"{name!r} leads the band; make another connection the "
                       f"leader first")
    if not enabled and entry["seats"]:
        raise KeyError(f"{name!r} holds the {', '.join(entry['seats'])} seat; "
                       f"move it to another player before switching it off")
    config.save({name: {"enabled": bool(enabled)}})
    return summary()


def seat(role: str, name: str) -> dict:
    """Give a seat to a player. A seat takes one player, so this moves it."""
    entry = member(name)
    if not entry["enabled"]:
        raise KeyError(f"{name!r} is switched off; switch it on before seating it")
    try:
        config.assign(role, name)
    except KeyError as err:
        raise KeyError(str(err)) from err
    return summary()


def remove(name: str) -> dict:
    """Hang up a player the user added. Leader and seated players are refused."""
    entry = member(name)
    if entry["leader"]:
        raise KeyError(f"{name!r} leads the band; make another connection the "
                       f"leader first")
    if entry["seats"]:
        raise KeyError(f"{name!r} holds the {', '.join(entry['seats'])} seat; "
                       f"give it to another player first")
    config.forget(name)
    return summary()


# ── copying every build ────────────────────────────────────────────────────

def copy_builds() -> bool:
    """Whether a build is copied whole. On by default; one switch turns it off."""
    return _settings().get("copy_builds", True) is not False


def set_copy_builds(flag: bool) -> dict:
    config.save({"band": {"copy_builds": bool(flag)}})
    return summary()


def builds_root() -> Path:
    return config.data_dir() / "builds"


def _relative(path: str) -> str:
    """A file path that stays inside the copy, or "" if it does not."""
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        return ""
    return "/".join(parts)


def _readable(label: str, reasoning: str, reply: str) -> str:
    blocks = [f"# {label}"]
    if reasoning:
        blocks.append(f"## reasoning\n\n{reasoning}")
    blocks.append(f"## reply\n\n{reply or '(nothing)'}")
    return "\n\n".join(blocks) + "\n"


def copy_build(record: dict, root: Path | None = None) -> dict:
    """Write one build out whole: every reply, every file, every attempt.

    The pool stores what is needed to train on; this stores what is needed to
    understand. Nothing is truncated — a reply that produced no files is as
    much evidence as a reply that produced ten, and a build that failed twice
    before passing keeps both failed sets.
    """
    from .builder import label_for  # builder imports this module: keep it local

    stamp = re.sub(r"[^0-9A-Za-z]+", "", str(record.get("at") or "")) or \
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    task = record.get("task") or {}
    slug = re.sub(r"[^a-z0-9]+", "-", str(task.get("id") or "task").lower())
    slug = slug.strip("-")[:60] or "task"
    base = (root or builds_root()) / stamp / f"{label_for(record.get('model', ''))}--{slug}"
    target, seen = base, 1
    while target.exists():
        seen += 1
        target = base.with_name(f"{base.name}-{seen}")
    target.mkdir(parents=True, exist_ok=True)

    final = record.get("files") or []
    written = 0
    total = 0
    for entry in final:
        rel = _relative(entry.get("path", ""))
        if not rel:
            continue
        path = target / "files" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        content = str(entry.get("content") or "")
        path.write_text(content, encoding="utf-8")
        written += 1
        total += len(content.encode("utf-8"))

    attempts = record.get("attempts") or []
    for attempt in attempts:
        number = int(attempt.get("n") or 0)
        for lane in ("plan", "files"):
            reply = attempt.get(f"{lane}_reply")
            reasoning = attempt.get(f"{lane}_reasoning") or ""
            if reply is None and not reasoning:
                continue
            (target / f"attempt-{number}-{lane}.md").write_text(
                _readable(lane, reasoning, reply or ""), encoding="utf-8")
        # Keep the failed set that differs from the one that finally built.
        if attempt.get("files") and attempt.get("files") != final:
            for entry in attempt["files"]:
                rel = _relative(entry.get("path", ""))
                if not rel:
                    continue
                path = target / f"attempt-{number}" / "files" / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                content = str(entry.get("content") or "")
                path.write_text(content, encoding="utf-8")
                written += 1
                total += len(content.encode("utf-8"))

    build = record.get("build") or {}
    (target / "build.txt").write_text("\n".join([
        f"command: {build.get('command', '')}",
        f"exit: {build.get('exit_code')}",
        f"ok: {build.get('ok')}",
        f"error: {build.get('error', '')}",
        "",
        build.get("stdout", "") or "(no output)",
    ]) + "\n", encoding="utf-8")
    (target / "record.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"path": str(target), "files": written, "bytes": total,
            "attempts": len(attempts)}


def summary() -> dict:
    """Everything the UI needs to draw the band in one call."""
    return {"leader": leader(), "members": members(), "seats": config.roles(),
            "copy_builds": copy_builds(), "path": str(builds_root())}
