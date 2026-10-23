"""PHP medium builds — ten templates, ten data variants each.

Every program is a single `<?php` file with at least three functions or methods,
a real data structure between them, and a deterministic multi-line report. No
argv, stdin, files, clock, network or randomness.
"""
from __future__ import annotations

LANGUAGE = "php"

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

LISTS = ((3, 1, 4), (7, 2, 9, 5), (1, 2, 3, 4, 5), (9,), (4, 4, 6),
         (8, 3, 1, 7), (2, 6, 5, 3, 8), (11, 4), (5, 9, 2, 6, 1),
         (10, 20, 30, 40))


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace(f"@{key}@", value)
    return template


def _php_rows(records: tuple) -> str:
    return ", ".join(f"['{name}', {qty}, {price}]" for name, qty, price in records)


def _php_matrix(matrix: tuple) -> str:
    return ", ".join("[" + ", ".join(str(v) for v in row) + "]" for row in matrix)


def _php_list(values: tuple) -> str:
    return "[" + ", ".join(str(v) for v in values) + "]"


WORD_FREQ = """<?php
$TEXT = '@TEXT@';

function tokens(string $text): array {
    return preg_split('/\\s+/', trim($text));
}

function counts(array $words): array {
    $table = [];
    foreach ($words as $word) {
        $table[$word] = ($table[$word] ?? 0) + 1;
    }
    return $table;
}

function ranked(array $table): array {
    $words = array_keys($table);
    usort($words, function (string $a, string $b) use ($table): int {
        if ($table[$a] === $table[$b]) {
            return strcmp($a, $b);
        }
        return $table[$b] <=> $table[$a];
    });
    return $words;
}

$table = counts(tokens($TEXT));
foreach (array_slice(ranked($table), 0, 4) as $word) {
    printf("%s: %d\\n", $word, $table[$word]);
}
"""

INVENTORY = """<?php
$STOCK = [@ROWS@];

function available(array $stock): array {
    return array_values(array_filter($stock, fn(array $row): bool => $row[1] > 0));
}

function total(array $rows): float {
    $sum = 0.0;
    foreach ($rows as $row) {
        $sum += $row[1] * $row[2];
    }
    return $sum;
}

function report(array $rows): array {
    $lines = [];
    foreach ($rows as $row) {
        $lines[] = sprintf('%-8s %3d x %6.2f = %8.2f', $row[0], $row[1], $row[2], $row[1] * $row[2]);
    }
    return $lines;
}

$rows = available($STOCK);
echo implode("\\n", report($rows)), "\\n";
printf("total %.2f\\n", total($rows));
"""

MATRIX = """<?php
$MATRIX = [@MATRIX@];

function transpose(array $matrix): array {
    $out = [];
    foreach ($matrix as $row) {
        foreach ($row as $index => $value) {
            $out[$index][] = $value;
        }
    }
    return $out;
}

function row_sums(array $matrix): array {
    return array_map(fn(array $row): int => array_sum($row), $matrix);
}

function render(array $matrix): string {
    $lines = [];
    foreach ($matrix as $row) {
        $cells = array_map(fn(int $v): string => sprintf('%3d', $v), $row);
        $lines[] = implode(' ', $cells);
    }
    return implode("\\n", $lines);
}

echo render(transpose($MATRIX)), "\\n";
echo 'sums ', implode(' ', row_sums($MATRIX)), "\\n";
"""

STACK = """<?php
class Stack {
    private array $items = [];

    public function push(int $value): void {
        $this->items[] = $value;
    }

    public function pop(): ?int {
        return array_pop($this->items);
    }

    public function peek(): ?int {
        if (count($this->items) === 0) {
            return null;
        }
        return $this->items[count($this->items) - 1];
    }

    public function size(): int {
        return count($this->items);
    }
}

function run(array $ops): array {
    $stack = new Stack();
    $out = [];
    foreach ($ops as $op) {
        $parts = explode(' ', $op);
        if ($parts[0] === 'push') {
            $stack->push((int) $parts[1]);
            $out[] = 'push ' . $parts[1];
        } elseif ($parts[0] === 'pop') {
            $value = $stack->pop();
            $out[] = 'pop ' . ($value === null ? 'none' : (string) $value);
        } else {
            $value = $stack->peek();
            $out[] = 'peek ' . ($value === null ? 'none' : (string) $value);
        }
    }
    return $out;
}

$OPS = [@OPS@];
echo implode("\\n", run($OPS)), "\\n";
echo 'left ', count($OPS) > 0 ? 'ok' : 'empty', "\\n";
"""

LINKED = """<?php
class Node {
    public function __construct(public int $value, public ?Node $next = null) {}
}

$VALUES = @LIST@;

function build(array $values): ?Node {
    $head = null;
    for ($i = count($values) - 1; $i >= 0; $i--) {
        $head = new Node($values[$i], $head);
    }
    return $head;
}

function reverse(?Node $head): ?Node {
    $prev = null;
    while ($head !== null) {
        $next = $head->next;
        $head->next = $prev;
        $prev = $head;
        $head = $next;
    }
    return $prev;
}

function render(?Node $head): string {
    $parts = [];
    while ($head !== null) {
        $parts[] = (string) $head->value;
        $head = $head->next;
    }
    return implode(' -> ', $parts);
}

$head = build($VALUES);
echo render($head), "\\n";
echo render(reverse($head)), "\\n";
"""

CSV = """<?php
$DATA = "@DATA@";

function parse(string $data): array {
    $lines = array_values(array_filter(explode("\\n", trim($data))));
    $header = explode(',', array_shift($lines));
    $rows = array_map(fn(string $line): array => explode(',', $line), $lines);
    return [$header, $rows];
}

function totals(array $header, array $rows): array {
    $out = [];
    for ($i = 1; $i < count($header); $i++) {
        $sum = 0.0;
        foreach ($rows as $row) {
            $sum += is_numeric($row[$i]) ? (float) $row[$i] : 1.0;
        }
        $out[$header[$i]] = $sum;
    }
    return $out;
}

[$header, $rows] = parse($DATA);
echo 'columns ', implode(',', array_slice($header, 1)), "\\n";
foreach (totals($header, $rows) as $name => $value) {
    printf("%s: %.2f\\n", $name, $value);
}
"""

SORT_RECORDS = """<?php
$ROWS = [@ROWS@];

function by_value(array $rows): array {
    usort($rows, function (array $a, array $b): int {
        $left = $a[1] * $a[2];
        $right = $b[1] * $b[2];
        if ($left === $right) {
            return strcmp($a[0], $b[0]);
        }
        return $right <=> $left;
    });
    return $rows;
}

function by_name(array $rows): array {
    usort($rows, fn(array $a, array $b): int => strcmp($a[0], $b[0]));
    return $rows;
}

function render(array $rows): string {
    $parts = [];
    foreach ($rows as $row) {
        $parts[] = sprintf('%s(%d)', $row[0], $row[1]);
    }
    return implode(', ', $parts);
}

echo 'value ', render(by_value($ROWS)), "\\n";
echo 'name  ', render(by_name($ROWS)), "\\n";
"""

FACTORS = """<?php
$NUMBERS = @NUMBERS@;

function factorise(int $value): array {
    $out = [];
    $divisor = 2;
    while ($divisor * $divisor <= $value) {
        while ($value % $divisor === 0) {
            $out[] = $divisor;
            $value = intdiv($value, $divisor);
        }
        $divisor++;
    }
    if ($value > 1) {
        $out[] = $value;
    }
    return $out;
}

function table(array $numbers): array {
    $rows = [];
    foreach ($numbers as $number) {
        $rows[] = [$number, factorise($number)];
    }
    return $rows;
}

foreach (table($NUMBERS) as [$number, $parts]) {
    printf("%d: %s\\n", $number, implode(' x ', $parts));
}
"""

BANK = """<?php
class Account {
    private int $balance;
    public array $log = [];

    public function __construct(int $opening) {
        $this->balance = $opening;
        $this->log[] = ['open', $opening, $opening];
    }

    public function deposit(int $amount): void {
        $this->balance += $amount;
        $this->log[] = ['deposit', $amount, $this->balance];
    }

    public function withdraw(int $amount): bool {
        if ($amount > $this->balance) {
            $this->log[] = ['refused', $amount, $this->balance];
            return false;
        }
        $this->balance -= $amount;
        $this->log[] = ['withdraw', $amount, $this->balance];
        return true;
    }
}

$OPS = [@OPS@];
$account = new Account($OPS[0][1]);
foreach (array_slice($OPS, 1) as [$kind, $amount]) {
    if ($kind === 'deposit') {
        $account->deposit($amount);
    } else {
        $account->withdraw($amount);
    }
}

foreach ($account->log as [$kind, $amount, $balance]) {
    printf("%-9s %4d -> %4d\\n", $kind, $amount, $balance);
}
"""

PIPELINE = """<?php
$TEXT = '@TEXT@';

function words(string $text): array {
    return preg_split('/\\s+/', trim($text));
}

function transform(array $words): array {
    return array_map(fn(string $word): string => ucfirst($word), $words);
}

function longest(array $words): string {
    $best = '';
    foreach ($words as $word) {
        if (strlen($word) > strlen($best)) {
            $best = $word;
        }
    }
    return $best;
}

function report(array $words): string {
    return implode(' | ', transform($words));
}

$items = words($TEXT);
echo report($items), "\\n";
$letters = array_sum(array_map('strlen', $items));
printf("%d %s %d\\n", count($items), longest($items), $letters);
"""


def programs() -> list[dict]:
    rows: list[dict] = []
    for text in TEXTS:
        rows.append({"title": f"word frequency: {text[:24]}", "template": "word-freq",
                     "code": _fill(WORD_FREQ, TEXT=text)})
    for records in RECORDS:
        rows.append({"title": f"inventory report: {records[0][0]}", "template": "inventory",
                     "code": _fill(INVENTORY, ROWS=_php_rows(records))})
        rows.append({"title": f"sort records: {records[0][0]}", "template": "sort-records",
                     "code": _fill(SORT_RECORDS, ROWS=_php_rows(records))})
    for matrix in MATRICES:
        rows.append({"title": f"matrix {matrix[0]}", "template": "matrix",
                     "code": _fill(MATRIX, MATRIX=_php_matrix(matrix))})
    for ops in STACK_OPS:
        literal = ", ".join(f"'{op}'" for op in ops)
        rows.append({"title": f"stack: {' '.join(ops[:2])}", "template": "stack",
                     "code": _fill(STACK, OPS=literal)})
    for values in LISTS:
        rows.append({"title": f"reverse list {list(values)}", "template": "linked-list",
                     "code": _fill(LINKED, LIST=_php_list(values))})
    for data in CSVS:
        escaped = data.replace("\\", "\\\\").replace('"', '\\"')
        rows.append({"title": f"csv totals: {data.split(',')[0]}", "template": "csv",
                     "code": _fill(CSV, DATA=escaped)})
    for n in NUMBERS:
        numbers = [n // 2, n - 1, n, 7, 11, 13, 17, 19]
        rows.append({"title": f"factors up to {n}", "template": "factors",
                     "code": _fill(FACTORS, NUMBERS=_php_list(tuple(numbers)))})
    for ledger in LEDGERS:
        pairs = ", ".join(f"['{kind}', {amount}]" for kind, amount in ledger)
        rows.append({"title": f"ledger from {ledger[0][1]}", "template": "bank",
                     "code": _fill(BANK, OPS=pairs)})
    for text in TEXTS:
        rows.append({"title": f"text pipeline: {text[:20]}", "template": "pipeline",
                     "code": _fill(PIPELINE, TEXT=text)})
    return rows
