"""relay — a seat a person fills, for models that only exist inside a chat window.

Some models cannot be connected at all: they have no endpoint, no key and no
API — Freebuff, the ChatGPT/Claude/Gemini web apps, anything you reach by
typing into a page. Hooking their private backend would be brittle and against
their terms, so this module does the honest version instead.

A relay player is a band player with `kind: "relay"` and no URL. When a seat
asks it something, the question is written to `data/relay/outbox/<id>.json` and
the call blocks. You copy the prompt into whichever chat window you like, paste
the answer back, and the seat gets exactly the text the model returned:

    python3 -m trainapp.relay --pending        # what is waiting, with the text
    python3 -m trainapp.relay --show <id>      # the whole prompt to paste
    python3 -m trainapp.relay --answer <id> --file reply.txt
    python3 -m trainapp.relay --answer <id> --text "..."   (or stdin)

Nothing is invented on the way through: the reply is returned verbatim, so a
JSON seat still needs the model to return JSON, and the harness still runs the
toolchain afterwards. A relay seat is slower than a socket and just as strict —
which is the point: it lets a model with no API take part without pretending it
has one.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config

DEFAULT_TIMEOUT_S = 3600.0
POLL_S = 1.0


class RelayTimeout(RuntimeError):
    """Nobody answered the prompt before the deadline."""


class RelayError(RuntimeError):
    """The request or the reply could not be read or written."""


def root() -> Path:
    path = config.data_dir() / "relay"
    (path / "outbox").mkdir(parents=True, exist_ok=True)
    (path / "inbox").mkdir(parents=True, exist_ok=True)
    (path / "archive").mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:4]


def _safe_id(name: str) -> str:
    if not re.fullmatch(r"[0-9A-Za-z._-]{1,64}", name or ""):
        raise RelayError(f"not a relay id: {name!r}")
    return name


def _write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise RelayError(f"cannot read {path.name}: {err}") from err
    return data if isinstance(data, dict) else {}


# ── the two sides of a hand-off ────────────────────────────────────────────

def submit(system: str, user: str, *, json_object: bool = False,
           player: str = "", seat: str = "") -> dict:
    """Write one prompt to the outbox and return it, id included."""
    request_id = _new_id()
    payload = {"id": request_id, "created_at": _now(), "player": player,
               "seat": seat, "json": bool(json_object),
               "system": system or "", "user": user or ""}
    _write(root() / "outbox" / f"{request_id}.json", payload)
    return payload


def prompt_text(request: dict) -> str:
    """Exactly what to paste into a chat window, system prompt first."""
    parts = []
    if request.get("system"):
        parts.append(f"[system]\n{request['system']}")
    parts.append(f"[task]\n{request.get('user') or ''}")
    if request.get("json"):
        parts.append("[answer with JSON only]")
    return "\n\n".join(parts)


def pending() -> list[dict]:
    """Requests still waiting for a person, oldest first.

    A request whose answer is already in the inbox is *not* pending: the reply
    is written and the seat will collect it on its next poll. Listing it again
    is how a hand-off loop answers the same prompt twice.
    """
    inbox = root() / "inbox"
    out: list[dict] = []
    for path in sorted((root() / "outbox").glob("*.json")):
        if (inbox / path.name).exists():
            continue
        try:
            out.append(_read(path))
        except RelayError:
            continue
    return out


def show(request_id: str) -> dict:
    path = root() / "outbox" / f"{_safe_id(request_id)}.json"
    if not path.is_file():
        raise RelayError(f"no pending request {request_id!r}")
    return _read(path)


def answer(request_id: str, content: str) -> dict:
    """Hand a reply back. The seat wakes up on the next poll."""
    request = show(request_id)
    reply = {"id": request["id"], "answered_at": _now(),
             "content": content or "", "reasoning": ""}
    _write(root() / "inbox" / f"{request['id']}.json", reply)
    return {**request, **reply}


def wait(request_id: str, timeout_s: float = DEFAULT_TIMEOUT_S,
         poll_s: float = POLL_S) -> dict:
    """Block until the reply lands, then archive both halves of the exchange."""
    inbox = root() / "inbox" / f"{_safe_id(request_id)}.json"
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    while True:
        if inbox.is_file():
            reply = _read(inbox)
            _archive(request_id, reply)
            return reply
        if time.monotonic() >= deadline:
            raise RelayTimeout(
                f"no answer to relay request {request_id} within "
                f"{timeout_s:g}s — run `python3 -m trainapp.relay --pending`")
        time.sleep(max(0.01, float(poll_s)))


def _archive(request_id: str, reply: dict) -> None:
    """Keep the exchange, but out of the way of the next one."""
    folder = root() / "archive"
    (folder / "inbox").mkdir(parents=True, exist_ok=True)
    (folder / "outbox").mkdir(parents=True, exist_ok=True)
    for source, target in (
            (root() / "inbox" / f"{request_id}.json", folder / "inbox" / f"{request_id}.json"),
            (root() / "outbox" / f"{request_id}.json", folder / "outbox" / f"{request_id}.json")):
        if source.is_file():
            os.replace(source, target)


# ── the seat itself ────────────────────────────────────────────────────────

class RelaySeat:
    """The same `ask` surface as the socket clients, answered by a person.

    Blocking on purpose: a run that is waiting for a paste should sit still, not
    guess. The timeout exists so an abandoned run fails with the command that
    would have unblocked it instead of hanging a thread forever.
    """

    def __init__(self, name: str = "relay", timeout_s: float = DEFAULT_TIMEOUT_S,
                 poll_s: float = POLL_S) -> None:
        self.model = name or "relay"
        self.name = self.model
        self.timeout_s = float(timeout_s or DEFAULT_TIMEOUT_S)
        self.poll_s = float(poll_s or POLL_S)

    def ask(self, system: str, user: str, json_object: bool = False,
            temperature: float | None = None) -> dict:
        started = time.monotonic()
        request = submit(system, user, json_object=json_object, player=self.model)
        reply = wait(request["id"], timeout_s=self.timeout_s, poll_s=self.poll_s)
        return {"content": reply.get("content") or "",
                "reasoning": reply.get("reasoning") or "",
                "model": self.model, "usage": {},
                "seconds": round(time.monotonic() - started, 2)}

    def close(self) -> None:
        return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Answer a relay seat by hand (for models with no API)")
    parser.add_argument("--pending", action="store_true",
                        help="list the prompts waiting for an answer")
    parser.add_argument("--show", default="", help="print one prompt to paste")
    parser.add_argument("--answer", default="", help="the request id to answer")
    parser.add_argument("--file", default="", help="read the reply from this file")
    parser.add_argument("--text", default="", help="the reply itself")
    args = parser.parse_args(argv)

    if args.pending:
        waiting = pending()
        if not waiting:
            print("no relay prompt is waiting")
            return 0
        for request in waiting:
            print(f"{request['id']}  {request.get('created_at', '')}  "
                  f"{request.get('player') or 'relay'}  "
                  f"{len(request.get('user') or '')} chars")
        return 0
    if args.show:
        print(prompt_text(show(args.show)))
        return 0
    if args.answer:
        if args.file:
            content = Path(args.file).expanduser().read_text(encoding="utf-8")
        elif args.text:
            content = args.text
        else:
            import sys
            content = sys.stdin.read()
        answered = answer(args.answer, content)
        print(f"delivered {answered['id']} ({len(answered['content'])} chars)")
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
