"""Python medium builds — ten templates, ten data variants each.

The reference implementation of the pattern: several functions, one data
structure carrying state between them, and a deterministic report on stdout.
Still one file, still no stdin, files, clock, network or randomness.
"""
from __future__ import annotations

LANGUAGE = "python"

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
    ("name,qty,price\nbolt,12,0.50\nnut,40,0.10\nwasher,0,0.05",),
    ("item,units,cost\nhammer,3,36.00\nsaw,0,18.50\ndrill,2,90.00",),
    ("city,pop,area\naustin,964,704\nboston,695,232\ndenver,715,401",),
    ("lang,year,stars\npython,1991,9\nrust,2010,7\ngo,2009,8",),
    ("day,high,low\nmon,21,9\ntue,19,8\nwed,23,12",),
    ("sku,stock,reorder\na1,4,10\nb2,0,5\nc3,18,10",),
    ("team,wins,losses\nred,7,3\nblue,5,5\ngreen,9,1",),
    ("route,km,minutes\nalpha,12,18\nbeta,7,9\ngamma,25,31",),
    ("book,parts,pages\none,3,120\ntwo,1,40\nthree,5,260",),
    ("part,width,height\nframe,80,120\npanel,40,60\ndoor,90,200",),
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


def _word_freq(text: str) -> str:
    return (
        f"TEXT = {text!r}\n\n"
        "def tokens(text):\n"
        "    return text.split()\n\n"
        "def counts(words):\n"
        "    table = {}\n"
        "    for word in words:\n"
        "        table[word] = table.get(word, 0) + 1\n"
        "    return table\n\n"
        "def ranked(table):\n"
        "    return sorted(table.items(), key=lambda pair: (-pair[1], pair[0]))\n\n"
        "def report(rows):\n"
        "    return '\\n'.join(f'{word}: {count}' for word, count in rows[:4])\n\n"
        "print(report(ranked(counts(tokens(TEXT)))))\n"
    )


def _inventory(records: tuple) -> str:
    items = ", ".join(f"({name!r}, {qty}, {price})" for name, qty, price in records)
    return (
        f"STOCK = [{items}]\n\n"
        "def available(stock):\n"
        "    return [row for row in stock if row[1] > 0]\n\n"
        "def value(rows):\n"
        "    return sum(qty * price for _, qty, price in rows)\n\n"
        "def lines(rows):\n"
        "    out = []\n"
        "    for name, qty, price in rows:\n"
        "        out.append(f'{name:<8} {qty:>3} x {price:>6.2f} = {qty * price:>8.2f}')\n"
        "    return out\n\n"
        "rows = available(STOCK)\n"
        "print('\\n'.join(lines(rows)))\n"
        "print(f'total {value(rows):.2f}')\n"
    )


def _matrix(matrix: tuple) -> str:
    rows = ", ".join(str(list(row)) for row in matrix)
    return (
        f"MATRIX = [{rows}]\n\n"
        "def transpose(matrix):\n"
        "    return [[row[i] for row in matrix] for i in range(len(matrix[0]))]\n\n"
        "def row_sums(matrix):\n"
        "    return [sum(row) for row in matrix]\n\n"
        "def render(matrix):\n"
        "    return '\\n'.join(' '.join(f'{value:>3}' for value in row) for row in matrix)\n\n"
        "print(render(transpose(MATRIX)))\n"
        "print('sums', *row_sums(MATRIX))\n"
    )


def _stack(ops: tuple) -> str:
    calls = "\n".join(f"    {op!r}," for op in ops)
    return (
        "class Stack:\n"
        "    def __init__(self):\n"
        "        self.items = []\n\n"
        "    def push(self, value):\n"
        "        self.items.append(value)\n\n"
        "    def pop(self):\n"
        "        return self.items.pop() if self.items else None\n\n"
        "    def peek(self):\n"
        "        return self.items[-1] if self.items else None\n\n"
        "def run(stack, ops):\n"
        "    out = []\n"
        "    for op in ops:\n"
        "        name, _, arg = op.partition(' ')\n"
        "        if name == 'push':\n"
        "            stack.push(int(arg))\n"
        "            out.append(f'push {arg}')\n"
        "        elif name == 'pop':\n"
        "            out.append(f'pop {stack.pop()}')\n"
        "        else:\n"
        "            out.append(f'peek {stack.peek()}')\n"
        "    return out\n\n"
        "OPS = [\n"
        f"{calls}\n"
        "]\n"
        "print('\\n'.join(run(Stack(), OPS)))\n"
    )


def _linked_list(values: tuple) -> str:
    return (
        f"VALUES = {list(values)!r}\n\n"
        "class Node:\n"
        "    def __init__(self, value, nxt=None):\n"
        "        self.value = value\n"
        "        self.next = nxt\n\n"
        "def build(values):\n"
        "    head = None\n"
        "    for value in reversed(values):\n"
        "        head = Node(value, head)\n"
        "    return head\n\n"
        "def reverse(head):\n"
        "    prev = None\n"
        "    while head:\n"
        "        head.next, prev, head = prev, head, head.next\n"
        "    return prev\n\n"
        "def render(head):\n"
        "    out = []\n"
        "    while head:\n"
        "        out.append(str(head.value))\n"
        "        head = head.next\n"
        "    return ' -> '.join(out)\n\n"
        "head = build(VALUES)\n"
        "print(render(head))\n"
        "print(render(reverse(head)))\n"
    )


def _csv(csv_text: str) -> str:
    return (
        f"DATA = {csv_text!r}\n\n"
        "def parse(data):\n"
        "    lines = [line for line in data.strip().splitlines() if line]\n"
        "    header = lines[0].split(',')\n"
        "    rows = [line.split(',') for line in lines[1:]]\n"
        "    return header, rows\n\n"
        "def totals(header, rows):\n"
        "    out = {}\n"
        "    for index, name in enumerate(header[1:], start=1):\n"
        "        try:\n"
        "            out[name] = sum(float(row[index]) for row in rows)\n"
        "        except ValueError:\n"
        "            out[name] = float(len(rows))\n"
        "    return out\n\n"
        "header, rows = parse(DATA)\n"
        "print('columns', ','.join(header[1:]))\n"
        "for name, value in totals(header, rows).items():\n"
        "    print(f'{name}: {value:.2f}')\n"
    )


def _sort_records(records: tuple) -> str:
    items = ", ".join(f"({name!r}, {qty}, {price})" for name, qty, price in records)
    return (
        f"ROWS = [{items}]\n\n"
        "def by_value(rows):\n"
        "    return sorted(rows, key=lambda row: (-row[1] * row[2], row[0]))\n\n"
        "def by_name(rows):\n"
        "    return sorted(rows, key=lambda row: row[0])\n\n"
        "def render(rows):\n"
        "    return ', '.join(f'{name}({qty})' for name, qty, _ in rows)\n\n"
        "def total_value(rows):\n"
        "    return sum(qty * price for _, qty, price in rows)\n\n"
        "print('value', render(by_value(ROWS)))\n"
        "print('name ', render(by_name(ROWS)))\n"
        "print('total', total_value(ROWS))\n"
    )


def _factors(n: int) -> str:
    return (
        # Distinct per input: a sliced range collapses (28 and 30 produce the
        # same eight numbers), which would ship the same program twice.
        f"NUMBERS = {[n // 2, n - 1, n, 7, 11, 13, 17, 19]}\n\n"
        "def factorise(value):\n"
        "    out = []\n"
        "    divisor = 2\n"
        "    while divisor * divisor <= value:\n"
        "        while value % divisor == 0:\n"
        "            out.append(divisor)\n"
        "            value //= divisor\n"
        "        divisor += 1\n"
        "    if value > 1:\n"
        "        out.append(value)\n"
        "    return out\n\n"
        "def table(numbers):\n"
        "    return [(n, factorise(n)) for n in numbers]\n\n"
        "for number, parts in table(NUMBERS):\n"
        "    print(f'{number}: ' + ' x '.join(str(part) for part in parts))\n"
    )


def _bank(ledger: tuple) -> str:
    ops = ", ".join(f"({kind!r}, {amount})" for kind, amount in ledger)
    return (
        "class Account:\n"
        "    def __init__(self, opening):\n"
        "        self.balance = opening\n"
        "        self.log = []\n\n"
        "    def deposit(self, amount):\n"
        "        self.balance += amount\n"
        "        self.log.append(('deposit', amount, self.balance))\n\n"
        "    def withdraw(self, amount):\n"
        "        if amount > self.balance:\n"
        "            self.log.append(('refused', amount, self.balance))\n"
        "            return False\n"
        "        self.balance -= amount\n"
        "        self.log.append(('withdraw', amount, self.balance))\n"
        "        return True\n\n"
        f"OPS = [{ops}]\n\n"
        "account = Account(OPS[0][1])\n"
        "account.log.append(('open', OPS[0][1], OPS[0][1]))\n"
        "for kind, amount in OPS[1:]:\n"
        "    account.deposit(amount) if kind == 'deposit' else account.withdraw(amount)\n\n"
        "for kind, amount, balance in account.log:\n"
        "    print(f'{kind:<9} {amount:>4} -> {balance:>4}')\n"
    )


def _pipeline(text: str) -> str:
    return (
        f"TEXT = {text!r}\n\n"
        "def words(text):\n"
        "    return text.split()\n\n"
        "def transform(words):\n"
        "    return [word.capitalize() for word in words]\n\n"
        "def longest(words):\n"
        "    return max(words, key=len) if words else ''\n\n"
        "def report(words):\n"
        "    return ' | '.join(transform(words))\n\n"
        "items = words(TEXT)\n"
        "print(report(items))\n"
        "print(len(items), longest(items), sum(len(word) for word in items))\n"
    )


def programs() -> list[dict]:
    rows: list[dict] = []
    for text in TEXTS:
        rows.append({"title": f"word frequency: {text[:24]}", "template": "word-freq",
                     "code": _word_freq(text)})
    for records in RECORDS:
        rows.append({"title": f"inventory report: {records[0][0]}", "template": "inventory",
                     "code": _inventory(records)})
        rows.append({"title": f"sort records: {records[0][0]}", "template": "sort-records",
                     "code": _sort_records(records)})
    for matrix in MATRICES:
        rows.append({"title": f"matrix {matrix[0]}", "template": "matrix",
                     "code": _matrix(matrix)})
    for ops in STACK_OPS:
        rows.append({"title": f"stack: {' '.join(ops[:2])}", "template": "stack",
                     "code": _stack(ops)})
    for values in ((3, 1, 4), (7, 2, 9, 5), (1, 2, 3, 4, 5), (9,), (4, 4, 6),
                   (8, 3, 1, 7), (2, 6, 5, 3, 8), (11, 4), (5, 9, 2, 6, 1),
                   (10, 20, 30, 40)):
        rows.append({"title": f"reverse list {list(values)}", "template": "linked-list",
                     "code": _linked_list(values)})
    for csv_text in CSVS:
        rows.append({"title": f"csv totals: {csv_text[0].split(',')[0]}", "template": "csv",
                     "code": _csv(csv_text[0])})
    for n in NUMBERS:
        rows.append({"title": f"factors up to {n}", "template": "factors",
                     "code": _factors(n)})
    for ledger in LEDGERS:
        rows.append({"title": f"ledger from {ledger[0][1]}", "template": "bank",
                     "code": _bank(ledger)})
    for text in TEXTS:
        rows.append({"title": f"text pipeline: {text[:20]}", "template": "pipeline",
                     "code": _pipeline(text)})
    return rows
