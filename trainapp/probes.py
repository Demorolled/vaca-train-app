"""probes — the contract gate a round has to pass before it can be kept.

Held-out preference accuracy says a policy prefers one file over another; it does
not say the policy still behaves like VACA's coder. The rounds that raised that
accuracy from 0.54 to 0.69 also went back to wrapping answers in fences and
started answering reasoning questions with a Python function — neither shows up
in the preference number.

This is the 17-probe boundary battery from `R40_BOUNDARY_SCAN.md`, reduced to the
probes whose answers a machine can judge, so `trainloop` can score every round:
fence-free single files, scaffold bodies replaced rather than echoed, no invented
`FILE:` blocks, silent arithmetic, and a reasoning lane that stays reasoning.

Checks are deliberately literal. They are a contract gate, not a quality grade:
they catch a round that breaks the format the app depends on, and leave "is the
code any good" to the battery, which compiles and runs it.

A probe is answered more than once, because one answer is a coin flip: three
draws at the app's own sampling, graded by majority, and a split probe is handed
a second batch so the pooled majority decides. `samples > 1` on a greedy coder
buys nothing — the same decode comes back every time — which is why `evaluate`
takes a temperature and says so in the log when it was given none.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import config

MAX_NEW_TOKENS = 384

# id, lane, prompt — verbatim from R40_BOUNDARY_SCAN.md so numbers stay comparable.
PROBES: tuple[tuple[str, str, str], ...] = (
    ("role-what", "role",
     "In 4 sentences or fewer: what is VACA, and what is your role inside it?"),
    ("role-who-plans", "role",
     "In VACA's build pipeline, who decides the list of files for a project — you "
     "(the model) or the app? Who writes the scaffold files? Answer in 3 sentences, no code."),
    ("role-contract", "role",
     "You are asked by VACA to write ONE file. List what MUST appear in your answer "
     "and what MUST NOT appear. Bullet points, max 6 bullets."),
    ("chat-name", "chat",
     "hey, quick one — suggest 3 short names for a CLI that renames files in bulk. "
     "one line each, casual."),
    ("chat-terse", "chat",
     "Say OK if you can hear me."),
    ("write-python", "write",
     "Write a Python 3 program `wc.py` that reads a file path from argv[1] and prints "
     "the number of non-empty lines. Output ONLY the file content. No markdown fences. "
     "No explanations."),
    ("write-go", "write",
     "Write a Go program `main.go` that prints the command-line arguments joined by "
     "spaces. Standard library only. Output ONLY the file content. No markdown fences."),
    ("write-ts", "write",
     "Write a single TypeScript file `todo.ts` (Node, ESM) with a class TodoStore with "
     "methods add(text), list(), complete(id). In-memory only. Output ONLY the file "
     "content. No markdown fences."),
    ("plan-rust", "plan",
     "Plan the files for this project: a Rust CLI that counts words in a text file. "
     "Single file is fine.\nOutput one line per file, exactly in this shape:\n"
     "<path> (<language>) — <role>\nNo other text."),
    ("plan-node", "plan",
     "Plan the files for: a multi-file Node.js API with users and posts endpoints, "
     "JSON storage.\nOutput one line per file, exactly in this shape:\n"
     "<path> (<language>) — <role>\nNo other text."),
    ("scaffold-who", "scaffold",
     "VACA creates scaffold/placeholder files before real code is written (for example "
     "entry points with TODO bodies). Answer in 3 sentences: does the app create them, "
     "or do you create them inside your output? And when you are later asked to write "
     "one of those files, what should happen to the placeholder body?"),
    ("scaffold-fill", "scaffold",
     "Fill in the real implementation of this scaffold file. Keep it valid Go.\n---\n"
     "// generated from template for Go CLI\npackage main\n\nimport \"fmt\"\n\n"
     "func main() {\n\t// TODO: implement\n\tfmt.Println()\n}\n---\n"
     "Output ONLY the file content."),
    ("scaffold-invent", "scaffold",
     "Write the file `router.go` for a small Go HTTP JSON API with a GET /users "
     "endpoint returning a hardcoded list of users. If other files are needed, output "
     "them as separate blocks, each starting with a line \"FILE: <path>\". If scaffold "
     "files are needed, create them too."),
    ("reason-prime", "reason", "Is 17 prime? Think step by step, then answer."),
    ("reason-silent", "reason",
     "Compute 23 * 47. Answer with only the number — do not show your work."),
    ("repair-go", "repair",
     "This Go file fails the compiler with: './main.go:6:2: declared and not used: x'. "
     "Return the corrected file only, no explanations.\n---\npackage main\n\n"
     "import \"fmt\"\n\nfunc main() {\n\tx := 1\n\tfmt.Println(\"hi\")\n}\n---"),
    ("meta-reason", "meta",
     "When you generate code for VACA, do you think step by step before answering? "
     "Should you? Answer in 3 sentences."),
)

FENCE = re.compile(r"```")
FILE_BLOCK = re.compile(r"(?m)^FILE: ")
PLAN_LINE = re.compile(r"^\S.*\([^)]+\).+—.+$")
CODE_MARKER = re.compile(r"```|\bdef\b|\bfunc\b|\bclass\b|\bimport\b|\bpackage\b")


def _first_line(text: str) -> str:
    return next((ln.strip() for ln in text.strip().splitlines() if ln.strip()), "")


def _duplicate_block(text: str) -> str:
    """The same opening line twice — the model answered and then answered again."""
    first = _first_line(text)
    if len(first) < 6:
        return ""
    return f"duplicate block ({first[:40]!r})" if text.count(first) > 1 else ""


def _no_fences(text: str) -> str:
    count = len(FENCE.findall(text))
    return f"{count} fence marker(s)" if count else ""


def _check_answer(pid: str, text: str) -> str:
    """Empty string when the probe passed, else why it failed."""
    body = text.strip()
    low = body.lower()
    if pid.startswith("write-"):
        return _no_fences(body) or _duplicate_block(body)
    if pid == "repair-go":
        why = _no_fences(body) or _duplicate_block(body)
        if why:
            return why
        # R40 kept the dead variable alive with `_ = 1`; a repair should delete it.
        return "kept the dead variable" if "x := 1" in body else ""
    if pid.startswith("plan-"):
        why = _no_fences(body)
        if why:
            return why
        lines = [ln for ln in body.splitlines() if ln.strip()]
        if len(lines) > 8:
            return f"over-planned ({len(lines)} files for a single-file ask)"
        if not all(PLAN_LINE.match(ln) for ln in lines):
            return "not the requested 'path (language) — role' shape"
        return ""
    if pid == "scaffold-fill":
        why = _no_fences(body) or _duplicate_block(body)
        if why:
            return why
        for marker in ("TODO", "generated from template", "placeholder"):
            if marker.lower() in low:
                return f"kept the scaffold text ({marker!r})"
        if "package main" not in body:
            return "did not return a Go file"
        return ""
    if pid == "scaffold-invent":
        why = _no_fences(body)
        if why:
            return why
        blocks = len(FILE_BLOCK.findall(body))
        return f"invented {blocks} FILE: block(s)" if blocks else ""
    if pid == "reason-prime":
        if CODE_MARKER.search(body):
            return "answered a reasoning question with code"
        # "True. It is a prime number because…" is a correct answer in prose;
        # requiring the literal words "is prime" failed it as if the lane broke.
        if "prime" not in low and "yes" not in low:
            return "never answered the question"
        return ""
    if pid == "reason-silent":
        return "" if body.strip().rstrip(".") == "1081" else f"did not answer with the number ({body[:40]!r})"
    return ""


# Probes whose answer a machine can judge; the role/chat/meta lanes are recorded
# for the transcript but cannot be graded without a reader.
SCORED = {pid for pid, _lane, _prompt in PROBES
          if pid.startswith(("write-", "plan-", "repair-"))
          or pid in ("scaffold-fill", "scaffold-invent",
                      "reason-prime", "reason-silent")}


def check(probe_id: str, text: str) -> dict:
    """A scored probe's verdict; probes without a check are recorded, not graded."""
    scored = probe_id in SCORED
    why = _check_answer(probe_id, text) if scored else ""
    return {"id": probe_id, "ok": not why, "reason": why, "scored": scored}


def locate() -> Path:
    path = config.data_dir() / "probes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _failing_reason(attempts: list[dict], passed: int, runs: int) -> str:
    """Why a probe lost: its most common failure, plus how many runs passed."""
    counts: dict[str, int] = {}
    for attempt in attempts:
        if attempt["ok"]:
            continue
        why = attempt["reason"] or "no answer"
        counts[why] = counts.get(why, 0) + 1
    why = max(counts, key=counts.get) if counts else "no answer"
    return f"{why} ({passed}/{runs} runs passed)" if runs > 1 else why


def _draw(coder, pid: str, prompt: str, count: int, log) -> list[dict]:
    """`count` independent answers to one probe, each graded on its own."""
    attempts: list[dict] = []
    for _ in range(count):
        try:
            text = coder.complete(prompt)
        except Exception as err:  # a broken coder is a failed probe, not a crash
            attempts.append({"ok": False, "response": "",
                             "reason": f"coder failed: {type(err).__name__}"})
            log(f"[probe {pid}] coder failed: {err}")
            continue
        verdict = check(pid, text)
        attempts.append({"ok": verdict["ok"], "reason": verdict["reason"],
                         "response": text})
    return attempts


def evaluate(model: str, adapter: str = "", max_new_tokens: int = MAX_NEW_TOKENS,
             samples: int = 1, confirm: int = 0, temperature: float = 0.0,
             top_p: float = 1.0, log=print) -> dict:
    """Run the battery against one adapter and return its pass set.

    One sample grades a coin flip as a fact. `samples > 1` grades each probe by
    a strict majority of its runs — but only if the runs are different draws: a
    greedy coder (`temperature=0`, the default) returns the same decode every
    time, so `samples` alone is a formality and this says so in the log.

    `confirm` is the stability half of the guard. A probe that splits its first
    batch (some runs pass, some fail) is not decided by that batch: it is asked
    `confirm` more times, and the pooled majority decides. A probe that fails
    every draw or passes every draw is left alone — a lane lost 3/3 or held 3/3
    is evidence, and paying for a recheck of it would only double the gate.

    torch/transformers are imported by `LocalCoder` lazily, so importing this
    module stays free on a machine without them.
    """
    from .localcoder import LocalCoder

    runs = max(1, samples)
    recheck = max(1, confirm)
    name = f"{model}+{Path(adapter).parent.name}" if adapter else model
    if runs > 1 and temperature <= 0:
        log(f"[probe gate] {name}: greedy coder, {runs} runs repeat one decode")
    coder = LocalCoder(model, adapter=adapter, max_new_tokens=max_new_tokens,
                       temperature=temperature, top_p=top_p)
    rows: list[dict] = []
    rechecked: list[str] = []
    try:
        for pid, lane, prompt in PROBES:
            attempts = _draw(coder, pid, prompt, runs, log)
            passed = sum(1 for attempt in attempts if attempt["ok"])
            if confirm and 0 < passed < runs:
                rechecked.append(pid)
                log(f"[probe {pid}] split {passed}/{runs}, asking {recheck} more")
                attempts += _draw(coder, pid, prompt, recheck, log)
                passed = sum(1 for attempt in attempts if attempt["ok"])
            total = len(attempts)
            ok = passed * 2 > total
            verdict = {"id": pid, "lane": lane, "prompt": prompt, "ok": ok,
                       "scored": pid in SCORED, "passed_runs": passed, "runs": total,
                       "rechecked": pid in rechecked,
                       "reason": "" if ok else _failing_reason(attempts, passed, total),
                       "response": attempts[-1]["response"], "attempts": attempts}
            rows.append(verdict)
            note = f" ({passed}/{total})" if total > 1 else ""
            log(f"[probe {pid}] {'pass' + note if ok else 'FAIL: ' + verdict['reason']}")
    finally:
        coder.close()

    scored = [r for r in rows if r.get("scored")]
    passed = [r["id"] for r in scored if r["ok"]]
    failures = [{"id": r["id"], "reason": r.get("reason") or "no answer"} for r in scored
                if not r["ok"]]
    result = {
        "arm": name,
        "adapter": adapter,
        "passed": len(passed),
        "total": len(scored),
        "passed_ids": passed,
        "failures": failures,
        "rechecked": rechecked,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = locate() / "probes.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({**result, "rows": rows}, ensure_ascii=False) + "\n")
    return result


def regressions(baseline: dict, current: dict) -> list[dict]:
    """Probes the baseline passed and the round now fails — the gate's verdict.

    A round may fix probes and gain others; only losing a passed probe blocks it.
    """
    before = set(baseline.get("passed_ids") or [])
    after = set(current.get("passed_ids") or [])
    reasons = {f["id"]: f["reason"] for f in current.get("failures") or []}
    return [{"id": pid, "reason": reasons.get(pid, "failed")}
            for pid in sorted(before - after)]


LANES = {pid: lane for pid, lane, _prompt in PROBES}


def lane_stats(result: dict) -> dict[str, dict]:
    """Pass counts per lane: which contract moved, not just the total.

    A total of 4/10 says a candidate lost two probes; it does not say whether it
    gave up the no-fence lane — the thing this gate exists to protect — or
    drifted on a prose answer.
    """
    out: dict[str, dict] = {}
    for pid in LANES:
        if pid not in SCORED:
            continue
        lane = LANES[pid]
        slot = out.setdefault(lane, {"passed": 0, "total": 0})
        slot["total"] += 1
        slot["passed"] += int(pid in set(result.get("passed_ids") or []))
    return out


def summary(result: dict) -> dict:
    """The compact form that goes into the loop's status/history."""
    return {"arm": result.get("arm", ""), "passed": result.get("passed", 0),
            "total": result.get("total", 0),
            "failures": [f["id"] for f in result.get("failures") or []],
            "lanes": lane_stats(result),
            "at": result.get("at", "")}
