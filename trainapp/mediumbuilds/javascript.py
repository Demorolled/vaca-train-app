"""JavaScript medium builds — ten templates, ten data variants each.

Several functions and one real data structure per program: a Map for counts, an
array of records, a class holding state, a linked list. Deterministic output, no
imports, no stdin, no clock, no randomness.
"""
from __future__ import annotations

import json

LANGUAGE = "javascript"

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

WORD_FREQ = """const TEXT = @TEXT@;

function tokenise(text) {
  return text.toLowerCase().split(/\\s+/).filter((word) => word.length > 0);
}

function count(words) {
  const table = new Map();
  for (const word of words) {
    table.set(word, (table.get(word) || 0) + 1);
  }
  return table;
}

function ranked(table) {
  return [...table.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function report(rows) {
  return rows.slice(0, 4).map(([word, count]) => word + ": " + count).join("\\n");
}

console.log(report(ranked(count(tokenise(TEXT)))));
"""

INVENTORY = """const STOCK = @STOCK@;

function available(stock) {
  return stock.filter((item) => item.qty > 0);
}

function value(rows) {
  return rows.reduce((sum, item) => sum + item.qty * item.price, 0);
}

function lines(rows) {
  return rows.map((item) =>
    item.name.padEnd(8) + " " + String(item.qty).padStart(3) + " x " +
    item.price.toFixed(2).padStart(6) + " = " + (item.qty * item.price).toFixed(2).padStart(8));
}

const rows = available(STOCK);
console.log(lines(rows).join("\\n"));
console.log("total " + value(rows).toFixed(2));
"""

MATRIX = """const MATRIX = @MATRIX@;

function transpose(matrix) {
  return matrix[0].map((_, index) => matrix.map((row) => row[index]));
}

function rowSums(matrix) {
  return matrix.map((row) => row.reduce((sum, value) => sum + value, 0));
}

function render(matrix) {
  return matrix.map((row) => row.map((value) => String(value).padStart(3)).join(" ")).join("\\n");
}

console.log(render(transpose(MATRIX)));
console.log("sums " + rowSums(MATRIX).join(" "));
"""

STACK = """class Stack {
  constructor() {
    this.items = [];
  }

  push(value) {
    this.items.push(value);
  }

  pop() {
    return this.items.length ? this.items.pop() : null;
  }

  peek() {
    return this.items.length ? this.items[this.items.length - 1] : null;
  }
}

function run(stack, ops) {
  const out = [];
  for (const op of ops) {
    const parts = op.split(" ");
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

const OPS = @OPS@;
console.log(run(new Stack(), OPS).join("\\n"));
"""

LINKED = """const VALUES = @VALUES@;

class Node {
  constructor(value, next) {
    this.value = value;
    this.next = next || null;
  }
}

function build(values) {
  let head = null;
  for (let index = values.length - 1; index >= 0; index -= 1) {
    head = new Node(values[index], head);
  }
  return head;
}

function reverse(head) {
  let previous = null;
  let node = head;
  while (node) {
    const next = node.next;
    node.next = previous;
    previous = node;
    node = next;
  }
  return previous;
}

function render(head) {
  const out = [];
  let node = head;
  while (node) {
    out.push(String(node.value));
    node = node.next;
  }
  return out.join(" -> ");
}

const head = build(VALUES);
console.log(render(head));
console.log(render(reverse(head)));
"""

CSV = """const DATA = @CSV@;

function parse(data) {
  const lines = data.trim().split("\\n");
  const header = lines[0].split(",");
  const rows = lines.slice(1).map((line) => line.split(","));
  return { header: header, rows: rows };
}

function totals(header, rows) {
  const out = {};
  for (let index = 1; index < header.length; index += 1) {
    const numbers = rows.map((row) => Number(row[index])).filter((value) => !Number.isNaN(value));
    out[header[index]] = numbers.reduce((sum, value) => sum + value, 0);
  }
  return out;
}

const parsed = parse(DATA);
console.log("columns " + parsed.header.slice(1).join(","));
for (const [name, value] of Object.entries(totals(parsed.header, parsed.rows))) {
  console.log(name + ": " + value.toFixed(2));
}
"""

SORT = """const ROWS = @ROWS@;

function byValue(rows) {
  return [...rows].sort((a, b) => b.qty * b.price - a.qty * a.price || a.name.localeCompare(b.name));
}

function byName(rows) {
  return [...rows].sort((a, b) => a.name.localeCompare(b.name));
}

function render(rows) {
  return rows.map((row) => row.name + "(" + row.qty + ")").join(", ");
}

console.log("value " + render(byValue(ROWS)));
console.log("name  " + render(byName(ROWS)));
"""

FACTORS = """const NUMBERS = @NUMBERS@;

function factorise(value) {
  const out = [];
  let rest = value;
  let divisor = 2;
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

function table(numbers) {
  return numbers.map((number) => [number, factorise(number)]);
}

for (const [number, parts] of table(NUMBERS)) {
  console.log(number + ": " + parts.join(" x "));
}
"""

BANK = """class Account {
  constructor(opening) {
    this.balance = opening;
    this.log = [];
  }

  deposit(amount) {
    this.balance += amount;
    this.log.push(["deposit", amount, this.balance]);
  }

  withdraw(amount) {
    if (amount > this.balance) {
      this.log.push(["refused", amount, this.balance]);
      return false;
    }
    this.balance -= amount;
    this.log.push(["withdraw", amount, this.balance]);
    return true;
  }
}

const OPS = @LEDGER@;
const account = new Account(OPS[0][1]);
account.log.push(["open", OPS[0][1], OPS[0][1]]);
for (const [kind, amount] of OPS.slice(1)) {
  if (kind === "deposit") {
    account.deposit(amount);
  } else {
    account.withdraw(amount);
  }
}

for (const [kind, amount, balance] of account.log) {
  console.log(kind.padEnd(9) + " " + String(amount).padStart(4) + " -> " + String(balance).padStart(4));
}
"""

PIPELINE = """const TEXT = @TEXT@;

function words(text) {
  return text.split(/\\s+/).filter((word) => word.length > 0);
}

function transform(items) {
  return items.map((word) => word.charAt(0).toUpperCase() + word.slice(1));
}

function longest(items) {
  return items.reduce((best, word) => (word.length > best.length ? word : best), "");
}

function report(items) {
  return transform(items).join(" | ");
}

const items = words(TEXT);
console.log(report(items));
console.log(items.length + " " + longest(items) + " " + items.reduce((sum, word) => sum + word.length, 0));
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


def _lists(values: tuple) -> str:
    return json.dumps(list(values))


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
                     "code": _fill(LINKED, VALUES=_lists(values))})
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
