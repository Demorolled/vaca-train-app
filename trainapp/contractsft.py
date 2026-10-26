"""contractsft — training rows for the two boundary contracts still failing.

The battery is a contract gate, not a quality grade: it checks that VACA still
gets one file back, with no markdown fence, no invented siblings, no echoed
scaffold. Two of those fail on every arm so far:

* `scaffold-invent` — asked for `router.go`, the model also invents other files
  and announces them with `FILE:` lines. VACA plans the file list; the model
  writes one file.
* `repair-go` — handed a Go file that fails with "declared and not used: x", the
  model returns the file with the dead variable still in it.

Neither is a capability the library can teach by showing more programs, so the
rows here are shaped like the contract itself. The invent rows come from the
library's verified multi-file sets — the answer is the one target file that set
really has, and the instruction repeats the invitation to invent so the refusal
is what gets learned. The repair rows take a verified Go build and insert the
dead declaration the compiler would reject, so the input is genuinely broken and
the answer is the build that already passed.
"""
from __future__ import annotations

from . import library, scaffoldsft

INVENT_INSTRUCTION = (
    "Write the file `{path}` for this project: {title}. If other files are needed, "
    "output them as separate blocks, each starting with a line \"FILE: <path>\". "
    "If scaffold files are needed, create them too.")
REPAIR_INSTRUCTION = (
    "This Go file fails the compiler with: '{error}'. Return the corrected file "
    "only, no explanations.\n---\n{code}\n---")

# Names the diagnostic can carry; the probe names `x`, so it appears first.
DEAD_NAMES = ("x", "tmp", "unused", "count", "n")


def _invent_rows(share: int = scaffoldsft.TRAIN_SHARE,
                 all_languages: bool = False) -> list[dict]:
    """One row per verified multi-file set: answer with the target file alone."""
    validation = library.load_validation()
    out: list[dict] = []
    seen: set[str] = set()
    for task in library.load_tasks(all_languages=all_languages):
        if not library.is_multi_file(task):
            continue
        if (validation.get(task.get("id", "")) or {}).get("status") != "verified":
            continue
        if not scaffoldsft.is_trainable(task, share):
            continue
        target = task.get("target", "")
        code = (task.get("code") or "").strip()
        if not target or not code or "FILE: " in code:
            continue
        if task["id"] in seen:
            continue
        seen.add(task["id"])
        title = (task.get("description") or task.get("title") or "a small project").strip()
        out.append({
            "instruction": INVENT_INSTRUCTION.format(path=target, title=title[:300]),
            "input": "",
            "output": code,
            "source": "library:one-file",
            "meta": {"task_id": task["id"], "language": task.get("language", ""),
                     "target": target},
        })
    return out


def _broken(code: str, name: str) -> tuple[str, int] | None:
    """The same file with one dead declaration added to `main`, and its line."""
    lines = code.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "func main() {":
            lines.insert(index + 1, f"\t{name} := 1")
            return "\n".join(lines) + "\n", index + 2
    return None


def _repair_rows(per_family: int = 2,
                 all_languages: bool = False) -> list[dict]:
    """Verified Go builds, broken by a dead declaration, repaired by the original."""
    validation = library.load_validation()
    counts: dict[str, int] = {}
    out: list[dict] = []
    for task in library.load_tasks(all_languages=all_languages):
        if task.get("language") != "go" or library.is_multi_file(task):
            continue
        if (validation.get(task.get("id", "")) or {}).get("status") != "verified":
            continue
        code = (task.get("code") or "").strip()
        if not code or "x := 1" in code:
            continue
        family = task.get("family") or task.get("title") or task["id"]
        if counts.get(family, 0) >= per_family:
            continue
        name = DEAD_NAMES[counts.get(family, 0) % len(DEAD_NAMES)]
        broken = _broken(code, name)
        if broken is None:
            continue
        text, line = broken
        counts[family] = counts.get(family, 0) + 1
        out.append({
            "instruction": REPAIR_INSTRUCTION.format(
                error=f"./main.go:{line}:2: declared and not used: {name}", code=text),
            "input": "",
            "output": code + "\n",
            "source": "library:dead-variable",
            "meta": {"task_id": task["id"], "language": "go", "name": name},
        })
    return out


def rows(share: int = scaffoldsft.TRAIN_SHARE,
         all_languages: bool = False) -> list[dict]:
    return (_invent_rows(share, all_languages)
            + _repair_rows(all_languages=all_languages))


def stats() -> dict:
    rows_ = rows()
    by_source: dict[str, int] = {}
    for row in rows_:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
    return {"rows": len(rows_), "by_source": by_source}
