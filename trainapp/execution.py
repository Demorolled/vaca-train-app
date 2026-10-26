"""execution — the Execution Schema Layer.

The harness deliberately knows nothing about a language's semantics. It knows
exactly three things per language:

  1. which executable proves the toolchain is installed (`which` / `Get-Command`)
  2. which argv checks the file compiles / parses
  3. which argv runs it

Everything else is the LLM's job: it gets the file, the command that was run,
the exit code and the output, and it fixes the code.

Steps are argv lists, never shell strings, so nothing here depends on Bash or
PowerShell quoting. `install` keeps the one-line setup command for each OS so a
missing toolchain is reported with a way out instead of a bare failure.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

IS_WINDOWS = os.name == "nt"
PLATFORM_LABEL = "Windows" if IS_WINDOWS else "Linux"
MAX_STREAM = 20_000


@dataclass(frozen=True)
class Toolchain:
    language: str
    extensions: tuple[str, ...]
    bins: tuple[str, ...]
    version_args: tuple[str, ...]
    check_steps: tuple[tuple[str, ...], ...]
    run_steps: tuple[tuple[str, ...], ...]
    install: dict[str, str]
    note: str = ""


TOOLCHAINS: dict[str, Toolchain] = {
    "python": Toolchain(
        language="python",
        extensions=(".py",),
        bins=("python3", "python"),
        version_args=("--version",),
        check_steps=(("{bin}", "-m", "py_compile", "{file}"),),
        run_steps=(("{bin}", "{file}"),),
        install={
            "linux": "sudo apt-get install -y python3",
            "windows": "winget install Python.Python.3.12",
        },
    ),
    "javascript": Toolchain(
        language="javascript",
        extensions=(".js", ".mjs", ".cjs"),
        bins=("node", "nodejs"),
        version_args=("--version",),
        check_steps=(("{bin}", "--check", "{file}"),),
        run_steps=(("{bin}", "{file}"),),
        install={
            "linux": "sudo apt-get install -y nodejs",
            "windows": "winget install OpenJS.NodeJS.LTS",
        },
    ),
    "typescript": Toolchain(
        language="typescript",
        extensions=(".ts",),
        bins=("node", "nodejs"),
        version_args=("--version",),
        # Node >= 22.6 strips types at load time; the base app does not ship tsc.
        run_steps=(("{bin}", "{file}"),),
        check_steps=(),
        install={
            "linux": "sudo apt-get install -y nodejs",
            "windows": "winget install OpenJS.NodeJS.LTS",
        },
        note="Runs via Node's built-in type stripping (Node >= 22.6); no tsc gate.",
    ),
    "go": Toolchain(
        language="go",
        extensions=(".go",),
        bins=("go",),
        version_args=("version",),
        check_steps=(("{bin}", "build", "-o", "{dir}/.node-bin", "{file}"),),
        run_steps=(("{dir}/.node-bin",),),
        install={
            "linux": "sudo apt-get install -y golang-go",
            "windows": "winget install GoLang.Go",
        },
    ),
    "rust": Toolchain(
        language="rust",
        extensions=(".rs",),
        bins=("rustc",),
        version_args=("--version",),
        check_steps=(
            ("{bin}", "--edition", "2021", "--crate-type", "lib", "--emit=metadata",
             "-o", "{dir}/.node-check.rmeta", "{file}"),
        ),
        run_steps=(
            ("{bin}", "--edition", "2021", "{file}", "-o", "{dir}/.node-bin"),
            ("{dir}/.node-bin",),
        ),
        install={
            "linux": "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
            "windows": "winget install Rustlang.Rustup",
        },
    ),
    "c": Toolchain(
        language="c",
        extensions=(".c",),
        bins=("gcc", "clang", "cc"),
        version_args=("--version",),
        check_steps=(("{bin}", "-fsyntax-only", "-std=c11", "{file}"),),
        run_steps=(
            ("{bin}", "-std=c11", "{file}", "-o", "{dir}/.node-bin"),
            ("{dir}/.node-bin",),
        ),
        install={
            "linux": "sudo apt-get install -y build-essential",
            "windows": "winget install BrechtSanders.WinLibs.POSIX.UCRT",
        },
    ),
    "cpp": Toolchain(
        language="cpp",
        extensions=(".cpp", ".cc", ".cxx"),
        bins=("g++", "clang++", "c++"),
        version_args=("--version",),
        check_steps=(("{bin}", "-fsyntax-only", "-std=c++17", "{file}"),),
        run_steps=(
            ("{bin}", "-std=c++17", "{file}", "-o", "{dir}/.node-bin"),
            ("{dir}/.node-bin",),
        ),
        install={
            "linux": "sudo apt-get install -y build-essential",
            "windows": "winget install BrechtSanders.WinLibs.POSIX.UCRT",
        },
    ),
    "java": Toolchain(
        language="java",
        extensions=(".java",),
        bins=("javac",),
        version_args=("-version",),
        check_steps=(("{bin}", "-d", "{dir}", "{file}"),),
        run_steps=(("java", "-cp", "{dir}", "{java_main}"),),
        install={
            "linux": "sudo apt-get install -y openjdk-17-jdk-headless",
            "windows": "winget install Microsoft.OpenJDK.17",
        },
        note="The file is written under its public class name, so the launcher resolves it.",
    ),
    "ruby": Toolchain(
        language="ruby",
        extensions=(".rb",),
        bins=("ruby",),
        version_args=("--version",),
        check_steps=(("{bin}", "-c", "{file}"),),
        run_steps=(("{bin}", "{file}"),),
        install={
            "linux": "sudo apt-get install -y ruby-full",
            "windows": "winget install RubyInstallerTeam.Ruby",
        },
    ),
    "php": Toolchain(
        language="php",
        extensions=(".php",),
        bins=("php",),
        version_args=("--version",),
        check_steps=(("{bin}", "-l", "{file}"),),
        run_steps=(("{bin}", "{file}"),),
        install={
            "linux": "sudo apt-get install -y php-cli",
            "windows": "winget install PHP.PHP",
        },
    ),
    "kotlin": Toolchain(
        language="kotlin",
        extensions=(".kt", ".kts"),
        bins=("kotlinc", "kotlinc-jvm"),
        version_args=("-version",),
        check_steps=(("{bin}", "{file}", "-include-runtime", "-d", "{dir}/.node.jar"),),
        run_steps=(("java", "-jar", "{dir}/.node.jar"),),
        install={
            "linux": "sudo snap install kotlin --classic",
            "windows": "winget install JetBrains.Kotlin",
        },
    ),
    "swift": Toolchain(
        language="swift",
        extensions=(".swift",),
        bins=("swiftc",),
        version_args=("--version",),
        check_steps=(("{bin}", "-typecheck", "{file}"),),
        run_steps=(
            ("{bin}", "{file}", "-o", "{dir}/.node-bin"),
            ("{dir}/.node-bin",),
        ),
        install={
            "linux": "curl -O https://download.swift.org/swiftly/linux/swiftly-$(uname -m).tar.gz && tar zxf swiftly-$(uname -m).tar.gz && ./swiftly init --quiet-shell-followup",
            "windows": "winget install --id Swift.Toolchain -e",
        },
    ),
    "csharp": Toolchain(
        language="csharp",
        extensions=(".cs",),
        bins=("dotnet",),
        version_args=("--version",),
        # A .cs file is not a project: `dotnet build` refuses a directory with
        # no .csproj (MSB1003). run_node scaffolds a throwaway project that
        # compiles the file by absolute path, so every caller — the node
        # runner, validation, the tournament, the battery — works the same way
        # and the source directory stays clean.
        check_steps=(("{bin}", "build", "{project}", "--nologo", "-v", "q",
                      "-o", "{proj}/out"),),
        run_steps=(("{bin}", "{proj}/out/node.dll"),),
        install={
            "linux": "sudo apt-get install -y dotnet-sdk-8.0",
            "windows": "winget install Microsoft.DotNet.SDK.8",
        },
        note="Built through a generated .csproj; top-level statements and Main both run.",
    ),
}

CSHARP_PROJECT = """<Project Sdk=\"Microsoft.NET.Sdk\">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>{tfm}</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>disable</Nullable>
    <AssemblyName>node</AssemblyName>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include=\"{source}\" />
  </ItemGroup>
</Project>
"""

# Toolchain installers that are not on a non-login shell's PATH.
BIN_SEARCH_DIRS = (
    Path.home() / ".cargo" / "bin",
    Path.home() / ".dotnet",
    Path.home() / ".local" / "bin",
    Path.home() / ".local" / "share" / "swiftly" / "bin",
    Path.home() / "snap" / "bin",
    Path("/snap/bin"),
)

EXTENSION_INDEX = {
    ext: name for name, spec in TOOLCHAINS.items() for ext in spec.extensions
}


@dataclass
class StepResult:
    argv: list[str]
    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


@dataclass
class RunResult:
    ok: bool
    language: str = ""
    command: str = ""
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    error: str = ""
    steps: list[StepResult] = field(default_factory=list)

    @property
    def output(self) -> str:
        """stdout + stderr, the text the LLM is shown."""
        parts = [p for p in (self.stdout.strip(), self.stderr.strip()) if p]
        return "\n".join(parts)[:MAX_STREAM]

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "language": self.language,
            "platform": PLATFORM_LABEL,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout[-MAX_STREAM:],
            "stderr": self.stderr[-MAX_STREAM:],
            "output": self.output,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "steps": [
                {
                    "command": s.command,
                    "exit_code": s.exit_code,
                    "timed_out": s.timed_out,
                    "duration_ms": s.duration_ms,
                }
                for s in self.steps
            ],
        }


@dataclass
class Probe:
    language: str
    available: bool
    bin: str = ""
    version: str = ""
    install: str = ""
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "language": self.language,
            "available": self.available,
            "bin": self.bin,
            "version": self.version,
            "install": self.install,
            "error": self.error,
            "note": TOOLCHAINS[self.language].note if self.language in TOOLCHAINS else "",
        }


def detect_language(filename: str | Path) -> str:
    """Language id from the file extension, or "" when nothing owns it."""
    return EXTENSION_INDEX.get(Path(filename).suffix.lower(), "")


# Compile-only snippets are common in the Rosetta corpus: a helper function or
# a class with no entry point. They build but cannot be launched, so calling
# them "verified programs" is what put them in tournament seed lists.
MAIN_PATTERNS = {
    "go": re.compile(r"\bfunc\s+main\s*\("),
    "rust": re.compile(r"\bfn\s+main\s*\("),
    "c": re.compile(r"\bmain\s*\("),
    "cpp": re.compile(r"\bmain\s*\("),
    "java": re.compile(r"\bmain\s*\(\s*(?:final\s+)?String\b"),
    "kotlin": re.compile(r"\bfun\s+main\s*\("),
    "csharp": re.compile(r"\b(?:static\s+)?(?:async\s+)?(?:void|int|Task)\s+Main\s*\("),
}
# Languages whose files are scripts: the file itself is the entry point.
SCRIPT_LANGUAGES = {"python", "javascript", "typescript", "ruby", "php", "swift"}


def _strip_code(text: str, language: str = "") -> str:
    """Drop comments and string literals so braces/parens can be counted."""
    out: list[str] = []
    index, size = 0, len(text)
    while index < size:
        char = text[index]
        pair = text[index:index + 2]
        if pair == "//":
            index = text.find("\n", index) + 1 or size
        elif pair == "/*":
            end = text.find("*/", index + 2)
            index = size if end < 0 else end + 2
        elif char == "'" and language == "rust" and text.find("'", index + 1, index + 6) < 0:
            # `&'static str` is a lifetime, not a string. Treating it as a
            # literal ran to the end of the file and hid `fn main`, so every
            # Rust program with a borrowed field was compiled as a library.
            out.append(char)
            index += 1
        elif char in "\"'":
            quote, index = char, index + 1
            while index < size and text[index] != quote:
                index += 2 if text[index] == "\\" else 1
            index += 1
            out.append("\"\"")
        else:
            out.append(char)
            index += 1
    return "".join(out)


def _has_top_level_statement(code: str) -> bool:
    """C# top-level statements: a `;` outside every brace."""
    depth = 0
    for char in _strip_code(code):
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char == ";" and depth == 0:
            return True
    return False


_PUBLIC_TYPE = re.compile(
    r"\bpublic\s+(?:(?:final|abstract|strictfp)\s+)*"
    r"(?:class|interface|enum|record)\s+([A-Za-z_$][A-Za-z0-9_$]*)")
# A package-private class is still launched by its own name (`java Doors`), so
# the public-type rule only decides which name wins when there is a choice.
_ANY_TYPE = re.compile(r"\b(?:class|interface|enum|record)\s+([A-Za-z_$][A-Za-z0-9_$]*)")


_JAVA_PACKAGE = re.compile(r"^\s*package\s+([A-Za-z_][\w.]*)\s*;", re.M)
_JAVA_TYPE = re.compile(r"\b(?:class|enum|record)\s+([A-Za-z_$][\w$]*)")
_JAVA_MAIN = re.compile(r"\bstatic\b[^;{}()]*\bvoid\s+main\s*\(\s*(?:final\s+)?String\b")


def _brace_end(text: str, open_index: int) -> int:
    """Index just past the brace matching `text[open_index] == '{'`."""
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(text)


def java_main_class(code: str) -> str:
    """Fully-qualified class to launch: the one that declares `main`.

    `java -cp dir Foo` only resolves `Foo` when it is in the default package;
    `package programas;` puts the class file in `dir/programas/` and the
    launcher needs `programas.Foo`.

    A type's body ends at its own closing brace, not at the next `class`
    keyword: a nested `class Item` declared under the outer class would
    otherwise swallow the outer class's `main` and be launched by name.
    """
    text = code or ""
    package = _JAVA_PACKAGE.search(text)
    prefix = f"{package.group(1)}." if package else ""
    for match in _JAVA_TYPE.finditer(text):
        start, name = match.start(), match.group(1)
        open_index = text.find("{", match.end())
        if open_index < 0:
            continue
        if _JAVA_MAIN.search(text[start:_brace_end(text, open_index)]):
            return prefix + name
    return prefix + source_stem("java", text)


def source_stem(language: str, code: str) -> str:
    """File stem the code requires, or `candidate` when any name will do.

    Java's launcher takes a class name and the public class must match the file
    name, so writing every file as `candidate.java` rejected valid programs with
    "Could not find or load main class candidate".
    """
    if language == "java":
        match = _PUBLIC_TYPE.search(code or "") or _ANY_TYPE.search(code or "")
        if match:
            return match.group(1)
    return "candidate"


def program_entry_point(language: str, code: str) -> bool:
    """True when the file is runnable as a program, not just compilable."""
    if language in SCRIPT_LANGUAGES:
        return True
    pattern = MAIN_PATTERNS.get(language)
    if not pattern:
        return True
    # Strip first: a commented-out `static void Main()` is not an entry point.
    stripped = _strip_code(code or "", language)
    if pattern.search(stripped):
        return True
    return language == "csharp" and _has_top_level_statement(stripped)


def resolve_bin(language: str) -> str:
    spec = TOOLCHAINS.get(language)
    if not spec:
        return ""
    for candidate in spec.bins:
        found = shutil.which(candidate)
        if found:
            return found
        for directory in BIN_SEARCH_DIRS:
            probe = directory / (candidate + (".exe" if IS_WINDOWS else ""))
            if probe.is_file():
                return str(probe)
    return ""


def install_hint(language: str) -> str:
    spec = TOOLCHAINS.get(language)
    if not spec:
        return ""
    return spec.install.get("windows" if IS_WINDOWS else "linux", "")


def probe(language: str, timeout_s: float = 10) -> Probe:
    """`which rustc` / `Get-Command rustc`: is the toolchain usable?"""
    spec = TOOLCHAINS.get(language)
    if not spec:
        return Probe(language, False, error=f"no toolchain spec for {language!r}")
    binary = resolve_bin(language)
    if not binary:
        return Probe(language, False, install=install_hint(language),
                     error=f"{' / '.join(spec.bins)} not found on PATH")
    try:
        done = subprocess.run(
            [binary, *spec.version_args],
            capture_output=True, text=True, errors="replace", timeout=timeout_s,
            env=_child_env(),
        )
        version = (done.stdout or done.stderr or "").strip().splitlines()
        return Probe(language, True, bin=binary,
                     version=version[0][:120] if version else "")
    except (OSError, subprocess.SubprocessError) as err:
        return Probe(language, False, bin=binary, error=str(err)[:300])


def probe_all() -> list[dict]:
    return [probe(name).as_dict() for name in TOOLCHAINS]


def _child_env() -> dict:
    env = dict(os.environ)
    # Keep toolchain output readable and unbuffered on both OSes.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    # `dotnet build` otherwise prints a first-run banner and telemetry notice.
    env.setdefault("DOTNET_CLI_TELEMETRY_OPTOUT", "1")
    env.setdefault("DOTNET_NOLOGO", "1")
    return env


# ─── Multi-file (scaffold) coverage ────────────────────────────────────────
# `run_node` proves one file. A real app is a set of files, and the defects a
# set can have — an import of a sibling nobody wrote, a class the launcher
# cannot find, two files declaring the same symbol — are invisible to a
# per-file gate. `run_files` builds the whole set the way the language toolchain
# actually does: all sources together, one entry point.

TS_GLOBALS = """// Minimal ambient shims for the Node globals a generated app uses, so a set
// can be typechecked without @types/node installed. Only those globals are
// erased; every type error in the app's own files still fails the gate.
declare var process: any;
declare var require: any;
declare var module: any;
declare var exports: any;
declare var __dirname: string;
declare var __filename: string;
declare var Buffer: any;
declare var global: any;
declare var setTimeout: any;
declare var setInterval: any;
declare var clearInterval: any;
declare var clearTimeout: any;
declare namespace NodeJS {
  type Timeout = any;
  type ProcessEnv = Record<string, string | undefined>;
}
"""

TS_CONFIG = """{
  \"compilerOptions\": {
    \"noEmit\": true,
    \"skipLibCheck\": true,
    \"strict\": false,
    \"target\": \"es2020\",
    \"module\": \"esnext\",
    \"moduleResolution\": \"bundler\",
    \"allowImportingTsExtensions\": true,
    \"types\": [],
    \"lib\": [\"es2020\", \"dom\"]
  },
  \"include\": [\"**/*.ts\", \"**/*.tsx\"]
}
"""

CSHARP_SET_PROJECT = """<Project Sdk=\"Microsoft.NET.Sdk\">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>{tfm}</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>disable</Nullable>
    <AssemblyName>node</AssemblyName>
  </PropertyGroup>
</Project>
"""

# Where a `tsc` lives when the app tree ships one (VACA's node_modules) rather
# than the desktop having a global install.
TSC_SEARCH_DIRS = (
    Path.home() / "Desktop" / "visual-ai-architect" / "node_modules" / ".bin",
)

# A file that *is* the program, by convention. The target of a scaffold task is
# usually a module, so launching the target would run the wrong file: these are
# the only names that may be launched when the target carries one.
ENTRY_STEMS = {"main", "index", "app", "server", "cli", "entry", "start"}


def is_entry_name(path: str | Path) -> bool:
    return Path(path).stem.lower() in ENTRY_STEMS


SET_SCRIPT_LANGS = {"python", "javascript", "php", "ruby"}
SET_BUILD_LANGS = {"go", "rust", "c", "cpp", "java", "kotlin", "csharp", "swift",
                   "typescript"}


def resolve_tsx() -> str:
    """A TypeScript runner, so a set that only prints can be observed.

    `tsc --noEmit` proves a set typechecks; it cannot show what the program
    does. `tsx` resolves the extensionless imports these sets use, so the
    observable probe can run the entry the way the app would.
    """
    found = shutil.which("tsx")
    if found:
        return found
    for directory in TSC_SEARCH_DIRS:
        probe = directory.parent / ".bin" / ("tsx.cmd" if IS_WINDOWS else "tsx")
        if probe.is_file():
            return str(probe)
    return ""


def resolve_tsc() -> str:
    found = shutil.which("tsc")
    if found:
        return found
    for directory in TSC_SEARCH_DIRS:
        probe = directory / ("tsc.cmd" if IS_WINDOWS else "tsc")
        if probe.is_file():
            return str(probe)
    return ""


def safe_relative(path: str) -> str:
    """A path a file set may be written to: relative, no traversal, no absolutes."""
    text = (path or "").replace("\\", "/").strip()
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if not parts or text.startswith("/") or any(p == ".." for p in parts):
        return ""
    if re.match(r"^[A-Za-z]:", parts[0]):
        return ""
    return "/".join(parts)


def _entry_for(lang: str, paths: list[str], contents: dict[str, str], entry: str) -> str:
    """The file the toolchain launches."""
    wanted = safe_relative(entry)
    if wanted and wanted in paths:
        return wanted
    if lang in ("java", "csharp", "c", "cpp", "go", "rust"):
        pattern = MAIN_PATTERNS.get(lang)
        if pattern:
            for path in sorted(paths):
                text = contents.get(path, "")
                if pattern.search(_strip_code(text)) or (
                        lang == "csharp" and _has_top_level_statement(_strip_code(text))):
                    return path
    # An app's entry is conventionally main.* / index.* / app.* at the top.
    def rank(path: str) -> tuple:
        return (path.count("/"), 0 if is_entry_name(path) else 1, path)
    return sorted(paths, key=rank)[0]


def _sources(paths: list[str], suffixes: tuple[str, ...]) -> list[str]:
    return [p for p in sorted(paths) if Path(p).suffix.lower() in suffixes]


def run_files(files: list[dict] | dict[str, str], language: str,
              entry: str = "", timeout_s: float = 60,
              compile_only: bool = False,
              args: list[str] | None = None) -> RunResult:
    """Write a whole file set to a scratch dir, build it, and run its entry.

    TypeScript is typechecked with `tsc --noEmit` (no runtime step): a set that
    passes it can be compiled by the export pipeline, which is the claim being
    proven. Java, Kotlin, C, C++, Swift, Go and C# build all sources together;
    Python, JS, PHP and Ruby run the entry file with the siblings importable.
    """
    lang = (language or "").lower()
    if lang == "js":
        lang = "javascript"
    if lang == "ts":
        lang = "typescript"
    items = files.items() if isinstance(files, dict) else [
        (f.get("path", ""), f.get("content", "")) for f in (files or [])]
    contents: dict[str, str] = {}
    for raw_path, content in items:
        path = safe_relative(str(raw_path))
        if path:
            contents[path] = str(content or "")
    if not contents:
        return RunResult(ok=False, language=lang, error="empty file set")
    if lang not in SET_SCRIPT_LANGS and lang not in SET_BUILD_LANGS:
        return RunResult(ok=False, language=lang,
                         error=f"no multi-file build for {language!r}")

    binary = resolve_bin("javascript" if lang in ("typescript", "javascript") else lang)
    if lang in ("typescript", "javascript"):
        binary = binary or (resolve_tsc() if lang == "typescript" else "")
    if not binary:
        hint = install_hint(lang)
        return RunResult(ok=False, language=lang,
                         error=f"toolchain missing for {lang}" + (f" — install with: {hint}" if hint else ""))

    scratch = Path(tempfile.mkdtemp(prefix="vaca-set-"))
    try:
        for path, content in contents.items():
            target = scratch / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        paths = sorted(contents)
        entry_path = _entry_for(lang, paths, contents, entry)
        plan = _set_plan(lang, scratch, entry_path, paths, contents, binary, args)
        if isinstance(plan, RunResult):
            return plan
        return _run_plan(lang, plan, scratch, timeout_s, compile_only)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _set_plan(lang: str, scratch: Path, entry: str, paths: list[str],
              contents: dict[str, str], binary: str,
              args: list[str] | None = None) -> list[tuple[list[str], Path]]:
    """(check steps, run steps) for a file set, as argv + cwd.

    `args` is set only by a caller that knows the invocation — the observable
    probe with `--help` or a fixture argument, the builder's `run` command, the
    orchestra's blueprint. Without it every plan stays exactly as it was, so
    scoring and the battery are unaffected.
    """
    tail = list(args or [])
    runnable = Path(scratch / entry)
    if lang == "python":
        return [([binary, "-m", "py_compile", entry], scratch),
                ([binary, entry, *tail], scratch)]
    if lang == "javascript":
        return [([binary, "--check", entry], scratch),
                ([binary, entry, *tail], scratch)]
    if lang == "php":
        return [([binary, "-l", entry], scratch), ([binary, entry, *tail], scratch)]
    if lang == "ruby":
        return [([binary, "-c", entry], scratch), ([binary, entry, *tail], scratch)]
    if lang == "typescript":
        (scratch / "tsconfig.json").write_text(TS_CONFIG, encoding="utf-8")
        (scratch / "vaca-globals.d.ts").write_text(TS_GLOBALS, encoding="utf-8")
        tsc = resolve_tsc()
        if not tsc:
            return RunResult(ok=False, language=lang,
                             error="tsc not found (no global install, no VACA node_modules)")
        plan = [([tsc, "-p", str(scratch / "tsconfig.json"), "--pretty", "false"],
                 scratch)]
        if args is not None:
            runner = resolve_tsx()
            if not runner:
                return RunResult(ok=False, language=lang,
                                 error="tsx not found: a TypeScript set cannot be run")
            plan.append(([runner, entry, *tail], scratch))
        return plan
    if lang == "go":
        if "go.mod" not in paths:
            (scratch / "go.mod").write_text("module node\n\ngo 1.21\n", encoding="utf-8")
        return [([binary, "build", "-o", ".node-bin", "."], scratch),
                ([str(scratch / ".node-bin"), *tail], scratch)]
    if lang == "rust":
        if "Cargo.toml" in paths:
            # A cargo workspace is not modelled: a set that ships one is built
            # by `cargo`, which may need the network for its dependencies.
            return RunResult(ok=False, language=lang,
                             error="cargo project not supported for file sets")
        return [([binary, "--edition", "2021", "--crate-type", "lib",
                  "--emit=metadata", "-o", ".node-check.rmeta", entry], scratch),
                ([binary, "--edition", "2021", entry, "-o", ".node-bin"], scratch),
                ([str(scratch / ".node-bin"), *tail], scratch)]
    if lang in ("c", "cpp"):
        suffixes = (".c",) if lang == "c" else (".cpp", ".cc", ".cxx")
        sources = _sources(paths, suffixes) or [entry]
        return [([binary, *sources, "-o", ".node-bin"], scratch),
                ([str(scratch / ".node-bin"), *tail], scratch)]
    if lang == "java":
        sources = _sources(paths, (".java",))
        main_class = java_main_class(contents.get(entry, ""))
        return [([binary, "-d", ".out", *sources], scratch),
                (["java", "-cp", str(scratch / ".out"), main_class, *tail], scratch)]
    if lang == "kotlin":
        sources = _sources(paths, (".kt", ".kts"))
        return [([binary, *sources, "-include-runtime", "-d", ".node.jar"], scratch),
                (["java", "-jar", str(scratch / ".node.jar"), *tail], scratch)]
    if lang == "swift":
        sources = _sources(paths, (".swift",))
        return [([binary, *sources, "-o", ".node-bin"], scratch),
                ([str(scratch / ".node-bin"), *tail], scratch)]
    if lang == "csharp":
        project = scratch / "node.csproj"
        project.write_text(CSHARP_SET_PROJECT.format(tfm=_dotnet_tfm(binary)),
                           encoding="utf-8")
        return [([binary, "build", str(project), "--nologo", "-v", "q",
                  "-o", str(scratch / "out")], scratch),
                ([binary, str(scratch / "out" / "node.dll"), *tail], scratch)]
    return RunResult(ok=False, language=lang, error=f"no multi-file build for {lang!r}")


def _run_plan(lang: str, plan: list[tuple[list[str], Path]], scratch: Path,
              timeout_s: float, compile_only: bool) -> RunResult:
    # Steps past the first are compile+runtime; `compile_only` stops after the
    # first one, which is always the build (or the typecheck).
    steps = list(plan[:1] if compile_only else plan)
    checks = 1 if len(plan) > 1 else 0
    results: list[StepResult] = []
    started = time.monotonic()
    for index, (argv, cwd) in enumerate(steps):
        step_timeout = max(timeout_s, 180) if index < checks else timeout_s
        step_started = time.monotonic()
        try:
            done = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                                  errors="replace", timeout=step_timeout,
                                  env=_child_env(), stdin=subprocess.DEVNULL)
            step = StepResult(argv=argv, command=display_command(argv),
                              exit_code=done.returncode,
                              stdout=(done.stdout or "")[-MAX_STREAM:],
                              stderr=(done.stderr or "")[-MAX_STREAM:],
                              duration_ms=int((time.monotonic() - step_started) * 1000))
        except subprocess.TimeoutExpired:
            step = StepResult(argv=argv, command=display_command(argv), exit_code=None,
                              stdout="", stderr=f"timed out after {step_timeout:g}s",
                              duration_ms=int((time.monotonic() - step_started) * 1000),
                              timed_out=True)
        except OSError as err:
            step = StepResult(argv=argv, command=display_command(argv), exit_code=None,
                              stdout="", stderr=str(err),
                              duration_ms=int((time.monotonic() - step_started) * 1000))
        results.append(step)
        if step.exit_code != 0:
            return RunResult(ok=False, language=lang, command=step.command,
                             exit_code=step.exit_code, stdout=step.stdout,
                             stderr=step.stderr,
                             duration_ms=int((time.monotonic() - started) * 1000),
                             error="timed out" if step.timed_out else "",
                             steps=results)
    last = results[-1]
    return RunResult(ok=True, language=lang, command=last.command,
                     exit_code=last.exit_code, stdout=last.stdout,
                     stderr=last.stderr,
                     duration_ms=int((time.monotonic() - started) * 1000),
                     steps=results)


def _context(path: Path, binary: str) -> dict:
    return {
        "{bin}": binary,
        "{file}": str(path),
        "{dir}": str(path.parent),
        "{stem}": path.stem,
    }


_TFM_CACHE: dict[str, str] = {}


def _dotnet_tfm(binary: str) -> str:
    """Target framework matching the installed SDK; net8.0 when unsure."""
    if binary in _TFM_CACHE:
        return _TFM_CACHE[binary]
    tfm = "net8.0"
    try:
        done = subprocess.run([binary, "--version"], capture_output=True, text=True,
                              timeout=60, stdin=subprocess.DEVNULL)
        major = (done.stdout or "").strip().split(".")[0]
        if major.isdigit():
            tfm = f"net{major}.0"
    except (OSError, subprocess.SubprocessError):
        pass
    _TFM_CACHE[binary] = tfm
    return tfm


def _csharp_project(scratch: Path, source: Path, tfm: str) -> Path:
    """Write a minimal project that compiles `source` from wherever it lives."""
    project = scratch / "node.csproj"
    project.write_text(
        CSHARP_PROJECT.format(tfm=tfm, source=xml_escape(str(source.resolve()))),
        encoding="utf-8")
    return project


def render_step(template: tuple[str, ...], context: dict) -> list[str]:
    argv: list[str] = []
    for token in template:
        for placeholder, value in context.items():
            token = token.replace(placeholder, value)
        argv.append(token)
    return argv


def display_command(argv: list[str]) -> str:
    if IS_WINDOWS:
        return subprocess.list2cmdline(argv)
    return " ".join(shlex.quote(a) for a in argv)


def run_node(path: str | Path, language: str | None = None,
             timeout_s: float = 60, compile_only: bool = False) -> RunResult:
    """Compile-check then run one node file. First failure wins."""
    file_path = Path(path).resolve()
    if not file_path.is_file():
        return RunResult(ok=False, error=f"no such file: {file_path}")
    lang = language or detect_language(file_path)
    if not lang or lang not in TOOLCHAINS:
        return RunResult(
            ok=False,
            error=f"no execution schema for {file_path.name!r} "
                  f"(supported: {', '.join(sorted(TOOLCHAINS))})",
        )

    binary = resolve_bin(lang)
    if not binary:
        hint = install_hint(lang)
        return RunResult(
            ok=False,
            language=lang,
            error=f"toolchain missing: none of {', '.join(TOOLCHAINS[lang].bins)} "
                  f"on PATH" + (f" — install with: {hint}" if hint else ""),
        )

    spec = TOOLCHAINS[lang]
    context = _context(file_path, binary)
    scratch: Path | None = None
    if lang == "csharp":
        scratch = Path(tempfile.mkdtemp(prefix="vaca-cs-"))
        project = _csharp_project(scratch, file_path, _dotnet_tfm(binary))
        context["{proj}"] = str(scratch)
        context["{project}"] = str(project)
    elif lang == "java":
        try:
            context["{java_main}"] = java_main_class(
                file_path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            context["{java_main}"] = context["{stem}"]
    try:
        return _run_steps(spec, context, file_path, lang, timeout_s, compile_only)
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)


def _run_steps(spec: Toolchain, context: dict, file_path: Path, lang: str,
               timeout_s: float, compile_only: bool = False) -> RunResult:
    """Run the check steps then the run steps; first failure wins."""
    steps = list(spec.check_steps) + ([] if compile_only else list(spec.run_steps))
    checks = len(spec.check_steps)
    results: list[StepResult] = []
    started = time.monotonic()

    for index, template in enumerate(steps):
        argv = render_step(template, context)
        # A first `dotnet build` restores and compiles a project; 20 s is plenty
        # for a compiler but not for that, so check steps get a floor.
        step_timeout = max(timeout_s, 120) if index < checks else timeout_s
        step_started = time.monotonic()
        try:
            # errors="replace": a candidate is free to print raw bytes (a C
            # program writing 0x85 is enough), and a strict decode used to take
            # down the whole run instead of failing that one candidate.
            done = subprocess.run(
                argv, cwd=str(file_path.parent), capture_output=True, text=True,
                errors="replace", timeout=step_timeout, env=_child_env(),
                stdin=subprocess.DEVNULL,
            )
            step = StepResult(
                argv=argv,
                command=display_command(argv),
                exit_code=done.returncode,
                stdout=(done.stdout or "")[-MAX_STREAM:],
                stderr=(done.stderr or "")[-MAX_STREAM:],
                duration_ms=int((time.monotonic() - step_started) * 1000),
            )
        except subprocess.TimeoutExpired:
            step = StepResult(
                argv=argv, command=display_command(argv), exit_code=None,
                stdout="", stderr=f"timed out after {step_timeout:g}s",
                duration_ms=int((time.monotonic() - step_started) * 1000),
                timed_out=True,
            )
        except OSError as err:
            step = StepResult(
                argv=argv, command=display_command(argv), exit_code=None,
                stdout="", stderr=str(err),
                duration_ms=int((time.monotonic() - step_started) * 1000),
            )

        results.append(step)
        if step.exit_code != 0:
            return RunResult(
                ok=False,
                language=lang,
                command=step.command,
                exit_code=step.exit_code,
                stdout=step.stdout,
                stderr=step.stderr,
                duration_ms=int((time.monotonic() - started) * 1000),
                error="timed out" if step.timed_out else "",
                steps=results,
            )

    last = results[-1]
    return RunResult(
        ok=True,
        language=lang,
        command=last.command,
        exit_code=last.exit_code,
        stdout=last.stdout,
        stderr=last.stderr,
        duration_ms=int((time.monotonic() - started) * 1000),
        steps=results,
    )
