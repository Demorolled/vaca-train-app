"""judge — the larger model that ranks small builds.

The judge never sees a candidate in isolation. It gets the task, the reference
(confirmed) implementation, and two candidates with their measured bytes and
runtime, and must return a structured verdict. That keeps it anchored to
something real instead of rewarding confident prose.

Deterministic checks run first and are final:

  * a candidate that failed the toolchain loses to one that passed, no model call
  * identical code is a tie
  * two failures are a no-contest

Only the subjective slice (which correct build is smaller / faster / more
versatile) is left to the model.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import config

FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)
JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _chat(messages: list[dict], *, url: str | None = None, model: str | None = None,
          timeout_s: float | None = None, max_tokens: int | None = None,
          temperature: float | None = None) -> str:
    settings = config.connection("judge")
    base = (url or settings["url"]).rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    body = json.dumps({
        "model": model or settings["model"],
        "messages": messages,
        "max_tokens": max_tokens or settings["max_tokens"],
        "temperature": settings["temperature"] if temperature is None else temperature,
        "stream": False,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = str(settings.get("api_key") or "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(
        base + "/chat/completions", data=body,
        headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout_s or settings["timeout_s"]) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "") or ""


def parse_verdict(text: str) -> dict | None:
    """The verdict JSON from a reply that may be fenced or chatty."""
    if not text:
        return None
    candidates = FENCE_RE.findall(text) or [text]
    for chunk in candidates:
        match = JSON_RE.search(chunk)
        if not match:
            continue
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and str(data.get("winner", "")).upper() in ("A", "B", "TIE"):
            return data
    # Fallback: a bare `WINNER: A` line still counts, but only with a letter.
    match = re.search(r"winner\s*[:\-]\s*(A|B|tie)\b", text, re.I)
    if match:
        return {"winner": match.group(1), "reason": "parsed from text",
                "scores": {}, "dimensions": {}}
    return None


def _verdict_prompt(task: dict, reference: str, a: dict, b: dict) -> list[dict]:
    system = (
        "You are a senior code reviewer judging two implementations of the same "
        "task. Correctness comes first: an incorrect build always loses. Among "
        "correct builds, prefer the one that is SMALLER (fewer bytes/tokens), "
        "FASTER (lower measured runtime), and MORE VERSATILE (clear structure, "
        "no needless dependencies, easy to reuse), in that priority for "
        "correctness, then weight size, speed and versatility together.\n"
        "Answer with ONE JSON object and nothing else:\n"
        '{"winner":"A"|"B"|"tie","correctness":"A"|"B"|"tie",'
        '"smaller":"A"|"B"|"tie","faster":"A"|"B"|"tie",'
        '"versatility":"A"|"B"|"tie","reason":"one sentence"}'
    )
    user = (
        f"TASK: {task.get('title','')}\n"
        f"LANGUAGE: {task.get('language','')}\n"
        f"WHAT IT MUST DO: {task.get('description','')}\n\n"
        "REFERENCE (confirmed working):\n```\n" + reference[:4000] + "\n```\n\n"
        f"CANDIDATE A ({a.get('style','?')}, {a.get('bytes',0)} bytes, "
        f"{a.get('runtime_ms',0)} ms, valid={a.get('valid')}):\n```\n"
        + (a.get('code') or '')[:4000] + "\n```\n\n"
        f"CANDIDATE B ({b.get('style','?')}, {b.get('bytes',0)} bytes, "
        f"{b.get('runtime_ms',0)} ms, valid={b.get('valid')}):\n```\n"
        + (b.get('code') or '')[:4000] + "\n```\n\n"
        f"Measured stdout match vs reference: A={a.get('stdout_match')} "
        f"B={b.get('stdout_match')}."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def compare(task: dict, reference: str, a: dict, b: dict) -> dict:
    """Deterministic gate, then the LLM verdict. Never invents a winner."""
    if not a.get("valid") and not b.get("valid"):
        return {"winner": "tie", "reason": "neither candidate passed the toolchain",
                "source": "deterministic", "scores": {}, "dimensions": {}}
    if a.get("valid") and not b.get("valid"):
        return {"winner": "A", "reason": "B failed the toolchain",
                "source": "deterministic", "scores": {}, "dimensions": {}}
    if b.get("valid") and not a.get("valid"):
        return {"winner": "B", "reason": "A failed the toolchain",
                "source": "deterministic", "scores": {}, "dimensions": {}}
    if (a.get("code") or "").strip() == (b.get("code") or "").strip():
        return {"winner": "tie", "reason": "identical code",
                "source": "deterministic", "scores": {}, "dimensions": {}}

    try:
        raw = _chat(_verdict_prompt(task, reference, a, b))
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        return {"winner": "", "reason": "", "error": f"judge unreachable: {err}"[:300],
                "source": "llm", "scores": {}, "dimensions": {}}

    parsed = parse_verdict(raw)
    if not parsed:
        return {"winner": "", "reason": "unparseable verdict", "raw": raw[:800],
                "source": "llm", "scores": {}, "dimensions": {}}
    winner = str(parsed.get("winner", "")).upper()
    dimensions = {k: str(parsed.get(k, "")).upper()
                  for k in ("correctness", "smaller", "faster", "versatility")}
    return {"winner": winner, "reason": str(parsed.get("reason", ""))[:500],
            "source": "llm", "scores": parsed.get("scores") or {},
            "dimensions": dimensions, "raw": raw[:800]}


def health() -> dict:
    """Is the judge model actually being served?"""
    settings = config.connection("judge")
    base = settings["url"].rstrip("/")
    root = base[:-3] if base.endswith("/v1") else base
    try:
        with urllib.request.urlopen(root + "/api/tags", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        names = [m.get("name", "") for m in payload.get("models", [])]
        return {"up": True, "model": settings["model"],
                "served": settings["model"] in names, "models": names[:20]}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as err:
        return {"up": False, "model": settings["model"], "error": str(err)[:300]}
