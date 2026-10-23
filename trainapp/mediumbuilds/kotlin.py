"""Kotlin medium builds — ten multi-function templates, ten data variants each.

Same shape as the Swift module: money in integer cents (no locale-dependent
formatting), a dictionary or list carrying state between functions, and one
`fun main()` printing a deterministic report. No imports.
"""
from __future__ import annotations

LANGUAGE = "kotlin"

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
    return "listOf(" + ", ".join(
        f"Triple({_string(name)}, {qty}, {price})" for name, qty, price in records) + ")"


def _matrix_literal(matrix: tuple) -> str:
    rows = ", ".join(
        "listOf(" + ", ".join(str(value) for value in row) + ")" for row in matrix)
    return f"listOf({rows})"


def _ints(values: tuple) -> str:
    return "listOf(" + ", ".join(str(value) for value in values) + ")"


def _op_list(ops: tuple) -> str:
    return "listOf(" + ", ".join(_string(op) for op in ops) + ")"


def _pairs(pairs: tuple) -> str:
    return "listOf(" + ", ".join(
        f"Pair({_string(name)}, {amount})" for name, amount in pairs) + ")"


WORD_FREQ = """val TEXT = @TEXT@

fun tokens(text: String): List<String> = text.split(" ")

fun counts(words: List<String>): Map<String, Int> {
    val table = mutableMapOf<String, Int>()
    for (word in words) {
        table[word] = (table[word] ?: 0) + 1
    }
    return table
}

fun ranked(table: Map<String, Int>): List<Pair<String, Int>> =
    table.toList().sortedWith(
        compareByDescending<Pair<String, Int>> { it.second }.thenBy { it.first })

fun report(rows: List<Pair<String, Int>>): String =
    rows.take(4).joinToString("\\n") { it.first + ": " + it.second }

fun main() {
    println(report(ranked(counts(tokens(TEXT)))))
}
"""

INVENTORY = """val STOCK = @ROWS@

fun available(stock: List<Triple<String, Int, Int>>): List<Triple<String, Int, Int>> =
    stock.filter { it.second > 0 }

fun totalCents(rows: List<Triple<String, Int, Int>>): Int =
    rows.sumOf { it.second * it.third }

fun lines(rows: List<Triple<String, Int, Int>>): List<String> =
    rows.map { it.first + " " + it.second + " x " + it.third + "c = " + (it.second * it.third) + "c" }

fun main() {
    val rows = available(STOCK)
    println(lines(rows).joinToString("\\n"))
    println("total " + totalCents(rows) + "c")
}
"""

MATRIX = """val MATRIX = @MATRIX@

fun transpose(matrix: List<List<Int>>): List<List<Int>> {
    val out = mutableListOf<List<Int>>()
    for (index in matrix[0].indices) {
        val row = mutableListOf<Int>()
        for (source in matrix) {
            row.add(source[index])
        }
        out.add(row)
    }
    return out
}

fun rowSums(matrix: List<List<Int>>): List<Int> = matrix.map { it.sum() }

fun render(matrix: List<List<Int>>): String =
    matrix.joinToString("\\n") { it.joinToString(" ") }

fun main() {
    println(render(transpose(MATRIX)))
    println("sums " + rowSums(MATRIX).joinToString(" "))
}
"""

STACK = """val OPS = @OPS@

class Stack {
    private val items = mutableListOf<Int>()

    fun push(value: Int) {
        items.add(value)
    }

    fun pop(): Int? = if (items.isEmpty()) null else items.removeAt(items.size - 1)

    fun peek(): Int? = items.lastOrNull()
}

fun run(stack: Stack, ops: List<String>): List<String> {
    val out = mutableListOf<String>()
    for (op in ops) {
        val parts = op.split(" ")
        when (parts[0]) {
            "push" -> {
                stack.push(parts[1].toInt())
                out.add("push " + parts[1])
            }
            "pop" -> out.add("pop " + (stack.pop() ?: -1))
            else -> out.add("peek " + (stack.peek() ?: -1))
        }
    }
    return out
}

fun main() {
    println(run(Stack(), OPS).joinToString("\\n"))
}
"""

LINKED_LIST = """val VALUES = @VALUES@

class Node(val value: Int, var next: Node? = null)

fun build(values: List<Int>): Node? {
    var head: Node? = null
    for (value in values.reversed()) {
        head = Node(value, head)
    }
    return head
}

fun reverse(head: Node?): Node? {
    var previous: Node? = null
    var current = head
    while (current != null) {
        val following = current.next
        current.next = previous
        previous = current
        current = following
    }
    return previous
}

fun render(head: Node?): String {
    val parts = mutableListOf<String>()
    var cursor = head
    while (cursor != null) {
        parts.add(cursor.value.toString())
        cursor = cursor.next
    }
    return parts.joinToString(" -> ")
}

fun main() {
    val head = build(VALUES)
    println(render(head))
    println(render(reverse(head)))
}
"""

CSV = """val DATA = @DATA@

fun parse(data: String): Pair<List<String>, List<List<String>>> {
    val lines = data.trim().split("\\n").filter { it.isNotEmpty() }
    val header = lines[0].split(",")
    val rows = lines.drop(1).map { it.split(",") }
    return Pair(header, rows)
}

fun totals(header: List<String>, rows: List<List<String>>): List<Pair<String, Int>> {
    val out = mutableListOf<Pair<String, Int>>()
    for (index in 1 until header.size) {
        var total = 0
        for (row in rows) {
            total += row[index].toIntOrNull() ?: 0
        }
        out.add(Pair(header[index], total))
    }
    return out
}

fun main() {
    val (header, rows) = parse(DATA)
    println("rows " + rows.size)
    for ((name, total) in totals(header, rows)) {
        println(name + ": " + total)
    }
}
"""

SORT_RECORDS = """val ROWS = @ROWS@

fun byValue(rows: List<Triple<String, Int, Int>>): List<Triple<String, Int, Int>> =
    rows.sortedWith(
        compareByDescending<Triple<String, Int, Int>> { it.second * it.third }
            .thenBy { it.first })

fun byName(rows: List<Triple<String, Int, Int>>): List<Triple<String, Int, Int>> =
    rows.sortedBy { it.first }

fun render(rows: List<Triple<String, Int, Int>>): String =
    rows.joinToString(", ") { it.first + "(" + it.second + ")" }

fun main() {
    println("value " + render(byValue(ROWS)))
    println("name  " + render(byName(ROWS)))
}
"""

FACTORS = """val NUMBERS = @NUMBERS@

fun factorise(value: Int): List<Int> {
    val out = mutableListOf<Int>()
    var rest = value
    var divisor = 2
    while (divisor * divisor <= rest) {
        while (rest % divisor == 0) {
            out.add(divisor)
            rest /= divisor
        }
        divisor += 1
    }
    if (rest > 1) {
        out.add(rest)
    }
    return out
}

fun table(numbers: List<Int>): List<Pair<Int, List<Int>>> =
    numbers.map { Pair(it, factorise(it)) }

fun main() {
    for ((number, parts) in table(NUMBERS)) {
        println(number.toString() + ": " + parts.joinToString(" x "))
    }
}
"""

BANK = """val OPS = @OPS@

class Account(opening: Int) {
    var balance: Int = opening
    val log = mutableListOf<Triple<String, Int, Int>>()

    fun deposit(amount: Int) {
        balance += amount
        log.add(Triple("deposit", amount, balance))
    }

    fun withdraw(amount: Int) {
        if (amount > balance) {
            log.add(Triple("refused", amount, balance))
            return
        }
        balance -= amount
        log.add(Triple("withdraw", amount, balance))
    }
}

fun main() {
    val account = Account(OPS[0].second)
    account.log.add(Triple("open", OPS[0].second, OPS[0].second))
    for ((kind, amount) in OPS.drop(1)) {
        if (kind == "deposit") account.deposit(amount) else account.withdraw(amount)
    }
    for ((kind, amount, balance) in account.log) {
        println(kind + " " + amount + " -> " + balance)
    }
}
"""

PIPELINE = """val TEXT = @TEXT@

fun words(text: String): List<String> = text.split(" ")

fun capitalise(word: String): String =
    if (word.isEmpty()) word else word[0].uppercase() + word.substring(1)

fun longest(items: List<String>): String =
    items.maxByOrNull { it.length } ?: ""

fun letters(items: List<String>): Int = items.sumOf { it.length }

fun main() {
    val items = words(TEXT)
    println(items.joinToString(" | ") { capitalise(it) })
    println(items.size.toString() + " " + longest(items) + " " + letters(items))
}
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
