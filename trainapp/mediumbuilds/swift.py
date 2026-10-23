"""Swift medium builds — ten multi-function templates, ten data variants each.

Deliberately Foundation-free: no `import`, no `String(format:)`, money in integer
cents so nothing depends on locale or floating-point formatting. Each program
keeps state in a dictionary, an array or a small class and prints a report.
"""
from __future__ import annotations

LANGUAGE = "swift"

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
    (("bolt", 12, 50), ("nut", 40, 10), ("washer", 0, 5)),
    (("hammer", 3, 1200), ("saw", 0, 1850), ("drill", 2, 4500)),
    (("pen", 100, 120), ("ink", 4, 600), ("pad", 25, 250)),
    (("cpu", 2, 19900), ("ram", 4, 7900), ("ssd", 0, 12000)),
    (("apple", 30, 40), ("pear", 0, 50), ("plum", 11, 80)),
    (("cup", 6, 300), ("plate", 6, 400), ("fork", 0, 200)),
    (("rope", 2, 1500), ("hook", 9, 450), ("glove", 1, 2200)),
    (("map", 1, 800), ("compass", 0, 3000), ("whistle", 5, 350)),
    (("tile", 200, 100), ("grout", 3, 900), ("seal", 0, 700)),
    (("lamp", 4, 2500), ("bulb", 0, 400), ("cable", 12, 300)),
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

LISTS = (
    (3, 1, 4), (7, 2, 9, 5), (1, 2, 3, 4, 5), (9,), (4, 4, 6),
    (8, 3, 1, 7), (2, 6, 5, 3, 8), (11, 4), (5, 9, 2, 6, 1), (10, 20, 30, 40),
)

CSVS = (
    "name,qty,price\nbolt,12,50\nnut,40,10\nwasher,0,5",
    "item,units,cost\nhammer,3,3600\nsaw,0,1850\ndrill,2,9000",
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


def _fill(template: str, **values) -> str:
    text = template
    for key, value in values.items():
        text = text.replace(f"@{key}@", str(value))
    return text


def _string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _triples(records: tuple) -> str:
    return "[" + ", ".join(
        f"({_string(name)}, {qty}, {price})" for name, qty, price in records) + "]"


def _matrix_literal(matrix: tuple) -> str:
    return "[" + ", ".join(
        "[" + ", ".join(str(value) for value in row) + "]" for row in matrix) + "]"


def _ints(values: tuple) -> str:
    return "[" + ", ".join(str(value) for value in values) + "]"


def _op_list(ops: tuple) -> str:
    return "[" + ", ".join(_string(op) for op in ops) + "]"


def _pairs(pairs: tuple) -> str:
    return "[" + ", ".join(f"({_string(name)}, {amount})" for name, amount in pairs) + "]"


WORD_FREQ = """let TEXT = @TEXT@

func tokens(_ text: String) -> [String] {
    return text.split(separator: " ").map { String($0) }
}

func counts(_ words: [String]) -> [String: Int] {
    var table: [String: Int] = [:]
    for word in words {
        table[word, default: 0] += 1
    }
    return table
}

func ranked(_ table: [String: Int]) -> [(String, Int)] {
    let sorted = table.sorted { left, right in
        if left.value == right.value { return left.key < right.key }
        return left.value > right.value
    }
    return sorted.map { ($0.key, $0.value) }
}

func report(_ rows: [(String, Int)]) -> String {
    var lines: [String] = []
    for (word, count) in rows.prefix(4) {
        lines.append(word + ": " + String(count))
    }
    return lines.joined(separator: "\\n")
}

print(report(ranked(counts(tokens(TEXT)))))
"""

INVENTORY = """let STOCK = @ROWS@

func available(_ stock: [(String, Int, Int)]) -> [(String, Int, Int)] {
    return stock.filter { $0.1 > 0 }
}

func totalCents(_ rows: [(String, Int, Int)]) -> Int {
    var total = 0
    for row in rows {
        total += row.1 * row.2
    }
    return total
}

func lines(_ rows: [(String, Int, Int)]) -> [String] {
    var out: [String] = []
    for (name, qty, price) in rows {
        out.append(name + " " + String(qty) + " x " + String(price) + "c = "
                   + String(qty * price) + "c")
    }
    return out
}

let rows = available(STOCK)
print(lines(rows).joined(separator: "\\n"))
print("total " + String(totalCents(rows)) + "c")
"""

MATRIX = """let MATRIX = @MATRIX@

func transpose(_ matrix: [[Int]]) -> [[Int]] {
    var out: [[Int]] = []
    for index in matrix[0].indices {
        var row: [Int] = []
        for source in matrix {
            row.append(source[index])
        }
        out.append(row)
    }
    return out
}

func rowSums(_ matrix: [[Int]]) -> [Int] {
    var out: [Int] = []
    for row in matrix {
        var total = 0
        for value in row {
            total += value
        }
        out.append(total)
    }
    return out
}

func render(_ matrix: [[Int]]) -> String {
    var lines: [String] = []
    for row in matrix {
        var parts: [String] = []
        for value in row {
            parts.append(String(value))
        }
        lines.append(parts.joined(separator: " "))
    }
    return lines.joined(separator: "\\n")
}

print(render(transpose(MATRIX)))
print("sums", rowSums(MATRIX))
"""

STACK = """let OPS = @OPS@

final class Stack {
    private var items: [Int] = []

    func push(_ value: Int) {
        items.append(value)
    }

    func pop() -> Int? {
        return items.popLast()
    }

    func peek() -> Int? {
        return items.last
    }
}

func run(_ stack: Stack, _ ops: [String]) -> [String] {
    var out: [String] = []
    for op in ops {
        let parts = op.split(separator: " ")
        let name = String(parts[0])
        if name == "push" {
            let value = Int(parts[1]) ?? 0
            stack.push(value)
            out.append("push " + String(value))
        } else if name == "pop" {
            out.append("pop " + String(stack.pop() ?? -1))
        } else {
            out.append("peek " + String(stack.peek() ?? -1))
        }
    }
    return out
}

print(run(Stack(), OPS).joined(separator: "\\n"))
"""

LINKED_LIST = """let VALUES = @VALUES@

final class Node {
    var value: Int
    var next: Node?

    init(_ value: Int, _ next: Node? = nil) {
        self.value = value
        self.next = next
    }
}

func build(_ values: [Int]) -> Node? {
    var head: Node? = nil
    for value in values.reversed() {
        head = Node(value, head)
    }
    return head
}

func reverse(_ head: Node?) -> Node? {
    var previous: Node? = nil
    var current = head
    while let node = current {
        let following = node.next
        node.next = previous
        previous = node
        current = following
    }
    return previous
}

func render(_ head: Node?) -> String {
    var parts: [String] = []
    var cursor = head
    while let node = cursor {
        parts.append(String(node.value))
        cursor = node.next
    }
    return parts.joined(separator: " -> ")
}

let head = build(VALUES)
print(render(head))
print(render(reverse(head)))
"""

CSV = """let DATA = @DATA@

func parse(_ data: String) -> ([String], [[String]]) {
    let lines = data.split(separator: "\\n").map { String($0) }
    let header = lines[0].split(separator: ",").map { String($0) }
    var rows: [[String]] = []
    for line in lines.dropFirst() {
        rows.append(line.split(separator: ",").map { String($0) })
    }
    return (header, rows)
}

func totals(_ header: [String], _ rows: [[String]]) -> [(String, Int)] {
    var out: [(String, Int)] = []
    for index in 1..<header.count {
        var total = 0
        for row in rows {
            total += Int(row[index]) ?? 0
        }
        out.append((header[index], total))
    }
    return out
}

let (header, rows) = parse(DATA)
print("rows " + String(rows.count))
for (name, total) in totals(header, rows) {
    print(name + ": " + String(total))
}
"""

SORT_RECORDS = """let ROWS = @ROWS@

func byValue(_ rows: [(String, Int, Int)]) -> [(String, Int, Int)] {
    return rows.sorted { left, right in
        let leftValue = left.1 * left.2
        let rightValue = right.1 * right.2
        if leftValue == rightValue { return left.0 < right.0 }
        return leftValue > rightValue
    }
}

func byName(_ rows: [(String, Int, Int)]) -> [(String, Int, Int)] {
    return rows.sorted { $0.0 < $1.0 }
}

func render(_ rows: [(String, Int, Int)]) -> String {
    var parts: [String] = []
    for (name, qty, _) in rows {
        parts.append(name + "(" + String(qty) + ")")
    }
    return parts.joined(separator: ", ")
}

print("value " + render(byValue(ROWS)))
print("name  " + render(byName(ROWS)))
"""

FACTORS = """let NUMBERS = @NUMBERS@

func factorise(_ value: Int) -> [Int] {
    var out: [Int] = []
    var rest = value
    var divisor = 2
    while divisor * divisor <= rest {
        while rest % divisor == 0 {
            out.append(divisor)
            rest /= divisor
        }
        divisor += 1
    }
    if rest > 1 {
        out.append(rest)
    }
    return out
}

func table(_ numbers: [Int]) -> [(Int, [Int])] {
    var out: [(Int, [Int])] = []
    for number in numbers {
        out.append((number, factorise(number)))
    }
    return out
}

func render(_ parts: [Int]) -> String {
    var words: [String] = []
    for part in parts {
        words.append(String(part))
    }
    return words.joined(separator: " x ")
}

for (number, parts) in table(NUMBERS) {
    print(String(number) + ": " + render(parts))
}
"""

BANK = """let OPS = @OPS@

final class Account {
    var balance: Int
    var log: [(String, Int, Int)] = []

    init(_ opening: Int) {
        self.balance = opening
    }

    func deposit(_ amount: Int) {
        balance += amount
        log.append(("deposit", amount, balance))
    }

    func withdraw(_ amount: Int) {
        if amount > balance {
            log.append(("refused", amount, balance))
            return
        }
        balance -= amount
        log.append(("withdraw", amount, balance))
    }
}

let account = Account(OPS[0].1)
account.log.append(("open", OPS[0].1, OPS[0].1))
for (kind, amount) in OPS.dropFirst() {
    if kind == "deposit" {
        account.deposit(amount)
    } else {
        account.withdraw(amount)
    }
}
for (kind, amount, balance) in account.log {
    print(kind + " " + String(amount) + " -> " + String(balance))
}
"""

PIPELINE = """let TEXT = @TEXT@

func words(_ text: String) -> [String] {
    return text.split(separator: " ").map { String($0) }
}

func capitalise(_ word: String) -> String {
    guard let first = word.first else { return word }
    return String(first).uppercased() + String(word.dropFirst())
}

func longest(_ items: [String]) -> String {
    var best = ""
    for word in items where word.count > best.count {
        best = word
    }
    return best
}

func letters(_ items: [String]) -> Int {
    var total = 0
    for word in items {
        total += word.count
    }
    return total
}

let items = words(TEXT)
var title: [String] = []
for word in items {
    title.append(capitalise(word))
}
print(title.joined(separator: " | "))
print(items.count, longest(items), letters(items))
"""


def programs() -> list[dict]:
    rows: list[dict] = []
    for text in TEXTS:
        rows.append({"title": f"word frequency: {text[:24]}", "template": "word-freq",
                     "code": _fill(WORD_FREQ, TEXT=_string(text))})
    for records in RECORDS:
        rows.append({"title": f"inventory report: {records[0][0]}", "template": "inventory",
                     "code": _fill(INVENTORY, ROWS=_triples(records))})
        rows.append({"title": f"sort records: {records[0][0]}", "template": "sort-records",
                     "code": _fill(SORT_RECORDS, ROWS=_triples(records))})
    for matrix in MATRICES:
        rows.append({"title": f"matrix {matrix[0]}", "template": "matrix",
                     "code": _fill(MATRIX, MATRIX=_matrix_literal(matrix))})
    for ops in STACK_OPS:
        rows.append({"title": f"stack: {' '.join(ops[:2])}", "template": "stack",
                     "code": _fill(STACK, OPS=_op_list(ops))})
    for values in LISTS:
        rows.append({"title": f"reverse list {list(values)}", "template": "linked-list",
                     "code": _fill(LINKED_LIST, VALUES=_ints(values))})
    for csv_text in CSVS:
        rows.append({"title": f"csv totals: {csv_text.split(',')[0]}", "template": "csv",
                     "code": _fill(CSV, DATA=_string(csv_text))})
    for number in NUMBERS:
        values = (number // 2, number - 1, number, 7, 11, 13, 17, 19)
        rows.append({"title": f"factors up to {number}", "template": "factors",
                     "code": _fill(FACTORS, NUMBERS=_ints(values))})
    for ledger in LEDGERS:
        rows.append({"title": f"ledger from {ledger[0][1]}", "template": "bank",
                     "code": _fill(BANK, OPS=_pairs(ledger))})
    for text in TEXTS:
        rows.append({"title": f"text pipeline: {text[:20]}", "template": "pipeline",
                     "code": _fill(PIPELINE, TEXT=_string(text))})
    return rows
