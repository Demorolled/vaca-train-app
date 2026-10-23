"""TypeScript medium builds — ten templates, ten data variants each.

The same programs as the JavaScript module with explicit types throughout, so
each one is a real typecheck target: an interface for the record shape, typed
Map entries, typed class fields and annotated callbacks. No imports, no stdin, no
clock, no randomness; it must pass `tsc --noEmit` on its own.
"""
from __future__ import annotations

import json

LANGUAGE = "typescript"

TEXTS = (
    "the quick brown fox jumps over the lazy dog the fox",
    "a small step for man a giant leap for mankind",
    "one two two three three three four four four four",
    "red green blue red green red",
    "build test ship build test build",
    "alpha beta gamma alpha beta alpha",
    "data data model model model view view view view",
    "cat dog cat bird cat dog",
    "read read write write write refactor",
    "north south east west north south north",
)

RECORDS = (
    (("bolt", 12, 0.5), ("nut", 40, 0.1), ("washer", 0, 0.05)),
    (("hammer", 3, 12.0), ("saw", 0, 18.5), ("drill", 2, 45.0)),
    (("pen", 100, 1.2), ("ink", 4, 6.0), ("pad", 25, 2.5)),
    (("cpu", 2, 199.0), ("ram", 4, 79.0), ("ssd", 0, 120.0)),
    (("apple", 30, 0.4), ("pear", 0, 0.5), ("plum", 11, 0.8)),
    (("cup", 6, 3.0), ("plate", 6, 4.0), ("fork", 0, 2.0)),
    (("rope", 2, 15.0), ("hook", 9, 4.5), ("glove", 1, 22.0)),
    (("map", 1, 8.0), ("compass", 0, 30.0), ("whistle", 5, 3.5)),
    (("tile", 200, 1.0), ("grout", 3, 9.0), ("seal", 0, 7.0)),
    (("lamp", 4, 25.0), ("bulb", 0, 4.0), ("cable", 12, 3.0)),
)

MATRICES = (
    ((1, 2, 3), (4, 5, 6), (7, 8, 9)),
    ((2, 0, 1), (0, 3, 0), (1, 0, 2)),
    ((5, 1, 9), (2, 6, 3), (8, 4, 7)),
    ((1, 1, 1), (2, 2, 2), (3, 3, 3)),
    ((0, 2, 4), (6, 8, 10), (12, 14, 16)),
    ((9, 8, 7), (6, 5, 4), (3, 2, 1)),
    ((4, 4, 0), (0, 4, 4), (4, 0, 4)),
    ((11, 12, 13), (21, 22, 23), (31, 32, 33)),
    ((3, 0, 0), (0, 3, 0), (0, 0, 3)),
    ((7, 5, 3), (1, 9, 2), (4, 6, 8)),
)

CSVS = (
    "name,qty,price\nbolt,12,0.50\nnut,40,0.10\nwasher,0,0.05",
    "item,units,cost\nhammer,3,36.00\nsaw,0,18.50\ndrill,2,90.00",
    "city,pop,area\naustin,964,704\nboston,695,232\ndenver,715,401",
    "lang,year,stars\npython,1991,9\nrust,2010,7\ngo,2009,8",
    "day,high,low\nmon,21,9\ntue,19,8\nwed,23,12",
    "sku,stock,reorder\na1,4,10\nb2,0,5\nc3,18,10",
    "team,wins,losses\nred,7,3\nblue,5,5\ngreen,9,1",
    "route,km,minutes\nalpha,12,18\nbeta,7,9\ngamma,25,31",
    "book,parts,pages\none,3,120\ntwo,1,40\nthree,5,260",
    "part,width,height\nframe,80,120\npanel,40,60\ndoor,90,200",
)

NUMBERS = (12, 18, 28, 30, 36, 45, 60, 84, 97, 120)

STACK_OPS = (
    ("push 3", "push 1", "peek", "pop", "push 4", "pop", "pop"),
    ("push 9", "push 9", "pop", "peek", "pop", "pop", "peek"),
    ("push 2", "pop", "push 7", "push 8", "peek", "pop", "pop"),
    ("push 5", "push 6", "push 7", "pop", "pop", "pop", "pop"),
    ("push 1", "push 2", "pop", "push 3", "push 4", "pop", "peek"),
    ("push 10", "peek", "push 20", "peek", "pop", "peek", "pop"),
    ("push 8", "push 3", "pop", "push 9", "pop", "pop", "peek"),
    ("push 4", "push 4", "push 4", "pop", "pop", "pop", "pop"),
    ("push 0", "pop", "pop", "push 1", "peek", "push 2", "pop"),
    ("push 6", "push 5", "peek", "pop", "push 7", "pop", "pop"),
)

LEDGERS = (
    (("open", 100), ("deposit", 50), ("withdraw", 30), ("withdraw", 500)),
    (("open", 20), ("withdraw", 5), ("withdraw", 15), ("deposit", 7)),
    (("open", 0), ("deposit", 12), ("withdraw", 12), ("withdraw", 1)),
    (("open", 250), ("withdraw", 249), ("deposit", 3), ("withdraw", 4)),
    (("open", 40), ("deposit", 0), ("withdraw", 40), ("deposit", 1)),
    (("open", 75), ("withdraw", 25), ("withdraw", 25), ("withdraw", 25)),
    (("open", 5), ("deposit", 500), ("withdraw", 250), ("withdraw", 255)),
    (("open", 1000), ("withdraw", 999), ("deposit", 1), ("withdraw", 2)),
    (("open", 33), ("deposit", 33), ("withdraw", 66), ("deposit", 34)),
    (("open", 8), ("withdraw", 4), ("deposit", 10), ("withdraw", 14)),
)

LISTS = (
    (3, 1, 4), (7, 2, 9, 5), (1, 2, 3, 4, 5), (9,), (4, 4, 6),
    (8, 3, 1, 7), (2, 6, 5, 3, 8), (11, 4), (5, 9, 2, 6, 1), (10, 20, 30, 40),
)

WORD_FREQ = """const TEXT: string = @TEXT@;

function tokenise(text: string): string[] {
  return text.toLowerCase().split(/\\s+/).filter((word: string) => word.length > 0);
}

function count(words: string[]): Map<string, number> {
  const table: Map<string, number> = new Map();
  for (const word of words) {
    table.set(word, (table.get(word) || 0) + 1);
  }
  return table;
}

function ranked(table: Map<string, number>): Array<[string, number]> {
  const rows: Array<[string, number]> = [...table.entries()];
  return rows.sort((a: [string, number], b: [string, number]): number =>
    b[1] - a[1] || a[0].localeCompare(b[0]));
}

function report(rows: Array<[string, number]>): string {
  return rows.slice(0, 4).map(([word, count]: [string, number]): string => word + ": " + count).join("\\n");
}

console.log(report(ranked(count(tokenise(TEXT)))));
"""

INVENTORY = """interface Item {
  name: string;
  qty: number;
  price: number;
}

const STOCK: Item[] = @STOCK@;

function available(stock: Item[]): Item[] {
  return stock.filter((item: Item): boolean => item.qty > 0);
}

function value(rows: Item[]): number {
  return rows.reduce((sum: number, item: Item): number => sum + item.qty * item.price, 0);
}

function lines(rows: Item[]): string[] {
  return rows.map((item: Item): string =>
    item.name.padEnd(8) + " " + String(item.qty).padStart(3) + " x " +
    item.price.toFixed(2).padStart(6) + " = " + (item.qty * item.price).toFixed(2).padStart(8));
}

const rows: Item[] = available(STOCK);
console.log(lines(rows).join("\\n"));
console.log("total " + value(rows).toFixed(2));
"""

MATRIX = """const MATRIX: number[][] = @MATRIX@;

function transpose(matrix: number[][]): number[][] {
  return matrix[0].map((_: number, index: number): number[] => matrix.map((row: number[]): number => row[index]));
}

function rowSums(matrix: number[][]): number[] {
  return matrix.map((row: number[]): number => row.reduce((sum: number, value: number): number => sum + value, 0));
}

function render(matrix: number[][]): string {
  return matrix.map((row: number[]): string =>
    row.map((value: number): string => String(value).padStart(3)).join(" ")).join("\\n");
}

console.log(render(transpose(MATRIX)));
console.log("sums " + rowSums(MATRIX).join(" "));
"""

STACK = """class Stack {
  items: number[];

  constructor() {
    this.items = [];
  }

  push(value: number): void {
    this.items.push(value);
  }

  pop(): number | null {
    // `|| null` would turn a popped 0 into null; the op lists push 0 on purpose.
    const value: number | undefined = this.items.pop();
    return value === undefined ? null : value;
  }

  peek(): number | null {
    return this.items.length ? this.items[this.items.length - 1] : null;
  }
}

function run(stack: Stack, ops: string[]): string[] {
  const out: string[] = [];
  for (const op of ops) {
    const parts: string[] = op.split(" ");
    if (parts[0] === "push") {
      stack.push(Number(parts[1]));
      out.push("push " + parts[1]);
    } else if (parts[0] === "pop") {
      out.push("pop " + stack.pop());
    } else {
      out.push("peek " + stack.peek());
    }
  }
  return out;
}

const OPS: string[] = @OPS@;
console.log(run(new Stack(), OPS).join("\\n"));
"""

LINKED = """const VALUES: number[] = @VALUES@;

// `Node` is the DOM's own interface: declaring a class with that name is a
// duplicate identifier under lib.dom, so the list node is `ListNode`.
class ListNode {
  value: number;
  next: ListNode | null;

  constructor(value: number, next: ListNode | null = null) {
    this.value = value;
    this.next = next;
  }
}

function build(values: number[]): ListNode | null {
  let head: ListNode | null = null;
  for (let index: number = values.length - 1; index >= 0; index -= 1) {
    head = new ListNode(values[index], head);
  }
  return head;
}

function reverse(head: ListNode | null): ListNode | null {
  let previous: ListNode | null = null;
  let node: ListNode | null = head;
  while (node) {
    const next: ListNode | null = node.next;
    node.next = previous;
    previous = node;
    node = next;
  }
  return previous;
}

function render(head: ListNode | null): string {
  const out: string[] = [];
  let node: ListNode | null = head;
  while (node) {
    out.push(String(node.value));
    node = node.next;
  }
  return out.join(" -> ");
}

const head: ListNode | null = build(VALUES);
console.log(render(head));
console.log(render(reverse(head)));
"""

CSV = """const DATA: string = @CSV@;

interface Table {
  header: string[];
  rows: string[][];
}

function parse(data: string): Table {
  const lines: string[] = data.trim().split("\\n");
  const header: string[] = lines[0].split(",");
  const rows: string[][] = lines.slice(1).map((line: string): string[] => line.split(","));
  return { header: header, rows: rows };
}

function totals(header: string[], rows: string[][]): Record<string, number> {
  const out: Record<string, number> = {};
  for (let index: number = 1; index < header.length; index += 1) {
    const numbers: number[] = rows.map((row: string[]): number => Number(row[index]))
      .filter((value: number): boolean => !Number.isNaN(value));
    out[header[index]] = numbers.reduce((sum: number, value: number): number => sum + value, 0);
  }
  return out;
}

const parsed: Table = parse(DATA);
console.log("columns " + parsed.header.slice(1).join(","));
const sums: Record<string, number> = totals(parsed.header, parsed.rows);
for (const name of Object.keys(sums)) {
  console.log(name + ": " + sums[name].toFixed(2));
}
"""

SORT = """interface Item {
  name: string;
  qty: number;
  price: number;
}

const ROWS: Item[] = @ROWS@;

function byValue(rows: Item[]): Item[] {
  return [...rows].sort((a: Item, b: Item): number =>
    b.qty * b.price - a.qty * a.price || a.name.localeCompare(b.name));
}

function byName(rows: Item[]): Item[] {
  return [...rows].sort((a: Item, b: Item): number => a.name.localeCompare(b.name));
}

function render(rows: Item[]): string {
  return rows.map((row: Item): string => row.name + "(" + row.qty + ")").join(", ");
}

console.log("value " + render(byValue(ROWS)));
console.log("name  " + render(byName(ROWS)));
"""

FACTORS = """const NUMBERS: number[] = @NUMBERS@;

function factorise(value: number): number[] {
  const out: number[] = [];
  let rest: number = value;
  let divisor: number = 2;
  while (divisor * divisor <= rest) {
    while (rest % divisor === 0) {
      out.push(divisor);
      rest /= divisor;
    }
    divisor += 1;
  }
  if (rest > 1) {
    out.push(rest);
  }
  return out;
}

function table(numbers: number[]): Array<[number, number[]]> {
  return numbers.map((number: number): [number, number[]] => [number, factorise(number)]);
}

for (const row of table(NUMBERS)) {
  console.log(row[0] + ": " + row[1].join(" x "));
}
"""

BANK = """type Entry = [string, number, number];

class Account {
  balance: number;
  log: Entry[];

  constructor(opening: number) {
    this.balance = opening;
    this.log = [];
  }

  deposit(amount: number): void {
    this.balance += amount;
    this.log.push(["deposit", amount, this.balance]);
  }

  withdraw(amount: number): boolean {
    if (amount > this.balance) {
      this.log.push(["refused", amount, this.balance]);
      return false;
    }
    this.balance -= amount;
    this.log.push(["withdraw", amount, this.balance]);
    return true;
  }
}

const OPS: Array<[string, number]> = @LEDGER@;
const account: Account = new Account(OPS[0][1]);
account.log.push(["open", OPS[0][1], OPS[0][1]]);
for (const op of OPS.slice(1)) {
  if (op[0] === "deposit") {
    account.deposit(op[1]);
  } else {
    account.withdraw(op[1]);
  }
}

for (const entry of account.log) {
  console.log(entry[0].padEnd(9) + " " + String(entry[1]).padStart(4) + " -> " + String(entry[2]).padStart(4));
}
"""

PIPELINE = """const TEXT: string = @TEXT@;

function words(text: string): string[] {
  return text.split(/\\s+/).filter((word: string): boolean => word.length > 0);
}

function transform(items: string[]): string[] {
  return items.map((word: string): string => word.charAt(0).toUpperCase() + word.slice(1));
}

function longest(items: string[]): string {
  return items.reduce((best: string, word: string): string => (word.length > best.length ? word : best), "");
}

function report(items: string[]): string {
  return transform(items).join(" | ");
}

const items: string[] = words(TEXT);
console.log(report(items));
console.log(items.length + " " + longest(items) + " " + items.reduce((sum: number, word: string): number => sum + word.length, 0));
"""


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace(f"@{key}@", value)
    return template


def _stock(records: tuple) -> str:
    rows = [{"name": name, "qty": qty, "price": price} for name, qty, price in records]
    return json.dumps(rows)


def _matrix(matrix: tuple) -> str:
    return json.dumps([list(row) for row in matrix])


def _ledger(ledger: tuple) -> str:
    return json.dumps([list(op) for op in ledger])


def programs() -> list[dict]:
    rows: list[dict] = []
    for text in TEXTS:
        rows.append({"title": f"word frequency: {text[:24]}", "template": "word-freq",
                     "code": _fill(WORD_FREQ, TEXT=json.dumps(text))})
    for records in RECORDS:
        rows.append({"title": f"inventory report: {records[0][0]}", "template": "inventory",
                     "code": _fill(INVENTORY, STOCK=_stock(records))})
        rows.append({"title": f"sort records: {records[0][0]}", "template": "sort-records",
                     "code": _fill(SORT, ROWS=_stock(records))})
    for matrix in MATRICES:
        rows.append({"title": f"matrix {list(matrix[0])}", "template": "matrix",
                     "code": _fill(MATRIX, MATRIX=_matrix(matrix))})
    for ops in STACK_OPS:
        rows.append({"title": f"stack: {' '.join(ops[:2])}", "template": "stack",
                     "code": _fill(STACK, OPS=json.dumps(list(ops)))})
    for values in LISTS:
        rows.append({"title": f"reverse list {list(values)}", "template": "linked-list",
                     "code": _fill(LINKED, VALUES=json.dumps(list(values)))})
    for text in CSVS:
        rows.append({"title": f"csv totals: {text.split(',')[0]}", "template": "csv",
                     "code": _fill(CSV, CSV=json.dumps(text))})
    for number in NUMBERS:
        rows.append({"title": f"factors up to {number}", "template": "factors",
                     "code": _fill(FACTORS, NUMBERS=json.dumps(
                         [number // 2, number - 1, number, 7, 11, 13, 17, 19]))})
    for ledger in LEDGERS:
        rows.append({"title": f"ledger from {ledger[0][1]}", "template": "bank",
                     "code": _fill(BANK, LEDGER=_ledger(ledger))})
    for text in TEXTS:
        rows.append({"title": f"text pipeline: {text[:20]}", "template": "pipeline",
                     "code": _fill(PIPELINE, TEXT=json.dumps(text))})
    return rows
