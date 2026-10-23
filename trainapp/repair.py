"""repair — the harness's only intelligence loop.

The harness runs the node, and if it fails it hands the LLM exactly what an
operator would: the file, the argv that was executed, the platform, the exit
code and the output. It does not classify the language's errors, and it does
not know the language's semantics. The model fixes the file; the harness proves
the fix by running the same argv again.

A fix that passes is captured as training data. A fix that does not pass is
discarded and the original file is restored — neither the node nor the dataset
keeps an unverified guess.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from . import capture, config
from .execution import PLATFORM_LABEL, RunResult, detect_language, run_node

FENCE_RE = re.compile(r"```[A-Za-z0-9_+-]*\s*\n(.*?)```", re.DOTALL)


class LLMError(RuntimeError):
    """The model could not be reached or returned nothing usable."""


class Completer(Protocol):
    def complete(self, prompt: str) -> str: ...


class OllamaClient:
    """Minimal Ollama client, so the app needs no SDK and no network service."""

    def __init__(self, model: str | None = None, url: str | None = None,
                 timeout_s: float | None = None, num_ctx: int | None = None,
                 temperature: float | None = None) -> None:
        settings = config.load()["llm"]
        self.model = model or settings["model"]
        self.url = (url or settings["url"]).rstrip("/")
        self.timeout_s = timeout_s or settings["timeout_s"]
        self.num_ctx = num_ctx or settings.get("num_ctx", 8192)
        self.temperature = 0.2 if temperature is None else temperature

    def complete(self, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}/api/generate", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise LLMError(f"LLM unreachable at {self.url}: {err}") from err
        except json.JSONDecodeError as err:
            raise LLMError(f"LLM returned non-JSON: {err}") from err
        text = (payload.get("response") or "").strip()
        if not text:
            raise LLMError("LLM returned an empty response")
        return text


def extract_code(reply: str) -> str:
    """The corrected file from a model reply: largest fenced block, else the text."""
    blocks = [m.group(1).strip() for m in FENCE_RE.finditer(reply or "")]
    if blocks:
        return _tidy(max(blocks, key=len))
    return _tidy(reply or "")


def _tidy(text: str) -> str:
    lines = text.replace("\r\n", "\n").strip().splitlines()
    # Strip a bare opening/closing fence the regex could not pair.
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip() + "\n"


def build_prompt(*, filename: str, language: str, command: str, exit_code: int | None,
                 output: str, code: str, goal: str, attempt: int,
                 max_attempts: int) -> str:
    context = [
        f"File: {filename}",
        f"Language: {language}",
        f"Platform: {PLATFORM_LABEL}",
        f"Command: {command}",
        f"Exit code: {exit_code}",
        "Output:",
        (output or "(no output)")[:12_000],
    ]
    if goal.strip():
        context.insert(0, f"Goal: {goal.strip()}")
    return (
        "You are fixing one file in a project. The harness ran it and it failed.\n"
        + "\n".join(context)
        + f"\n\nAttempt {attempt} of {max_attempts}. Here is the file:\n"
        + "```\n" + code.strip() + "\n```\n\n"
        + "Fix the file so the command above succeeds. Return only the complete "
        "corrected file — no markdown fence, no explanation, no diff."
    )


def _write_run_log(payload: dict) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = config.runs_dir() / f"fix-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def fix_node(path: str | Path, *, goal: str = "", max_attempts: int = 3,
             llm: Completer | None = None, timeout_s: float = 60) -> dict:
    """Run -> fail -> ask the LLM to fix -> run again, up to `max_attempts`."""
    file_path = Path(path).resolve()
    if not file_path.is_file():
        return {"status": "error", "error": f"no such file: {file_path}"}

    language = detect_language(file_path)
    if not language:
        return {"status": "error",
                "error": f"no execution schema for {file_path.name!r}"}

    original = file_path.read_text(encoding="utf-8")
    first = run_node(file_path, language, timeout_s=timeout_s)
    if first.ok:
        return {
            "status": "already_passing",
            "language": language,
            "run": first.as_dict(),
            "attempts": [],
            "captured": False,
            "captured_reason": "nothing to fix",
        }

    completer = llm or OllamaClient()
    attempts: list[dict] = []
    last: RunResult = first
    current = original
    captured, capture_reason = False, "not verified"

    for attempt in range(1, max_attempts + 1):
        prompt = build_prompt(
            filename=file_path.name, language=language, command=last.command,
            exit_code=last.exit_code, output=last.output, code=current,
            goal=goal, attempt=attempt, max_attempts=max_attempts,
        )
        started = time.monotonic()
        try:
            reply = completer.complete(prompt)
        except LLMError as err:
            attempts.append({"attempt": attempt, "ok": False, "phase": "llm",
                             "error": str(err), "llm_ms": 0})
            capture_reason = f"LLM failed: {err}"
            break
        llm_ms = int((time.monotonic() - started) * 1000)

        candidate = extract_code(reply)
        changed = candidate.strip() != current.strip()
        if changed:
            file_path.write_text(candidate, encoding="utf-8")
            current = candidate

        result = run_node(file_path, language, timeout_s=timeout_s) if changed else last
        attempts.append({
            "attempt": attempt,
            "ok": bool(changed and result.ok),
            "changed": changed,
            "exit_code": result.exit_code,
            "command": result.command,
            "error": "" if result.ok else (result.error or ""),
            "llm_ms": llm_ms,
        })
        last = result
        if changed and result.ok:
            row = capture.make_fix_row(
                language=language,
                filename=file_path.name,
                platform=PLATFORM_LABEL,
                command=first.command,
                exit_code=first.exit_code,
                error_output=first.output,
                before=original,
                after=current,
                goal=goal,
                attempts=attempt,
            )
            captured, capture_reason = capture.append_row(row)
            break

    status = "fixed" if last.ok and current.strip() != original.strip() else "failed"
    payload = {
        "status": status,
        "file": str(file_path),
        "language": language,
        "goal": goal,
        "platform": PLATFORM_LABEL,
        "first_run": first.as_dict(),
        "final_run": last.as_dict(),
        "attempts": attempts,
        "captured": captured,
        "captured_reason": capture_reason,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    payload["log"] = str(_write_run_log(payload))
    if status == "failed":
        # An unverified guess never stays in the node: restore what the user had.
        file_path.write_text(original, encoding="utf-8")
    return payload
