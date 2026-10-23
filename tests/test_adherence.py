"""Tests for the file-set adherence score."""
import unittest

from trainapp import adherence


class AdherenceTests(unittest.TestCase):
    def test_a_missing_sibling_import_fails(self) -> None:
        report = adherence.score_files([
            {"path": "src/main.ts", "content": "import { x } from './ghost';\nconsole.log(x);\n"},
        ])
        self.assertIn("sibling_imports_ok", report["failures"])
        self.assertEqual(report["score"], 0.75)  # 3 of 4 checks pass

    def test_a_resolved_sibling_import_passes(self) -> None:
        report = adherence.score_files([
            {"path": "src/main.ts", "content": "import { x } from './util';\nconsole.log(x());\n"},
            {"path": "src/util.ts", "content": "export function x(): number {\n  return 1;\n}\n"},
        ])
        self.assertEqual(report["failures"], {})
        self.assertEqual(report["fully_adherent"], 2)

    def test_an_entry_file_is_not_required_to_export(self) -> None:
        report = adherence.score_files([
            {"path": "main.ts", "content": "import './boot';\nconsole.log('up');\n"},
            {"path": "boot.ts", "content": "console.log('boot');\n"},
        ])
        # `main.ts` is an entry, so only `boot.ts` is asked for an export.
        self.assertNotIn("exports_declared", report["per_file"]["main.ts"]["failed"])

    def test_a_module_without_exports_fails(self) -> None:
        report = adherence.score_files([
            {"path": "loose.ts", "content": "const hidden = 1;\nconsole.log(hidden);\n"},
        ])
        self.assertIn("exports_declared", report["failures"])

    def test_a_stub_is_flagged_even_though_it_compiles(self) -> None:
        report = adherence.score_files([
            {"path": "lib.ts", "content": "export function work(): void {\n  // not implemented\n}\n"},
        ])
        self.assertIn("not_stub", report["failures"])

    def test_a_manifest_turns_bare_imports_into_a_decision(self) -> None:
        manifest = '{"dependencies": {"express": "^4"}}'
        allowed = adherence.score_files([
            {"path": "package.json", "content": manifest},
            {"path": "server.ts", "content": "import express from 'express';\nexport const app = express();\n"},
        ])
        self.assertNotIn("no_phantom_imports", allowed["failures"])
        denied = adherence.score_files([
            {"path": "package.json", "content": manifest},
            {"path": "server.ts", "content": "import lodash from 'lodash';\nexport const x = lodash;\n"},
        ])
        self.assertIn("no_phantom_imports", denied["failures"])

    def test_go_local_package_imports_must_exist(self) -> None:
        files = [
            {"path": "go.mod", "content": "module example.com/app\n\ngo 1.21\n"},
            {"path": "main.go", "content":
             'package main\n\nimport (\n\t"fmt"\n\n\t"example.com/app/util"\n)\n\n'
             'func main() { fmt.Println(util.N()) }\n'},
        ]
        report = adherence.score_files(files, "go")
        self.assertIn("imports_resolve", report["failures"])

        files.append({"path": "util/util.go",
                      "content": "package util\n\nfunc N() int { return 1 }\n"})
        fixed = adherence.score_files(files, "go")
        self.assertNotIn("imports_resolve", fixed["failures"])

    def test_an_empty_set_is_zero_not_an_exception(self) -> None:
        report = adherence.score_files([])
        self.assertEqual(report["score"], 0.0)
        self.assertEqual(report["file_count"], 0)


if __name__ == "__main__":
    unittest.main()
