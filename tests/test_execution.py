"""Execution Schema Layer: detection, argv rendering, real runs, honest failures."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import execution
from trainapp.execution import PLATFORM_LABEL


class TempFileMixin(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, name: str, code: str) -> Path:
        path = self.dir / name
        path.write_text(code, encoding="utf-8")
        return path


class DetectionTests(unittest.TestCase):
    def test_detects_by_extension(self) -> None:
        self.assertEqual(execution.detect_language("main.py"), "python")
        self.assertEqual(execution.detect_language("Main.java"), "java")
        self.assertEqual(execution.detect_language("lib.rs"), "rust")
        self.assertEqual(execution.detect_language("page.php"), "php")

    def test_unknown_extension_has_no_language(self) -> None:
        self.assertEqual(execution.detect_language("notes.txt"), "")
        self.assertEqual(execution.detect_language("Makefile"), "")

    def test_every_extension_maps_to_one_language(self) -> None:
        seen = {}
        for name, spec in execution.TOOLCHAINS.items():
            for ext in spec.extensions:
                self.assertNotIn(ext, seen, f"{ext} owned by {seen.get(ext)} and {name}")
                seen[ext] = name

    def test_schema_covers_both_operating_systems(self) -> None:
        for name, spec in execution.TOOLCHAINS.items():
            self.assertIn("linux", spec.install, f"{name} has no Linux install hint")
            self.assertIn("windows", spec.install, f"{name} has no Windows install hint")
            self.assertTrue(spec.bins, f"{name} has no executable candidates")
            self.assertTrue(spec.run_steps, f"{name} has no run step")


class SourceStemTests(unittest.TestCase):
    def test_java_file_is_named_after_its_public_class(self) -> None:
        code = "public final class Doors { public static void main(String[] a) {} }"
        self.assertEqual(execution.source_stem("java", code), "Doors")
        # Package-private is still launched by name, so it wins over `candidate`.
        self.assertEqual(execution.source_stem("java", "class Plain {}"), "Plain")

    def test_java_main_is_found_in_the_outer_class_not_a_nested_one(self) -> None:
        code = ("public class Inventory {\n"
                "    static class Item { int qty; }\n"
                "    public static void main(String[] args) { Item i = new Item(); }\n"
                "}\n")
        self.assertEqual(execution.java_main_class(code), "Inventory")

    def test_rust_lifetimes_do_not_hide_the_entry_point(self) -> None:
        code = ("struct Item { name: &'static str }\n"
                "fn main() { let i = Item { name: \"x\" }; println!(\"{}\", i.name); }\n")
        self.assertTrue(execution.program_entry_point("rust", code))
        # A single-quoted JS string is still stripped, so this stays language-aware.
        self.assertFalse(execution.program_entry_point(
            "rust", "let t = 'not rust';\nfn helper() {}\n"))
        self.assertEqual(execution.source_stem("java", "System.out.println(1);"),
                         "candidate")
        self.assertEqual(execution.source_stem("go", "package main"), "candidate")


class JavaLaunchTests(unittest.TestCase):
    def test_package_is_included_in_the_launch_name(self) -> None:
        code = ("package programas;\n"
                "public class Iterative {\n"
                "  public static void main(String[] args) { }\n}\n")
        self.assertEqual(execution.java_main_class(code), "programas.Iterative")

    def test_default_package_stays_bare(self) -> None:
        code = "public class Hello { public static void main(String[] a) { } }"
        self.assertEqual(execution.java_main_class(code), "Hello")

    def test_main_class_is_found_behind_a_helper_class(self) -> None:
        code = ("class Util { }\n"
                "class Runner {\n"
                "  public static void main(String args[]) { }\n}\n")
        self.assertEqual(execution.java_main_class(code), "Runner")

    @unittest.skipUnless(shutil.which("javac") and shutil.which("java"),
                         "javac/java not installed")
    def test_packaged_program_runs(self) -> None:
        code = ("package demo;\n"
                "public class Hello {\n"
                "  public static void main(String[] args) { System.out.println(\"pkg\"); }\n"
                "}\n")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "Hello.java"
        path.write_text(code, encoding="utf-8")
        result = execution.run_node(path, "java", timeout_s=60)
        self.assertTrue(result.ok, result.get("stderr") if isinstance(result, dict) else result.stderr)
        self.assertIn("pkg", result.stdout)


class EntryPointTests(unittest.TestCase):
    def test_kotlin_and_go_need_a_main(self) -> None:
        self.assertFalse(execution.program_entry_point(
            "kotlin", "fun oneHundredDoors(): List<Int> { return emptyList() }"))
        self.assertTrue(execution.program_entry_point(
            "kotlin", "fun main() { println(1) }"))
        self.assertFalse(execution.program_entry_point(
            "go", "package main\nfunc helper() {}\n"))
        self.assertTrue(execution.program_entry_point(
            "go", "package main\nfunc main() {}\n"))
        self.assertFalse(execution.program_entry_point("rust", "fn helper() {}\n"))
        self.assertTrue(execution.program_entry_point("rust", "fn main() {}\n"))

    def test_csharp_accepts_main_or_top_level_statements(self) -> None:
        self.assertTrue(execution.program_entry_point(
            "csharp", "class P { static void Main() { } }"))
        self.assertTrue(execution.program_entry_point(
            "csharp", "int[] a = { 1, 2 };\nConsole.WriteLine(a.Length);\n"))
        self.assertFalse(execution.program_entry_point(
            "csharp", "static string Reverse(string s) { return s; }"))

    def test_script_languages_are_always_runnable(self) -> None:
        for language in ("python", "ruby", "javascript", "typescript", "php", "swift"):
            self.assertTrue(execution.program_entry_point(language, "x = 1\n"), language)

    def test_comments_and_strings_do_not_fake_an_entry_point(self) -> None:
        code = '// static void Main() {}\nclass P { static string S = "void Main() {}"; }\n'
        self.assertFalse(execution.program_entry_point("csharp", code))


class RenderingTests(TempFileMixin):
    def test_placeholders_are_filled(self) -> None:
        path = self.write("tool.py", "print(1)\n")
        ctx = execution._context(path, "/usr/bin/python3")
        argv = execution.render_step(("{bin}", "-m", "py_compile", "{file}"), ctx)
        self.assertEqual(argv, ["/usr/bin/python3", "-m", "py_compile", str(path)])

    def test_stem_and_dir_placeholders(self) -> None:
        path = self.write("Game.java", "class Game {}\n")
        ctx = execution._context(path, "/usr/bin/javac")
        self.assertEqual(execution.render_step(("{dir}", "{stem}"), ctx),
                         [str(self.dir), "Game"])

    def test_display_command_is_quoted_on_posix(self) -> None:
        shown = execution.display_command(["python3", "a b.py"])
        if os.name != "nt":
            self.assertIn("'a b.py'", shown)

    def test_platform_label_is_real(self) -> None:
        self.assertIn(PLATFORM_LABEL, ("Linux", "Windows"))


class ProbeTests(unittest.TestCase):
    def test_python_is_available(self) -> None:
        probe = execution.probe("python")
        self.assertTrue(probe.available, probe.error)
        self.assertTrue(probe.bin)
        self.assertEqual(probe.language, "python")

    def test_missing_toolchain_reports_install_hint(self) -> None:
        fake = execution.Toolchain(
            language="python", extensions=(".py",), bins=("definitely-not-a-real-binary",),
            version_args=("--version",), check_steps=(), run_steps=(("{bin}", "{file}"),),
            install={"linux": "apt install python3", "windows": "winget install Python"},
        )
        with mock.patch.dict(execution.TOOLCHAINS, {"python": fake}):
            probe = execution.probe("python")
        self.assertFalse(probe.available)
        self.assertIn("definitely-not-a-real-binary", probe.error)
        self.assertTrue(probe.install)


class RunTests(TempFileMixin):
    def test_passing_python_node(self) -> None:
        path = self.write("ok.py", "print('hello from the node')\n")
        result = execution.run_node(path, timeout_s=30)
        self.assertTrue(result.ok, result.as_dict())
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.language, "python")
        self.assertIn("hello from the node", result.stdout)
        self.assertIn("py_compile", " ".join(result.steps[0].argv))

    def test_runtime_failure_carries_exit_code_and_text(self) -> None:
        path = self.write("boom.py", "print('before')\nraise SystemExit('nope')\n")
        result = execution.run_node(path, timeout_s=30)
        self.assertFalse(result.ok)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("nope", result.stderr)
        self.assertEqual(result.command, result.steps[-1].command)

    def test_syntax_error_fails_the_check_step(self) -> None:
        path = self.write("broken.py", "def broken(:\n    pass\n")
        result = execution.run_node(path, timeout_s=30)
        self.assertFalse(result.ok)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("SyntaxError", result.stderr)
        self.assertEqual(len(result.steps), 1, "must stop at the first failing step")

    def test_unknown_language_is_an_honest_failure(self) -> None:
        path = self.write("readme.txt", "hello\n")
        result = execution.run_node(path)
        self.assertFalse(result.ok)
        self.assertIn("no execution schema", result.error)
        self.assertIsNone(result.exit_code)

    def test_missing_toolchain_never_claims_success(self) -> None:
        path = self.write("x.py", "print(1)\n")
        fake = execution.Toolchain(
            language="python", extensions=(".py",), bins=("nope-not-installed",),
            version_args=("--version",), check_steps=(), run_steps=(("{bin}", "{file}"),),
            install={"linux": "apt install python3", "windows": "winget install Python"},
        )
        with mock.patch.dict(execution.TOOLCHAINS, {"python": fake}):
            result = execution.run_node(path)
        self.assertFalse(result.ok)
        self.assertIn("toolchain missing", result.error)
        self.assertIn("apt install python3", result.error)

    def test_timeout_is_reported_not_raised(self) -> None:
        path = self.write("slow.py", "import time\ntime.sleep(5)\n")
        result = execution.run_node(path, timeout_s=0.5)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "timed out")
        self.assertTrue(result.steps[-1].timed_out)


class FileSetTests(unittest.TestCase):
    """`run_files` builds the set, not one file — the scaffold gate."""

    def test_python_set_runs_with_its_siblings(self) -> None:
        result = execution.run_files([
            {"path": "main.py", "content": "from util import double\nprint(double(21))\n"},
            {"path": "util.py", "content": "def double(n):\n    return n * 2\n"},
        ], "python", entry="main.py")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.stdout.strip(), "42")

    def test_a_missing_sibling_is_a_real_failure(self) -> None:
        result = execution.run_files([
            {"path": "main.py", "content": "from util import double\nprint(double(21))\n"},
        ], "python", entry="main.py")
        self.assertFalse(result.ok)
        self.assertIn("util", result.stderr)

    def test_paths_cannot_escape_the_scratch_dir(self) -> None:
        self.assertEqual(execution.safe_relative("../etc/passwd"), "")
        self.assertEqual(execution.safe_relative("/etc/passwd"), "")
        self.assertEqual(execution.safe_relative("src/./main.py"), "src/main.py")
        self.assertEqual(execution.safe_relative("C:/x/y.py"), "")

    def test_escaping_entries_are_dropped_not_written(self) -> None:
        result = execution.run_files({"../evil.py": "print(1)"}, "python", entry="evil.py")
        # Nothing safe was left, so the set is empty rather than written outside.
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "empty file set")

    def test_an_empty_set_is_refused(self) -> None:
        self.assertEqual(execution.run_files([], "python").error, "empty file set")

    def test_a_language_without_a_set_build_says_so(self) -> None:
        result = execution.run_files([{"path": "a.txt", "content": "x"}], "klingon")
        self.assertFalse(result.ok)
        self.assertIn("no multi-file build", result.error)


if __name__ == "__main__":
    unittest.main()
