"""Puzzle generator: chunking, purposes, fakes, and the build-based grade."""
from __future__ import annotations

import random
import unittest

from trainapp import puzzles


JS = """import { x } from './util';

export function renderList(items) {
  const out = document.getElementById('list');
  out.innerHTML = items.map((i) => `<li>${i}</li>`).join('');
  return out;
}

const addItem = (item) => {
  const list = document.querySelector('#list');
  list.appendChild(document.createElement('li'));
};
"""

CSS = """.board {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  padding: 12px;
}

.tile {
  color: #fff;
  background: #222;
  border: 1px solid #444;
}
"""

PY = """def total(n):
    if n < 10:
        return 1
    return 2

def helper():
    return total(10)
"""


GO = """package main

import "fmt"

func total(n int) int {
	if n < 10 {
		return 1
	}
	return 2
}

func (a *Account) Deposit(amount int) {
	a.balance += amount
	fmt.Println(a.balance)
}
"""

RUST = """pub trait Shape {
    fn area(&self) -> f64;
}

pub fn describe<'a>(shape: &'a dyn Shape) -> String {
    let size = shape.area();
    if size > 10.0 {
        return String::from("large");
    }
    String::from("small")
}
"""

JAVA = """public class Shop {
    private int total;

    public int total(List<Item> items) {
        int sum = 0;
        for (Item item : items) {
            sum += item.qty;
        }
        return sum;
    }

    public Shop(int start) {
        this.total = start;
    }
}
"""

CSHARP = """public class Ledger
{
    private int total;

    public int Add(int amount)
    {
        total += amount;
        return total;
    }
}
"""


def task(files: list[dict], language: str = "python", target: str = "") -> dict:
    return {"id": "vaca-export/demo", "language": language, "runnable": True,
            "title": "demo", "description": "demo", "files": files,
            "target": target or files[0]["path"], "code": files[0]["content"]}


class ChunkTests(unittest.TestCase):
    def test_js_functions_become_nodes(self) -> None:
        nodes = puzzles.chunk_file("main.js", JS)
        self.assertEqual(len(nodes), 2)
        for node in nodes:
            # The span has to splice back to the exact same text, or a candidate
            # would be inserted in the wrong place.
            self.assertIn(node["code"], JS)
            self.assertEqual(JS[node["start"]:node["end"]].strip("\n"), node["code"])

    def test_purposes_are_classified(self) -> None:
        nodes = puzzles.chunk_file("main.js", JS)
        self.assertEqual([n["purpose"] for n in nodes],
                         ["ui-render", "ui-render"])

    def test_css_rules_are_styling(self) -> None:
        nodes = puzzles.chunk_file("style.css", CSS)
        self.assertEqual(len(nodes), 2)
        self.assertTrue(all(n["purpose"] == "styling" for n in nodes))

    def test_python_defs_are_nodes(self) -> None:
        nodes = puzzles.chunk_file("util.py", PY)
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0]["purpose"], "game-logic")

    def test_nested_functions_are_not_double_counted(self) -> None:
        code = ("export function outer() {\n"
                "  function inner() { return 1; }\n"
                "  return inner();\n"
                "}\n")
        nodes = puzzles.chunk_file("a.js", code)
        self.assertEqual(len(nodes), 1)

    def test_an_unknown_language_has_no_nodes(self) -> None:
        self.assertEqual(puzzles.chunk_file("a.rb", "def total(n)\n  n\nend\n"), [])

    def test_go_functions_and_methods_are_nodes(self) -> None:
        nodes = puzzles.chunk_file("main.go", GO)
        self.assertEqual(len(nodes), 2)
        self.assertTrue(nodes[0]["code"].startswith("func total"))
        self.assertTrue(nodes[1]["code"].startswith("func (a *Account) Deposit"))
        self.assertEqual(puzzles.language_of("main.go"), "go")
        for node in nodes:
            self.assertEqual(GO[node["start"]:node["end"]].strip("\n"), node["code"])

    def test_rust_lifetimes_do_not_break_brace_matching(self) -> None:
        nodes = puzzles.chunk_file("shape.rs", RUST)
        self.assertEqual(len(nodes), 1)
        node = nodes[0]
        self.assertTrue(node["code"].startswith("pub fn describe"))
        self.assertIn("&'a dyn Shape", node["code"])
        self.assertTrue(node["code"].rstrip().endswith("}"))
        self.assertEqual(puzzles.language_of("shape.rs"), "rust")

    def test_a_bodyless_rust_trait_method_is_not_a_node(self) -> None:
        self.assertNotIn("fn area", puzzles.chunk_file("shape.rs", RUST)[0]["code"])

    def test_java_methods_and_constructors_are_nodes(self) -> None:
        nodes = puzzles.chunk_file("Shop.java", JAVA)
        self.assertEqual(len(nodes), 2)
        self.assertTrue(nodes[0]["code"].lstrip().startswith("public int total"))
        self.assertTrue(nodes[1]["code"].lstrip().startswith("public Shop"))
        for node in nodes:
            self.assertEqual(JAVA[node["start"]:node["end"]].strip("\n"), node["code"])
        self.assertEqual(puzzles.language_of("Shop.java"), "java")

    def test_csharp_methods_are_nodes(self) -> None:
        nodes = puzzles.chunk_file("Ledger.cs", CSHARP)
        self.assertEqual(len(nodes), 1)
        self.assertTrue(nodes[0]["code"].lstrip().startswith("public int Add"))
        self.assertIn("return total;", nodes[0]["code"])
        self.assertEqual(puzzles.language_of("Ledger.cs"), "csharp")

    def test_compiled_purposes_are_classified(self) -> None:
        go_node = puzzles.chunk_file("main.go", GO)[1]
        self.assertEqual(go_node["purpose"], "output")

    def test_purpose_keywords(self) -> None:
        self.assertEqual(puzzles.classify_purpose("addEventListener('click', f)"),
                         "event-handler")
        self.assertEqual(puzzles.classify_purpose("SELECT * FROM notes"), "database")
        self.assertEqual(puzzles.classify_purpose("console.log(1)"), "output")
        self.assertEqual(puzzles.classify_purpose("const x = 1"), "state")


class CompiledMutationTests(unittest.TestCase):
    def test_go_comparison_mutates(self) -> None:
        node = puzzles.chunk_file("main.go", GO)[0]
        mutated = puzzles.subtle_mutation(node["code"], random.Random(2))
        self.assertIsNotNone(mutated)
        self.assertNotEqual(mutated[0], node["code"])

    def test_rust_comparison_mutates(self) -> None:
        node = puzzles.chunk_file("shape.rs", RUST)[0]
        mutated = puzzles.subtle_mutation(node["code"], random.Random(2))
        self.assertIsNotNone(mutated)
        self.assertNotEqual(mutated[0], node["code"])


class MutationTests(unittest.TestCase):
    def test_a_mutation_changes_the_code_and_names_its_operation(self) -> None:
        mutated, operation = puzzles.subtle_mutation("if (n < 10) { return n + 1; }",
                                                     random.Random(3))
        self.assertNotEqual(mutated, "if (n < 10) { return n + 1; }")
        self.assertIn(operation, {"comparison", "off-by-one", "boolean", "api"})

    def test_no_operator_means_no_puzzle(self) -> None:
        self.assertIsNone(puzzles.subtle_mutation("plain words here", random.Random(1)))

    def test_the_decoy_comes_from_another_app_with_the_same_purpose(self) -> None:
        a = task([{"path": "a.js", "content": JS}], "javascript", "a.js")
        b = task([{"path": "b.js", "content": JS.replace("items", "rows")}],
                 "javascript", "b.js")
        b["id"] = "vaca-export/other"
        index = puzzles.NodeIndex([a, b])
        node = puzzles.chunk_app(a["files"])[0]
        decoy = index.decoy(node["purpose"], exclude_task=a["id"],
                            language="javascript", exclude_code=node["code"])
        self.assertIsNotNone(decoy)
        self.assertEqual(decoy[0], "vaca-export/other")

    def test_build_puzzle_has_all_three_candidates(self) -> None:
        a = task([{"path": "a.js", "content": JS}], "javascript", "a.js")
        b = task([{"path": "b.js", "content": JS.replace("items", "rows")}],
                 "javascript", "b.js")
        b["id"] = "vaca-export/other"
        index = puzzles.NodeIndex([a, b])
        node = puzzles.chunk_app(a["files"])[0]
        puzzle = puzzles.build_puzzle(node, index, task_id=a["id"], language="javascript")
        self.assertIsNotNone(puzzle)
        self.assertNotEqual(puzzle["correct"], puzzle["mutant"])
        self.assertTrue(puzzle["decoy"])
        self.assertEqual(puzzle["decoy_from"], "vaca-export/other")


class ScoringTests(unittest.TestCase):
    def fixtures(self, util: str = PY,
                 call: str = "print(total(10))") -> tuple[dict, puzzles.Node]:
        files = [{"path": "main.py", "content": f"from util import total\n{call}\n"},
                 {"path": "util.py", "content": util}]
        node = next(n for n in puzzles.chunk_file("util.py", util)
                    if "n < 10" in n["code"])
        return task(files, "python", "util.py"), node

    def test_a_behaviour_changing_mutation_is_caught(self) -> None:
        app, node = self.fixtures()
        puzzle = {"correct": node["code"],
                  "mutant": node["code"].replace("n < 10", "n <= 10"),
                  "mutation": "comparison", "decoy": ""}
        row = puzzles.score_puzzle(app, node, puzzle)
        self.assertTrue(row["builds"])
        self.assertTrue(row["behaviour_stable"])
        self.assertTrue(row["mutant_detected"])
        self.assertEqual(row["clean"], 1.0)

    def test_a_broken_correct_node_is_a_defect(self) -> None:
        app, node = self.fixtures()
        broken = node["code"].replace("return 2", "return 2 +")
        puzzle = {"correct": broken,
                  "mutant": broken.replace("n < 10", "n <= 10"),
                  "mutation": "comparison", "decoy": ""}
        row = puzzles.score_puzzle(app, node, puzzle)
        self.assertFalse(row["builds"])
        self.assertFalse(row["behaviour_stable"])
        self.assertLess(row["clean"], 0.6)

    def test_a_surviving_mutation_marks_a_weak_exemplar(self) -> None:
        # `total(10)` returns `n` on both sides of the boundary, so flipping
        # `<` to `<=` cannot be seen from the output: the node is correct but
        # nothing in it is load-bearing.
        util = ("def total(n):\n"
                "    if n < 10:\n"
                "        return n\n"
                "    return 10\n")
        app, node = self.fixtures(util)
        puzzle = {"correct": node["code"],
                  "mutant": node["code"].replace("n < 10", "n <= 10"),
                  "mutation": "comparison", "decoy": ""}
        row = puzzles.score_puzzle(app, node, puzzle)
        self.assertTrue(row["builds"])
        self.assertFalse(row["mutant_detected"])
        self.assertLess(row["clean"], 1.0)


if __name__ == "__main__":
    unittest.main()
