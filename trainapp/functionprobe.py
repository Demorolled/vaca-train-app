"""functionprobe — verified rows at function granularity.

Measured on the same 19 non-TypeScript held-out sets, same model: asking for the
whole target file matched the reference output 4/19 times; asking for one
function, with the real signature and the sibling files in context, matched
11/19. The unit of generation was the bottleneck, not the weights.

So a row here is one function. The model writes it, it is spliced back into the
real target file, the whole set is built and run by `execution.run_files`, and
the row is a demonstration only when the set's output equals the untouched
set's output. A failure is kept with its error: it is the `rejected` half of a
pair and a probe for prompts, never an SFT output.

Prompts use the trainer's exact `### Instruction / ### Input / ### Response`
template (`train_lora.py`), so an exported row trains the prompt the probe asked.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from . import execution, library, repair, runprobe

# Languages whose target file can hold a function we can find and splice back.
BRACE_LANGS = {"go", "rust", "c", "cpp", "csharp", "java", "javascript",
               "typescript", "kotlin", "swift", "php"}
SCRIPT_LANGS = {"python", "ruby"}
LANGUAGES = BRACE_LANGS | SCRIPT_LANGS

# `foreach` was missing here, and PHP has no entry in SIGNATURES, so every
# `foreach ($x as $y) {` matched GENERIC: the probe then asked the model for "this
# foreach" and spliced a whole function over the loop body. 190 night asks did
# exactly that and the compiler answered "Cannot redeclare function".
CONTROL = re.compile(r"^\s*(if|for|foreach|while|switch|catch|else|do|try|finally|return|"
                     r"guard|defer)\b")
SIGNATURES = {
    "go": re.compile(r"^func\s+(\([^)]*\)\s*)?(\w+)\s*\("),
    # `function name(` with any modifier run, and the by-reference `&` form.
    "php": re.compile(r"^\s*(?:(?:public|protected|private|static|final|abstract)\s+)*"
                      r"function\s+&?\s*(\w+)\s*\("),
    "rust": re.compile(r"^\s*(pub\s+)?(async\s+)?fn\s+(\w+)\s*[<(]"),
    "python": re.compile(r"^(\s*)def\s+(\w+)\s*\("),
    "ruby": re.compile(r"^\s*def\s+(self\.)?(\w+[?!=]?)"),
}
# `Type name(args) {`, `Type name(args) => expr {`, indented or not.
GENERIC = re.compile(r"^\s*[^\s{}#/][^=;()]*\w+\s*\([^;]*\)\s*"
                     r"(?::\s*[^={]+|->\s*[^={]+)?\s*(const\s+)?\{\s*$")
ARROW = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*"
                   r"(?:async\s*)?(?:\([^)]*\)|[\w.]+)\s*(?::[^=]+)?=>\s*\{\s*$")
RUBY_OPENER = re.compile(r"^\s*(def|do|if|unless|case|begin|while|until|for|"
                         r"class|module)\b")
RUBY_DO = re.compile(r"\bdo\b\s*(\|[^|]*\|)?\s*$")
RUBY_END = re.compile(r"^\s*end\b")

TEMPLATE = ("### Instruction\n{instruction}\n\n"
            "### Input\n{input}\n\n"
            "### Response\n")
INSTRUCTION = ("Write ONLY this function for `{target}` in a {language} project. "
               "It must use the real exports of the sibling files below — do not "
               "invent members, and do not change the signature. Reply with the "
               "function only: no fences, no prose.")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def strip_noise(line: str) -> str:
    """A line with comments and string contents blanked, for brace counting."""
    line = re.sub(r"//.*$", "", line)
    if line.lstrip().startswith("#"):
        line = ""
    else:
        line = re.sub(r"#.*$", "", line)
    return re.sub(r"""(['"]).*?\1""", '""', line)


def block_by_braces(lines: list[str], start: int) -> int | None:
    depth, opened = 0, False
    for i in range(start, len(lines)):
        for ch in strip_noise(lines[i]):
            if ch == "{":
                depth += 1
                opened = True
            elif ch == "}":
                depth -= 1
        if opened and depth <= 0:
            return i
    return None


def block_by_indent(lines: list[str], start: int) -> int:
    indent = len(lines[start]) - len(lines[start].lstrip())
    last = start
    for i in range(start + 1, len(lines)):
        if not lines[i].strip():
            continue
        if len(lines[i]) - len(lines[i].lstrip()) <= indent:
            break
        last = i
    return last


def block_by_end(lines: list[str], start: int) -> int | None:
    """Ruby: `def` … its matching `end`, counting nested openers."""
    depth = 0
    for i in range(start, len(lines)):
        if RUBY_OPENER.match(lines[i]) or RUBY_DO.search(strip_noise(lines[i])):
            depth += 1
        if RUBY_END.match(lines[i]):
            depth -= 1
            if depth <= 0:
                return i
    return None


def find_functions(language: str, code: str) -> list[dict]:
    """Every function-shaped block in `code`, with its line span."""
    lines = code.splitlines()
    found: list[dict] = []
    for i, line in enumerate(lines):
        if CONTROL.match(line):
            continue
        if language in SIGNATURES:
            match = SIGNATURES[language].search(line)
        else:
            match = GENERIC.match(line)
            if match and ("=" in line.split("(")[0] or "return" in line):
                match = None
            if not match and language in {"javascript", "typescript"}:
                match = ARROW.match(line)
        if not match:
            continue
        if language == "python":
            end = block_by_indent(lines, i)
        elif language == "ruby":
            end = block_by_end(lines, i)
        else:
            end = block_by_braces(lines, i)
        if end is None or end <= i:
            continue
        found.append({"start": i, "end": end,
                      "block": "\n".join(lines[i:end + 1]),
                      "signature": line.strip(), "lines": end - i + 1})
    return found


def largest_function(language: str, code: str) -> dict | None:
    """The function worth asking for: the biggest one in the target file."""
    functions = find_functions(language, code)
    return max(functions, key=lambda f: f["lines"]) if functions else None


def probe_functions(task: dict, max_functions: int = 0,
                    min_lines: int = 4) -> list[dict]:
    """Every function worth asking for in the target, largest first.

    One set is not one prompt: a target file holds several functions, and each
    is a separate ask with the same siblings. `min_lines` drops one-liners that
    are not worth a model call.
    """
    target = target_of(task)
    if target is None:
        return []
    functions = [f for f in find_functions(task["language"], target["content"])
                 if f["lines"] >= min_lines]
    functions.sort(key=lambda f: f["lines"], reverse=True)
    return functions[:max_functions] if max_functions else functions


def function_name(signature: str) -> str:
    """The declared name: the last identifier that opens an argument list.

    `func (r *R) Name(x)` yields `Name`, not the receiver, and `int main(` yields
    `main`. Good enough to find the same function in a reply that also carries
    imports or a whole program.
    """
    names = re.findall(r"([A-Za-z_]\w*)\s*\(", signature or "")
    return names[-1] if names else ""


def extract_block(language: str, text: str, signature: str) -> str:
    """Just the asked-for function from a reply, dropping the rest of it.

    Models routinely answer a one-function ask with imports, a class wrapper or
    a whole program. Splicing that into the middle of a file breaks the build
    for a reason that has nothing to do with whether the function is right, so
    the reply is narrowed to the function whose name was asked for.
    """
    wanted = function_name(signature)
    if not wanted:
        return text
    for fn in find_functions(language, text):
        if function_name(fn["signature"]) == wanted:
            return fn["block"].rstrip() + "\n"
    return text


def splice(code: str, fn: dict, replacement: str) -> str:
    """`code` with `fn`'s line span replaced by `replacement`."""
    lines = code.splitlines()
    block = replacement.rstrip("\n").splitlines()
    return "\n".join(lines[:fn["start"]] + block + lines[fn["end"] + 1:]) + "\n"


def target_of(task: dict) -> dict | None:
    return next((f for f in task.get("files") or [] if f.get("path") == task.get("target")), None)


def entry_for(task: dict) -> str:
    return task["target"] if execution.is_entry_name(task["target"]) else ""


def run_set(task: dict, target_code: str, timeout_s: float = 25, probes=None,
            compile_only: bool = False):
    files = [{"path": f["path"],
              "content": target_code if f["path"] == task["target"] else f["content"]}
             for f in task["files"]]
    probe = runprobe.for_task(task, probes)
    return execution.run_files(files, task["language"], entry=entry_for(task),
                               timeout_s=timeout_s, compile_only=compile_only,
                               args=list(probe["args"]) if probe else None)


def siblings(task: dict) -> str:
    return "\n\n".join(f"--- {f['path']} ---\n{f['content'].strip()}"
                       for f in task["files"] if f["path"] != task["target"])


IMPORT_LINE = {
    "python": re.compile(r"^\s*(import|from)\s+\w"),
    "ruby": re.compile(r"^\s*(require|require_relative)\b"),
    "c": re.compile(r"^\s*#include\b"),
    "cpp": re.compile(r"^\s*#include\b"),
    "go": re.compile(r"^\s*(import\b|\"[\w./]+\"|\))"),
    "rust": re.compile(r"^\s*(use|extern\s+crate)\b"),
    "php": re.compile(r"^\s*(require|require_once|include|include_once|use)\b"),
}
DEFAULT_IMPORT = re.compile(r"^\s*(import|using|use|package)\b")


def import_lines(language: str, code: str, limit: int = 24) -> list[str]:
    """The top-level imports the target file already has, as written.

    The ask used to hide these. The model was told not to invent members while
    being shown the siblings and the signature but never the file's own import
    list, so it reached for `sort.Slice` in a file that never imported `sort`:
    490 of Go's 803 night failures are `undefined: <package>`, 280 of them
    `sort`/`io`/`ioutil`/`time`/`strconv`/`fmt`. The one list that would have
    settled it was the one the prompt left out.
    """
    pattern = IMPORT_LINE.get(language, DEFAULT_IMPORT)
    out: list[str] = []
    in_block = False
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#!"):
            continue
        if stripped.startswith("import (") and language == "go":
            in_block = True
        if pattern.match(line) or (in_block and stripped):
            out.append(stripped)
            if in_block and stripped == ")":
                in_block = False
        elif out and not in_block:
            break  # imports end at the first non-import line
        if len(out) >= limit:
            break
    return out


def prompt_parts(task: dict, fn: dict) -> tuple[str, str]:
    """(instruction, input) in the trainer's SFT shape."""
    instruction = INSTRUCTION.format(target=task["target"], language=task["language"])
    spec = (task.get("description") or task.get("title") or "").strip()
    parts = [f"### Function signature\n{fn['signature']}"]
    target = target_of(task)
    imports = import_lines(task.get("language", ""),
                           (target or {}).get("content", ""))
    if imports:
        parts.append("### Imports already in this file (declare nothing else)\n"
                     + "\n".join(imports))
    if spec:
        parts.append(f"### What it must do\n{spec}")
    parts.append(f"### Sibling files (authoritative)\n{siblings(task)}")
    return instruction, "\n\n".join(parts)


def prompt_for(task: dict, fn: dict) -> str:
    instruction, given = prompt_parts(task, fn)
    return TEMPLATE.format(instruction=instruction, input=given)


def collapse(text: str) -> str:
    """Whitespace-insensitive comparison, as the tournament compares stdout."""
    return " ".join((text or "").split())


def diagnostic(result) -> str:
    """Why a set failed, from whichever stream actually carried it.

    483 of the night's failed attempts recorded `compile: false` with an empty
    error: a checker that says nothing on some failures, or a run that exits
    non-zero having printed nothing, left nothing to learn from. The streams are
    tried in order, then the exit code — not a diagnosis, but evidence that
    something ran and failed, which is the difference between "unknown" and
    "no reason at all".
    """
    text = " ".join((result.error or result.stderr or result.stdout or "").split())
    if text:
        return text[:400]
    if result.exit_code is not None:
        return f"exited {result.exit_code} with no output"
    return "no output and no exit code: the step never started"


def probe(task: dict, client, timeout_s: float = 25, reference: str | None = None,
          reference_ok: bool | None = None, fn: dict | None = None) -> dict:
    """Ask for one function, splice it in, run the set, and score the row.

    An empty reference is not a failure: TypeScript sets are typechecked rather
    than run, and some programs print nothing. What cannot be judged is a set
    whose own reference run failed — that is a skip, never a model failure.
    """
    target = target_of(task)
    if fn is None:
        fn = largest_function(task["language"], target["content"]) if target else None
    if fn is None:
        return {"task_id": task["id"], "language": task["language"],
                "target": task.get("target", ""), "skipped": "no function",
                "at": now()}
    why = ""
    if reference is None or reference_ok is None:
        base = run_set(task, target["content"], timeout_s)
        reference = collapse(base.stdout)
        reference_ok = base.ok
        why = base.error or base.stderr or ""
    if not reference_ok:
        return {"task_id": task["id"], "language": task["language"],
                "target": task["target"], "skipped": "reference failed",
                "error": why[:400], "at": now()}

    prompt = prompt_for(task, fn)
    raw = repair.extract_code(client.complete(prompt))
    reply = extract_block(task["language"], raw, fn["signature"])
    got = run_set(task, splice(target["content"], fn, reply), timeout_s)
    match = got.ok and collapse(got.stdout) == reference
    instruction, given = prompt_parts(task, fn)
    return {
        "task_id": task["id"], "language": task["language"],
        "target": task["target"], "function": fn["signature"],
        "function_lines": fn["lines"],
        "compile": got.ok, "match": match, "reference": reference,
        "reference_ok": bool(reference_ok),
        "stdout": collapse(got.stdout)[:400],
        "error": diagnostic(got),
        "instruction": instruction, "input": given,
        "prompt": prompt, "reply": reply,
        "raw_reply": raw if raw.strip() != reply.strip() else "",
        "at": now(),
    }


def candidates() -> list[dict]:
    """Verified file sets, round-robin by language so any prefix is representative."""
    validation = library.load_validation()
    tasks = [t for t in library.load_tasks()
             if library.is_multi_file(t)
             and t.get("language") in LANGUAGES
             and (validation.get(t["id"]) or {}).get("status") == "verified"]
    groups: dict[str, list[dict]] = {}
    for task in sorted(tasks, key=lambda t: t["id"]):
        groups.setdefault(task.get("language", ""), []).append(task)
    out: list[dict] = []
    while any(groups.values()):
        for language in sorted(groups):
            if groups[language]:
                out.append(groups[language].pop(0))
    return out


def pool_candidates() -> list[dict]:
    """Verified file sets a frozen held-out pool may name, lane cut or not.

    The pools are frozen so cycles stay comparable, but `candidates()` is scoped
    to the five lanes and the cut came after the pools were first built. Resolving
    a pool through `candidates()` therefore *silently drops* the sets the champion
    was scored on: the champion's 20/70 came from all 76 sets, while every
    candidate since the cut was scored on the 53 that survived it, and the two
    rates were never the same measurement. A frozen pool is resolved whole.
    """
    validation = library.load_validation()
    return [t for t in library.load_tasks(all_languages=True)
            if library.is_multi_file(t)
            and t.get("language") in LANGUAGES
            and (validation.get(t["id"]) or {}).get("status") == "verified"]


def references(tasks: list[dict], timeout_s: float = 25) -> dict[str, tuple[bool, str]]:
    """The untouched set's (ran, stdout) per task, so a round need not re-run it."""
    out: dict[str, tuple[bool, str]] = {}
    for task in tasks:
        target = target_of(task)
        if target is None:
            continue
        base = run_set(task, target["content"], timeout_s)
        out[task["id"]] = (base.ok, collapse(base.stdout))
    return out


def sft_rows(records: list[dict]) -> list[dict]:
    """Passing rows as the correction sheet's `{instruction, input, output}` shape."""
    rows = []
    seen: set[tuple[str, str]] = set()
    for row in records:
        if not row.get("match") or not (row.get("reply") or "").strip():
            continue
        asked = row.get("function") or ""
        output = (extract_block(row["language"], row["reply"], asked)
                  if asked else row["reply"])
        # Samples of the same set can produce the identical answer; one
        # demonstration is enough, and duplicates skew the split.
        key = (row.get("prompt", ""), output.strip())
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "instruction": row["instruction"],
            "input": row["input"],
            "output": output.strip() + "\n",
            "task_id": row["task_id"], "language": row["language"],
            # "behaviour" ran and matched stdout; "compile" passed where the
            # set only typechecks (TypeScript) or prints nothing.
            "verified": "behaviour" if row.get("reference") else "compile",
            "origin": "function-probe",
        })
    return rows


def pair_rows(records: list[dict]) -> list[dict]:
    """Same prompt, a passing reply against a failing one — the ORPO shape."""
    passed: dict[str, dict] = {}
    failed: dict[str, list[dict]] = {}
    for row in records:
        if not row.get("prompt") or not (row.get("reply") or "").strip():
            continue
        if row.get("match"):
            passed.setdefault(row["prompt"], row)
        else:
            failed.setdefault(row["prompt"], []).append(row)
    def block(row: dict) -> str:
        asked = row.get("function") or ""
        text = row["reply"]
        return extract_block(row["language"], text, asked) if asked else text

    rows = []
    seen: set[tuple[str, str, str]] = set()
    for prompt, good in passed.items():
        for bad in failed.get(prompt, []):
            chosen, rejected = block(good).strip(), block(bad).strip()
            if not chosen or not rejected or chosen == rejected:
                continue
            key = (prompt, chosen, rejected)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"prompt": prompt, "chosen": chosen + "\n",
                         "rejected": rejected + "\n",
                         "task_id": good["task_id"], "language": good["language"],
                         "origin": "function:pair"})
    return rows
