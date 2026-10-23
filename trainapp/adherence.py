"""adherence — does a file set hang together as a scaffold?

A compiling file is not a modelled file. The failure mode that matters when an
app is built from several files is *adherence*: a module promises exports and
declares none, imports a sibling that was never written, imports a package that
is in no manifest, or is a stub that compiles because its body throws. None of
those show up in a single-file compile gate.

This is the trainer's copy of the transferable half of VACA's
`services/scaffoldVariation.ts:scoreFilesAdherence()` — the same checks, on a
file set, with no TypeScript runtime required:

  TypeScript / JavaScript   exports_declared, sibling_imports_ok,
                            no_phantom_imports, no_prose_leak, not_stub
  Go / Rust / Java / C#     declares_code, imports_resolve, no_prose_leak,
                            not_stub
  anything else             declares_code, no_prose_leak, not_stub

Checks that only make sense per-language are not run on other languages: a
relative-import check on Go would fail every file and turn the score into noise.
"""
from __future__ import annotations

import json
import re
from pathlib import PurePosixPath

from . import execution

TS_LANGS = {"typescript", "javascript"}
IMPORT_CHECKED = {"go", "rust", "java", "csharp"}
JVM_SAFE_PREFIXES = ("java.", "javax.", "jdk.", "sun.")
CS_SAFE_PREFIXES = ("System", "Microsoft", "Windows", "Newtonsoft")

STUB_PATTERNS = (
    re.compile(r"\bnot implemented\b", re.I),
    re.compile(r"\bunimplemented\b", re.I),
    re.compile(r"placeholder\s+for\b", re.I),
    re.compile(r"\bcoming soon\b", re.I),
    re.compile(r"\blorem ipsum\b", re.I),
    re.compile(r"throw new Error\(['\"]not", re.I),
    re.compile(r"TODO:\s*Implement"),
    re.compile(r"\bpass\s*$", re.M),
    re.compile(r"\braise NotImplementedError\b"),
)

FENCE_RE = re.compile(r"^\s*```", re.M)
PROSE_RE = re.compile(
    r"^\s*(?:\*\*[^*]+\*\*|Note:|NOTE:|Explanation:|Here's|Below is|"
    r"In this (?:solution|implementation|file|module|example)|"
    r"This (?:code|file|module|implementation|class|function) "
    r"(?:defines|implements|handles|provides|is|shows))")
# A prose line has words but no code punctuation.
CODE_PUNCT = set(";{}()=<>[]")

EXPORT_RE = re.compile(
    r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:const|let|var|function|class|"
    r"interface|type|enum|abstract|declare)\b|"
    r"\bmodule\.exports\b|\bexport\s*\{|\bexports\.[A-Za-z_$]")
REL_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(?\s*)['"](\.{1,2}/[^'"]*)['"]""")
BARE_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"]([^'".][^'"]*)['"]""")

GO_IMPORT_BLOCK = re.compile(r"\bimport\s*\(([^)]*)\)", re.S)
GO_IMPORT_ONE = re.compile(r'\bimport\s+(?:[\w.]+\s+)?"([^"]+)"')
GO_MODULE = re.compile(r"^\s*module\s+(\S+)", re.M)

JAVA_IMPORT = re.compile(r"^\s*import\s+([\w.]+)\s*;", re.M)
JAVA_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)

CS_USING = re.compile(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;", re.M)
CS_NAMESPACE = re.compile(r"^\s*namespace\s+([\w.]+)")

RUST_USE = re.compile(r"^\s*(?:pub\s+)?use\s+(crate|self|super)\b", re.M)
RUST_MOD = re.compile(r"^\s*(?:pub\s+)?mod\s+([A-Za-z_]\w*)\s*;", re.M)

DECLARES = {
    "go": re.compile(r"\bfunc\s+\w+|^\s*type\s+\w+|\bvar\s+\w+", re.M),
    "rust": re.compile(r"\bfn\s+\w+|\bstruct\s+\w+|\bimpl\b|\blet\s+\w+", re.M),
    "java": re.compile(r"\b(?:class|interface|enum|record)\s+\w+|\b\w+\s*=\s*"),
    "csharp": re.compile(r"\b(?:class|struct|interface|record)\s+\w+|\bvar\s+\w+|\b\w+\s*=\s*"),
}
DEFAULT_DECLARES = re.compile(r"\S")


def _norm(text: str) -> str:
    return (text or "").replace("\r\n", "\n")


def _path(value: str) -> str:
    """POSIX-ish relative path with no leading './' and no escapes."""
    parts = [p for p in PurePosixPath(_norm(value).strip()).parts if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return ""
    return "/".join(parts)


def _is_stub(code: str) -> bool:
    return any(p.search(code) for p in STUB_PATTERNS)


def _has_prose(code: str) -> bool:
    if FENCE_RE.search(code):
        return True
    for line in code.split("\n"):
        if not line.strip():
            continue
        if PROSE_RE.match(line) and not (CODE_PUNCT & set(line)):
            return True
    return False


# An entry file is expected to *use* the modules, not export anything, so the
# exports check does not apply to it. VACA's original check ran on generated
# modules, where every file was supposed to expose something.
def _is_entry(path: str) -> bool:
    return execution.is_entry_name(path)


def _declares_code(code: str, language: str) -> bool:
    pattern = DECLARES.get(language, DEFAULT_DECLARES)
    return bool(code.strip()) and bool(pattern.search(code))


def _candidates(spec: str, paths: set[str], importing: str) -> bool:
    """Resolve a relative import against the file set (extension-less too)."""
    base = PurePosixPath(importing).parent
    target = _path(str((base / spec).as_posix())) if base.as_posix() not in ("", ".") \
        else _path(spec)
    if not target:
        return False
    suffixes = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json",
                "/index.ts", "/index.tsx", "/index.js", "/index.jsx")
    return any((target + suffix) in paths for suffix in suffixes)


def _manifest_deps(files: dict[str, str]) -> set[str]:
    deps: set[str] = set()
    for path, content in files.items():
        if not path.endswith("package.json"):
            continue
        try:
            manifest = json.loads(content)
        except json.JSONDecodeError:
            continue
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            deps.update((manifest.get(key) or {}).keys())
    return deps


def _bare_import_ok(spec: str, deps: set[str]) -> bool:
    if spec.startswith("node:"):
        return True
    root = spec.split("/")[0]
    if root.startswith("@"):
        root = "/".join(spec.split("/")[:2])
    # A manifest in the set is the authority when there is one: a capture from a
    # real export knows its own dependencies, and guessing from a hardcoded list
    # would flag every legitimate package.
    if deps:
        return root in deps
    return True


def _go_imports_resolve(files: dict[str, str], path: str, code: str) -> bool:
    module = ""
    for candidate, content in files.items():
        match = GO_MODULE.search(content)
        if candidate.endswith("go.mod") and match:
            module = match.group(1)
            break
    if not module:
        return True  # nothing to resolve against; not a violation
    specs = [m.group(1) for m in GO_IMPORT_ONE.finditer(code)]
    for block in GO_IMPORT_BLOCK.finditer(code):
        specs.extend(re.findall(r'"([^"]+)"', block.group(1)))
    for spec in specs:
        if not spec.startswith(module.rstrip("/") + "/"):
            continue
        local = _path(spec[len(module.rstrip("/")) + 1:])
        if not local:
            return False
        if not any(p == local or p.startswith(local + "/") for p in files):
            return False
    return True


def _java_imports_resolve(files: dict[str, str], code: str) -> bool:
    declared = set()
    for content in files.values():
        declared.update(m.group(1) for m in JAVA_PACKAGE.finditer(content))
    for match in JAVA_IMPORT.finditer(code):
        name = match.group(1)
        if name.startswith(JVM_SAFE_PREFIXES):
            continue
        package = name.rsplit(".", 1)[0] if "." in name else name
        if package in declared or any(p.startswith(package + ".") for p in declared):
            continue
        return False
    return True


def _csharp_imports_resolve(files: dict[str, str], code: str) -> bool:
    namespaces = set()
    for content in files.values():
        namespaces.update(m.group(1) for m in CS_NAMESPACE.finditer(content))
    for match in CS_USING.finditer(code):
        name = match.group(1)
        if name.split(".")[0] in CS_SAFE_PREFIXES:
            continue
        if name in namespaces or any(ns.startswith(name + ".") for ns in namespaces):
            continue
        return False
    return True


def _rust_imports_resolve(files: dict[str, str], path: str, code: str) -> bool:
    declared = {m.group(1) for m in RUST_MOD.finditer(code)}
    directory = PurePosixPath(path).parent
    for name in declared:
        sibling = _path((directory / f"{name}.rs").as_posix())
        nested = _path((directory / name / "mod.rs").as_posix())
        if sibling not in files and nested not in files:
            return False
    return True


def score_files(files: list[dict], language: str = "") -> dict:
    """Score a file set for adherence.

    `files` is `[{path, content}]`. Returns the share of checks that passed, how
    many files passed every check, and a failure histogram — the shape VACA's
    scaffold experiment already reports, so a trainer number and an app number
    mean the same thing.
    """
    normalised: dict[str, str] = {}
    for entry in files or []:
        path = _path(entry.get("path", ""))
        if path:
            normalised[path] = _norm(entry.get("content", ""))
    if not normalised:
        return {"score": 0.0, "fully_adherent": 0, "file_count": 0, "failures": {},
                "per_file": {}}

    deps = _manifest_deps(normalised)
    paths = set(normalised)
    failures: dict[str, int] = {}
    per_file: dict[str, dict] = {}
    passed = checks = fully = 0

    for path, code in normalised.items():
        suffix = PurePosixPath(path).suffix.lower()
        lang = language.lower() if len(normalised) == 1 and language else ""
        is_ts = suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
        results: list[tuple[str, bool]] = []
        if is_ts:
            relative = [m.group(1) for m in REL_IMPORT_RE.finditer(code)]
            bare = [m.group(1) for m in BARE_IMPORT_RE.finditer(code)]
            results = [
                ("sibling_imports_ok",
                 all(_candidates(spec, paths, path) for spec in relative)),
                ("no_phantom_imports",
                 all(_bare_import_ok(spec, deps) for spec in bare)),
            ]
            if not _is_entry(path):
                results.insert(0, ("exports_declared", bool(EXPORT_RE.search(code))))
        elif lang in IMPORT_CHECKED or suffix in (".go", ".rs", ".java", ".cs"):
            resolved = True
            if suffix == ".go" or lang == "go":
                resolved = _go_imports_resolve(normalised, path, code)
            elif suffix == ".java" or lang == "java":
                resolved = _java_imports_resolve(normalised, code)
            elif suffix == ".cs" or lang == "csharp":
                resolved = _csharp_imports_resolve(normalised, code)
            elif suffix == ".rs" or lang == "rust":
                resolved = _rust_imports_resolve(normalised, path, code)
            results = [
                ("declares_code", _declares_code(code, lang or {
                    ".go": "go", ".rs": "rust", ".java": "java", ".cs": "csharp",
                }.get(suffix, ""))),
                ("imports_resolve", resolved),
            ]
        else:
            results = [("declares_code", _declares_code(code, lang))]

        results.append(("no_prose_leak", not _has_prose(code)))
        results.append(("not_stub", not _is_stub(code)))

        failed = [name for name, ok in results if not ok]
        for name, ok in results:
            checks += 1
            if ok:
                passed += 1
            else:
                failures[name] = failures.get(name, 0) + 1
        per_file[path] = {"passed": len(results) - len(failed),
                          "failed": failed}
        if not failed:
            fully += 1

    return {
        "score": round(passed / checks, 4) if checks else 0.0,
        "fully_adherent": fully,
        "file_count": len(normalised),
        "failures": failures,
        "per_file": per_file,
    }
