"""builder — the second connection does the work, and everything is captured.

VACA has two models. The first (`llm`) answers and draws nodes; this module uses
the second (`builder`, a larger model over the tailnet) to do the actual build:
plan the app, write every file, then repair what the toolchain rejects. The
small model is not asked to do any of it.

What makes the run worth keeping is the capture. After each app, the record
holds the brief, the plan, the model's own reasoning text where the server
exposes it, every reply, the parsed files, and the build/run result — labelled
by model. A second model on the same series produces a second pool, and the two
pools are comparable because the briefs are identical.

Nothing here is a training row yet. The pool is a corpus: the plans are the
scaffolding conventions, the file sets are templates, the failures are the
classes of mistake. `trainapp.buildfix` and `scaffoldsft` read *derived* rows;
this reads nothing back into the library, so a builder cannot pollute the
held-out pool by writing into it.

    python -m trainapp.builder --apps 5 --languages go,python
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import band, config, execution, scaffold

FILE_RE = re.compile(r"^\s*(?:#+\s*)?FILE:\s*`?([^\s`]+)`?\s*$", re.M)
# Models format the same information three ways: `FILE: x`, `### x.py`, `**x.py**`.
HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*|\*\*|`)?([\w./-]+\.(?:py|go|ts|tsx|js|jsx|java|cs|c|cc|cpp|h|rs|rb|php|kt|swift|json|md|txt|toml|yaml|yml|mod|sum))\s*(?:\*\*|`)?\s*:?\s*$",
    re.M)
FENCE_RE = re.compile(r"```[a-zA-Z0-9_+.#-]*\s*\n(.*?)```", re.DOTALL)
THINK_RE = re.compile(r"^\s*<think(?:ing)?>(.*?)</think(?:ing)?>\s*", re.DOTALL)

PLAN_SYSTEM = (
    "You are the builder in a multi-model system. You plan and you write code; "
    "a smaller model handles conversation and never touches this work.")
PLAN_ASK = """Build this app from scratch.

Brief: {brief}
Language: {language}
Working directory is empty; every file you name must be created.
{conventions}
Reply with JSON only:
{{"plan": "how you will build it, in your own words",
  "files": [{{"path": "relative/path", "purpose": "one line"}}],
  "entry": "the file that starts the program, or \\"\\" if it has none",
  "run": "the command a user would type, or \\"\\"",
  "expected_stdout": "what a correct run prints, if it prints"}}"""

FILES_SYSTEM = (
    "You write complete, buildable files. No placeholders, no TODO, no ellipses.")
FILES_ASK = """Plan for the app:
{plan}

Write ONLY {language} files. If the brief names another language, ignore that:
the language for this task is {language} and every source file must be {language}.

Write every file in full. Format exactly:

FILE: path/to/file
```{language}
<complete contents>
```

Then nothing else. Every path in the plan must appear, and the set must build
with: {build_hint}"""

REPAIR_NOTE = """
The previous attempt failed the toolchain. Fix it.

{feedback}

Return the complete set again, in the same FILE: format."""


class BuilderError(RuntimeError):
    """The second connection could not be reached or returned nothing usable."""


def settings() -> dict:
    """The connection the `builder` role is assigned to."""
    return config.connection("builder")


def label_for(model: str) -> str:
    """A filesystem-safe label for a model, so pools of two models stay apart."""
    return re.sub(r"[^a-z0-9.]+", "-", (model or "unknown").lower()).strip("-") or "unknown"


class Chat:
    """OpenAI-compatible chat that keeps more than the answer.

    Reasoning is captured when the server exposes it (`reasoning_content`,
    `reasoning`, `thinking`), and otherwise split out of a leading `<think>`
    block. It is stored as evidence, never trained on directly: a chain of
    thought cannot be checked, but the plan it produced can.
    """

    def __init__(self, url: str = "", model: str = "", timeout_s: float | None = None,
                 max_tokens: int | None = None,
                 temperature: float | None = None,
                 think: bool | None = None,
                 num_ctx: int | None = None,
                 kind: str | None = None,
                 api_key: str = "") -> None:
        cfg = settings()
        self.url = (url or cfg.get("url", "")).rstrip("/")
        self.model = model or cfg.get("model", "")
        self.timeout_s = float(timeout_s or cfg.get("timeout_s", 600))
        self.max_tokens = int(max_tokens or cfg.get("max_tokens", 6000))
        self.temperature = float(cfg.get("temperature", 0.2)
                                 if temperature is None else temperature)
        # Native chat is the only path that returns the thinking text; the
        # OpenAI-compatible one returns prose only, and a reasoning pool built
        # from it is missing the half that explains the design.
        # A band player carries its own wire protocol: the native chat API is
        # the only one that also returns the thinking text.
        self.kind = ((kind or cfg.get("kind") or "openai")).lower()
        # `think` is an Ollama option, honoured by reasoning models only; a
        # coding model returns nothing for it and the plan phase still records
        # the design thinking in plain text.
        self.think = bool(cfg.get("think", False) if think is None else think)
        # A local builder needs a context big enough for the plan, the copied
        # scaffold section and the whole file set; Ollama's default truncates
        # the ask silently. 0 leaves the server's own default alone.
        self.num_ctx = int(cfg.get("num_ctx") or 0 if num_ctx is None else num_ctx)
        # Empty for every local server, which needs no auth at all.
        self.api_key = api_key or str(cfg.get("api_key") or "")

    def ask(self, system: str, user: str, json_object: bool = False,
            temperature: float | None = None) -> dict:
        """One turn. `json_object` asks the server for JSON, not prose.

        Both wire protocols can do it: Ollama takes `format: json`, an
        OpenAI-compatible server takes `response_format`. A seat that must
        return a machine-readable verdict passes it, so a fence or a chatty
        preamble is refused by the server instead of parsed out afterwards.
        """
        heat = self.temperature if temperature is None else temperature
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        if self.kind == "ollama":
            base = re.sub(r"/v1$", "", self.url)
            url = base + "/api/chat"
            options: dict = {"temperature": heat,
                             "num_predict": self.max_tokens}
            if self.num_ctx:
                options["num_ctx"] = self.num_ctx
            body: dict = {
                "model": self.model, "messages": messages, "stream": False,
                "think": self.think, "options": options,
            }
            if json_object:
                body["format"] = "json"
        else:
            url = (self.url if self.url.endswith("/v1") else self.url + "/v1") \
                + "/chat/completions"
            body = {
                "model": self.model, "messages": messages,
                "max_tokens": self.max_tokens, "temperature": heat,
                "stream": False,
            }
            if json_object:
                body["response_format"] = {"type": "json_object"}
        body = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            url, data=body, headers=headers, method="POST")
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise BuilderError(f"builder unreachable at {self.url}: {err}") from err
        except json.JSONDecodeError as err:
            raise BuilderError(f"builder returned non-JSON: {err}") from err
        if self.kind == "ollama":
            message = payload.get("message") or {}
            usage = {"prompt_tokens": payload.get("prompt_eval_count"),
                     "completion_tokens": payload.get("eval_count")}
        else:
            message = ((payload.get("choices") or [{}])[0].get("message") or {})
            usage = payload.get("usage") or {}
        content = message.get("content") or ""
        reasoning = (message.get("reasoning_content") or message.get("reasoning")
                     or message.get("thinking") or "")
        if not reasoning:
            match = THINK_RE.match(content)
            if match:
                reasoning, content = match.group(1).strip(), content[match.end():]
        return {"content": content, "reasoning": reasoning,
                "model": payload.get("model") or self.model,
                "usage": usage, "seconds": round(time.monotonic() - started, 2)}


def parse_plan(reply: str) -> dict:
    """The plan JSON from a reply that may be fenced or chatty."""
    text = (reply or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def clean_block(text: str) -> str:
    """A file's contents without the fences a model wrapped them in."""
    lines = (text or "").replace("\r\n", "\n").strip("\n").splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip("\n") + "\n"


def parse_files(reply: str, language: str, plan: list[dict] | None = None) -> list[dict]:
    """The file set from a reply, whatever marker style the model chose.

    `FILE: path` is the shape asked for, but a 35B reasoning model answered
    with `### main.py` headings and another wrapped the whole answer in one
    fence — both are the same information, and rejecting them taught nothing.
    """
    text = reply or ""
    out: list[dict] = []
    matches = list(FILE_RE.finditer(text))
    for index, match in enumerate(matches):
        body = text[match.end():matches[index + 1].start() if index + 1 < len(matches)
                    else len(text)]
        fenced = FENCE_RE.search(body)
        out.append({"path": match.group(1).strip(),
                    "content": clean_block(fenced.group(1) if fenced else body)})
    if not out:
        markers = list(HEADING_RE.finditer(text))
        for index, match in enumerate(markers):
            body = text[match.end():markers[index + 1].start()
                        if index + 1 < len(markers) else len(text)]
            fenced = FENCE_RE.search(body)
            if fenced:
                out.append({"path": match.group(1).strip(),
                            "content": clean_block(fenced.group(1))})
    if out:
        return out
    blocks = [m.group(1) for m in FENCE_RE.finditer(text)]
    if blocks and plan:
        return [{"path": plan[0].get("path", ""),
                 "content": clean_block(blocks[0])}]
    return []


BUILD_HINT = {
    "python": "python3 <entry>",
    "go": "go build ./... && go run <entry>",
    "typescript": "tsc --noEmit (types are checked; the entry runs with tsx)",
    "javascript": "node <entry>",
    "java": "javac *.java && java <MainClass>",
    "c": "cc *.c -o app && ./app",
    "cpp": "c++ *.cpp -o app && ./app",
    "csharp": "dotnet build",
    "rust": "cargo build / rustc <entry>",
    "ruby": "ruby <entry>",
    "php": "php <entry>",
    "kotlin": "kotlinc *.kt -include-runtime -d app.jar",
    "swift": "swiftc *.swift -o app",
}


def build_hint(language: str) -> str:
    """What the toolchain in this repo actually does to a set of this language."""
    return BUILD_HINT.get(language) or f"the {language} toolchain in this repo"


def matches_language(files: list[dict], language: str) -> bool:
    """At least one source file is in the lane the brief asked for.

    The 30B wrote a C# lexer for a Python task and then failed the Python build
    three times; the toolchain's "SyntaxError: invalid syntax" on `using System;`
    was honest but useless as feedback. Catching the mismatch here says what to
    do about it.
    """
    toolchain = execution.TOOLCHAINS.get(language)
    if not toolchain or not files:
        return bool(files)
    return any(str(f.get("path", "")).endswith(tuple(toolchain.extensions))
               for f in files)


def args_from_run(run_cmd: str, entry: str) -> list[str]:
    """The arguments the plan itself says to invoke with.

    A CLI that prints `Usage: main.py <expression>` and exits 2 has not failed to
    build: it was run with no input. The builder states its invocation in the
    plan, so the harness uses it instead of guessing whitespace.
    """
    import shlex

    try:
        parts = shlex.split(run_cmd or "")
    except ValueError:
        return []
    if entry and entry in parts:
        return parts[parts.index(entry) + 1:]
    return []


def _run(files: list[dict], language: str, entry: str, timeout_s: float,
         args: list[str] | None = None):
    return execution.run_files(files, language, entry=entry, timeout_s=timeout_s,
                               args=args)


def _sha(files: list[dict]) -> str:
    blob = json.dumps(sorted((f["path"], f["content"]) for f in files))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_app(spec: dict, chat: Chat | None = None, attempts: int = 0,
              timeout_s: float = 60, log=None) -> dict:
    """Plan, write, build, repair. Returns the captured record for one app."""
    cfg = settings()
    chat = chat or Chat()
    attempts = int(attempts or cfg.get("attempts", 3))
    log = log or (lambda line: None)
    language = spec.get("language") or "python"
    # Whatever the other connections already worked out for this lane. Empty on
    # the first run of a language, so a pool from before this existed stays
    # comparable: the record says which prompt it was built under.
    conventions = scaffold.prompt_block(language)
    record: dict = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": chat.model, "endpoint": chat.url,
        "label": label_for(chat.model), "task": spec, "attempts": [],
        "pool_version": 1, "conventions": bool(conventions),
    }
    feedback = ""
    files: list[dict] = []
    entry = ""
    for number in range(1, attempts + 1):
        attempt: dict = {"n": number}
        try:
            plan_reply = chat.ask(PLAN_SYSTEM, PLAN_ASK.format(
                brief=spec.get("brief", ""), language=language,
                conventions=conventions))
        except BuilderError as err:
            record["error"] = str(err)[:400]
            break
        attempt["plan_reply"] = plan_reply["content"]
        attempt["plan_reasoning"] = plan_reply["reasoning"]
        attempt["seconds"] = plan_reply["seconds"]
        plan = parse_plan(plan_reply["content"])
        planned = plan.get("files") if isinstance(plan.get("files"), list) else []
        entry = str(plan.get("entry") or entry or "")
        ask = FILES_ASK.format(
            plan=json.dumps(plan, indent=2)[:4000] if plan else plan_reply["content"][:2000],
            language=language, build_hint=build_hint(language))
        if feedback:
            ask += REPAIR_NOTE.format(feedback=feedback)
        try:
            files_reply = chat.ask(FILES_SYSTEM, ask)
        except BuilderError as err:
            record["error"] = str(err)[:400]
            break
        attempt["files_reasoning"] = files_reply["reasoning"]
        attempt["files_reply"] = files_reply["content"]
        attempt["usage"] = files_reply["usage"]
        parsed = parse_files(files_reply["content"], language,
                             planned if isinstance(planned, list) else [])
        attempt["files"] = parsed
        if not parsed:
            feedback = "No FILE: blocks were found in your reply."
            attempt["build"] = {"ok": False, "error": feedback}
            record["attempts"].append(attempt)
            log(f"  attempt {number}: no files")
            continue
        if not matches_language(parsed, language):
            extensions = execution.TOOLCHAINS.get(language)
            ext = ", ".join(getattr(extensions, "extensions", ()) or ())
            feedback = (f"Those files are not {language}: this task must be written "
                        f"in {language}, and every source file ends with {ext}.")
            attempt["build"] = {"ok": False, "error": feedback}
            attempt["language_mismatch"] = True
            record["attempts"].append(attempt)
            record["language_mismatch"] = record.get("language_mismatch", 0) + 1
            log(f"  attempt {number}: wrong language ({language})")
            continue
        run_args = args_from_run(str(plan.get("run") or ""), entry)
        attempt["args"] = run_args
        result = _run(parsed, language, entry, timeout_s, run_args)
        attempt["build"] = {
            "ok": bool(result.ok), "error": execution_result_error(result),
            "stdout": (result.stdout or "")[-1200:],
            "command": result.command, "exit_code": result.exit_code,
        }
        # Tri-state, not a bool: `None` means nothing was compared because the
        # plan stated no output or the build never ran, and harvest has to be
        # able to tell that apart from a comparison that differed.
        expected = str(plan.get("expected_stdout") or "").strip()
        attempt["expected_stdout"] = expected
        attempt["expected_stdout_match"] = (
            None if not expected or not result.ok
            else " ".join((result.stdout or "").split()) == " ".join(expected.split()))
        record["attempts"].append(attempt)
        files = parsed
        log(f"  attempt {number}: {'ok' if result.ok else 'failed to build'}")
        if result.ok:
            break
        feedback = (result.error or result.stderr or result.stdout
                    or "the build exited non-zero with no output")[:1500]
    last = record["attempts"][-1] if record["attempts"] else {}
    build = last.get("build") or {}
    # The comparison travels with the record so a copy can be judged later by
    # whether anything was checked, not only by whether the build exited 0.
    build = {**build, "expected": str(last.get("expected_stdout") or ""),
             "stdout": str(build.get("stdout") or ""),
             "matches": last.get("expected_stdout_match")}
    record.update({
        "ok": bool(build.get("ok")),
        "files": files,
        "build": build,
        "dependency": _dependencies(files),
        "sha256": _sha(files) if files else "",
        "runs": len(record["attempts"]),
    })
    return record


def execution_result_error(result) -> str:
    text = " ".join((result.error or result.stderr or result.stdout or "").split())
    if text:
        return text[:1200]
    if result.exit_code is not None:
        return f"exited {result.exit_code} with no output"
    return "no output and no exit code"


def _dependencies(files: list[dict]) -> dict[str, list[str]]:
    """Standard-library-looking imports per file, so a pool can be mined for
    "what a program of this shape actually needs" without re-reading the text."""
    out: dict[str, list[str]] = {}
    for file in files:
        text = file["content"]
        found = set(re.findall(r'^\s*(?:import|from|use|require|#include)\s+"?([\w./]+)',
                               text, re.M))
        found |= set(re.findall(r'^\s*(?:import|using|use)\s+([\w.]+)', text, re.M))
        # `import ( "sort" ... )` spans lines in Go and Rust.
        for block in re.findall(r"(?:import|use)\s*\(([^)]*)\)", text, re.S):
            found |= set(re.findall(r'"([\w./]+)"', block))
        if found:
            out[file["path"]] = sorted(found)[:24]
    return out


def pool_path() -> Path:
    return config.data_dir() / "builder" / "pool.jsonl"


def status_path() -> Path:
    return config.data_dir() / "builder" / "status.json"


def write_pool(records: list[dict], path: Path | None = None) -> dict:
    """Append records to the pool, deduped per (label, task id, final files)."""
    path = path or pool_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str, str]] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            seen.add((row.get("label", ""), (row.get("task") or {}).get("id", ""),
                      row.get("sha256", "")))
    added = 0
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            key = (record.get("label", ""), (record.get("task") or {}).get("id", ""),
                   record.get("sha256", ""))
            if key in seen:
                continue
            seen.add(key)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            added += 1
    return {"path": str(path), "added": added, "written": len(records)}


def index(path: Path | None = None) -> dict:
    """What the pool holds, per model: apps, built, failed, tokens, languages."""
    path = path or pool_path()
    out: dict = {"path": str(path), "models": {}}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        slot = out["models"].setdefault(row.get("label", "?"), {
            "apps": 0, "built": 0, "files": 0, "runs": 0, "languages": {}})
        slot["apps"] += 1
        slot["built"] += int(bool(row.get("ok")))
        slot["files"] += len(row.get("files") or [])
        slot["runs"] += int(row.get("runs") or 0)
        language = (row.get("task") or {}).get("language", "?")
        slot["languages"][language] = slot["languages"].get(language, 0) + 1
    return out


def series(specs: list[dict], chat: Chat | None = None, log=None,
           attempts: int | None = None) -> list[dict]:
    chat = chat or Chat()
    out: list[dict] = []
    for index_, spec in enumerate(specs, start=1):
        log(f"[{index_}/{len(specs)}] {spec.get('id')} ({spec.get('language')})")
        out.append(build_app(spec, chat=chat, attempts=attempts, log=log))
    return out


def specs_from_library(languages: list[str] | None = None, apps: int = 3,
                       brief: str = "") -> list[dict]:
    """The briefs a series builds: one explicit brief, or library app tasks.

    A brief has no task id of its own, so it is named `brief/0` and keeps the
    first language asked for — the same shape `main` has always produced.
    """
    from . import library

    langs = [x for x in (languages or []) if x]
    if brief:
        return [{"id": "brief/0", "language": langs[0] if langs else "python",
                 "brief": brief, "source": "cli"}]
    specs: list[dict] = []
    for task in library.load_tasks():
        if len(specs) >= max(1, apps):
            break
        if not library.is_multi_file(task):
            continue
        if langs and task.get("language") not in langs:
            continue
        specs.append({"id": task["id"], "language": task["language"],
                      "brief": (task.get("description") or task.get("title") or "").strip(),
                      "source": "library"})
    return specs


# ── a series as a job the app can start and watch ──────────────────────────
# The UI has no shell, and a build is minutes of a 7B's time, so a series runs
# on a thread that publishes its progress the way validation, growth and the
# tournament already do: a status dict, mirrored to disk so a restart still
# shows the last run. The pool is written after EACH app — a series that is
# interrupted keeps every app it finished — and the scaffold snapshot with it,
# so the conventions are on disk the moment they exist.

JOB_LOCK = threading.RLock()
JOB: dict = {"state": "idle", "model": "", "connection": "", "apps": 0, "done": 0,
             "current": "", "started_at": "", "finished_at": "", "error": "",
             "records": [], "scaffold": {}}
_THREAD: threading.Thread | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def status() -> dict:
    """The job's state, falling back to the last finished run on disk."""
    with JOB_LOCK:
        snapshot = dict(JOB)
    if snapshot.get("state") == "idle":
        path = status_path()
        if path.exists():
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
                if saved.get("state") in ("done", "failed"):
                    snapshot = {**snapshot, **saved}
            except (OSError, json.JSONDecodeError):
                pass
    return snapshot


def _publish(**update) -> None:
    with JOB_LOCK:
        JOB.update(update)
        payload = dict(JOB)
    try:
        path = status_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    except OSError:
        pass


def _chat_from(entry: dict):
    """A chat that follows one connection's own block, not the builder role's.

    A `relay` player has no endpoint by design: it returns a seat a person
    answers by hand, with the same `ask` surface as the socket clients.
    """
    if str(entry.get("kind") or "").lower() == "relay":
        from .relay import RelaySeat
        return RelaySeat(name=str(entry.get("model") or "relay"),
                         timeout_s=float(entry.get("timeout_s") or 3600))
    return Chat(url=entry.get("url", ""), model=entry.get("model", ""),
                kind=entry.get("kind"), temperature=entry.get("temperature"),
                max_tokens=entry.get("max_tokens"),
                timeout_s=entry.get("timeout_s"),
                num_ctx=entry.get("num_ctx"),
                api_key=str(entry.get("api_key") or ""),
                think=bool(entry.get("think", False)))


def chat_for(connection: str = "") -> Chat:
    """A chat for a named player, or for the band's leader.

    The leader is the connection the user put in charge (`band.leader` — the
    14B on this box). Naming a player overrides it; a player that is switched
    off is refused rather than quietly used for a build.
    """
    if not connection:
        lead = band.leader()
        return _chat_from(lead) if lead else Chat()
    named = config.connections().get(connection)
    if not named:
        raise KeyError(f"no connection named {connection!r}")
    if named.get("enabled") is False:
        raise KeyError(f"connection {connection!r} is switched off")
    return _chat_from(named)


def run_series(specs: list[dict], chat: Chat, attempts: int | None = None) -> dict:
    """Build every spec, publishing after each app. Never raises."""
    _publish(state="running", model=chat.model, connection=label_for(chat.model),
             apps=len(specs), done=0, current="", error="", started_at=_now(),
             finished_at="", records=[])
    records: list[dict] = []
    try:
        for index, spec in enumerate(specs, start=1):
            _publish(current=f"{spec.get('language', '?')}: {spec.get('id', '?')}")
            record = build_app(spec, chat=chat, attempts=attempts)
            added = write_pool([record])["added"]
            snapshot = scaffold.write()
            # The pool dedupes; the copy does not. Every build is written out
            # whole so the run can be read again after the pool has moved on.
            copied = band.copy_build(record) if band.copy_builds() else {}
            records.append({
                "id": spec.get("id", ""), "language": spec.get("language", ""),
                "ok": bool(record.get("ok")), "runs": int(record.get("runs") or 0),
                "conventions": bool(record.get("conventions")),
                "files": [f.get("path") for f in (record.get("files") or [])],
                "added": added, "at": record.get("at", ""),
                "copy": copied.get("path", ""),
            })
            _publish(done=index, records=list(records),
                     scaffold=scaffold.summary())
    except Exception as err:  # a bad build must not kill the server thread
        _publish(state="failed", error=f"{type(err).__name__}: {err}"[:400],
                 finished_at=_now(), current="")
        return status()
    _publish(state="done", current="", finished_at=_now(),
             scaffold=scaffold.summary())
    return status()


def start(languages: list[str] | None = None, apps: int = 3,
          attempts: int | None = None, brief: str = "",
          connection: str = "") -> dict:
    """Start a series in the background; returns immediately with its status."""
    global _THREAD
    with JOB_LOCK:
        if JOB.get("state") == "running":
            return {**status(), "error": "a builder series is already running"}
        specs = specs_from_library(languages, apps, brief)
        if not specs:
            return {**status(),
                    "error": "no briefs to build: pass a brief or ingest the library"}
        try:
            chat = chat_for(connection)
        except KeyError as err:
            return {**status(), "error": str(err)}
        _publish(state="running", model=chat.model, connection=label_for(chat.model),
                 apps=len(specs), done=0, current="", error="", started_at=_now(),
                 finished_at="", records=[], scaffold={})
    _THREAD = threading.Thread(target=run_series,
                               args=(specs, chat, attempts), daemon=True)
    _THREAD.start()
    return status()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a series of apps with the second model")
    parser.add_argument("--apps", type=int, default=5)
    parser.add_argument("--languages", default="python,go,typescript")
    parser.add_argument("--model", default="", help="overrides builder.model")
    parser.add_argument("--url", default="", help="overrides builder.url")
    parser.add_argument("--brief", default="", help="one explicit app, repeatable")
    parser.add_argument("--think", action="store_true",
                        help="ask a reasoning model to expose its thinking")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    languages = [x.strip() for x in args.languages.split(",") if x.strip()]
    specs = specs_from_library(languages, args.apps, args.brief)
    chat = Chat(url=args.url, model=args.model,
                think=True if args.think else None)
    log = lambda line: print(line, flush=True)  # noqa: E731
    log(f"builder: {chat.model} at {chat.url} · {len(specs)} app(s)")
    records = series(specs[:args.apps], chat=chat, log=log)
    written = write_pool(records, Path(args.out) if args.out else None)
    print(json.dumps({"written": written, "index": index()}, indent=2))
    return 0 if any(r.get("ok") for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
