"""PHP base builds — ten templates, ten parameter variants each.

Every program starts with `<?php`, declares typed functions, and prints its
result with `echo ... . PHP_EOL`. No closing `?>`: a trailing tag is optional and
only risks emitting stray whitespace. Standard library only, no superglobals, no
files, no clock.
"""
from __future__ import annotations

LANGUAGE = "php"

Numbers = (5, 7, 9, 10, 12, 15, 16, 20, 25, 30)
Pairs = ((12, 18), (14, 21), (22, 33), (17, 5), (81, 27), (45, 60),
         (13, 39), (64, 48), (100, 35), (121, 11))
Words = ("the quick brown fox", "one two three", "hello brave new world",
         "go build something", "a b c d e", "ship it today",
         "read the fine manual", "small steps daily", "test then commit",
         "keep it simple")
Arrays = ([5, 3, 9, 1, 7], [10, 2, 33, 4], [8, 8, 2, 6], [1, 2, 3],
          [9, 5, 5, 1, 0], [42, 7, 13], [3, 1, 4, 1, 5], [2, 6, 4],
          [11, 22, 33, 44], [7, 0, 9, 2])
Tables = (3, 4, 5, 6, 7, 8, 9, 11, 12, 13)


def _array(values) -> str:
    return "[" + ", ".join(str(value) for value in values) + "]"


def _sum_to_n(n: int) -> str:
    return (
        "<?php\n"
        "function total(int $n): int\n"
        "{\n"
        "    $sum = 0;\n"
        "    for ($i = 1; $i <= $n; $i++) {\n"
        "        $sum += $i;\n"
        "    }\n"
        "    return $sum;\n"
        "}\n\n"
        "echo total(" + str(n) + ") . PHP_EOL;\n"
    )


def _factorial(n: int) -> str:
    return (
        "<?php\n"
        "function factorial(int $n): int|float\n"
        "{\n"
        "    $result = 1;\n"
        "    for ($i = 2; $i <= $n; $i++) {\n"
        "        $result *= $i;\n"
        "    }\n"
        "    return $result;\n"
        "}\n\n"
        "echo factorial(" + str(n) + ") . PHP_EOL;\n"
    )


def _fibonacci(n: int) -> str:
    return (
        "<?php\n"
        "function fib(int $n): array\n"
        "{\n"
        "    $out = [];\n"
        "    $a = 0;\n"
        "    $b = 1;\n"
        "    for ($i = 0; $i < $n; $i++) {\n"
        "        $out[] = $a;\n"
        "        $next = $a + $b;\n"
        "        $a = $b;\n"
        "        $b = $next;\n"
        "    }\n"
        "    return $out;\n"
        "}\n\n"
        "echo implode(' ', fib(" + str(n) + ")) . PHP_EOL;\n"
    )


def _primes(n: int) -> str:
    return (
        "<?php\n"
        "function primes(int $n): array\n"
        "{\n"
        "    $found = [];\n"
        "    for ($value = 2; $value <= $n; $value++) {\n"
        "        $isPrime = true;\n"
        "        for ($d = 2; $d < $value; $d++) {\n"
        "            if ($value % $d === 0) {\n"
        "                $isPrime = false;\n"
        "                break;\n"
        "            }\n"
        "        }\n"
        "        if ($isPrime) {\n"
        "            $found[] = $value;\n"
        "        }\n"
        "    }\n"
        "    return $found;\n"
        "}\n\n"
        "echo implode(',', primes(" + str(n) + ")) . PHP_EOL;\n"
    )


def _gcd(a: int, b: int) -> str:
    return (
        "<?php\n"
        "function gcd(int $a, int $b): int\n"
        "{\n"
        "    $x = $a;\n"
        "    $y = $b;\n"
        "    while ($y !== 0) {\n"
        "        $next = $x % $y;\n"
        "        $x = $y;\n"
        "        $y = $next;\n"
        "    }\n"
        "    return $x;\n"
        "}\n\n"
        "echo gcd(" + str(a) + ", " + str(b) + ") . PHP_EOL;\n"
    )


def _vowels(text: str) -> str:
    return (
        "<?php\n"
        "const TEXT = '" + text + "';\n\n"
        "function vowels(string $text): int\n"
        "{\n"
        "    $count = 0;\n"
        "    $lower = strtolower($text);\n"
        "    for ($i = 0; $i < strlen($lower); $i++) {\n"
        "        if (strpos('aeiou', $lower[$i]) !== false) {\n"
        "            $count++;\n"
        "        }\n"
        "    }\n"
        "    return $count;\n"
        "}\n\n"
        "echo vowels(TEXT) . PHP_EOL;\n"
    )


def _reverse_words(text: str) -> str:
    return (
        "<?php\n"
        "const TEXT = '" + text + "';\n\n"
        "function reverseWords(string $text): string\n"
        "{\n"
        "    return implode(' ', array_reverse(explode(' ', $text)));\n"
        "}\n\n"
        "echo reverseWords(TEXT) . PHP_EOL;\n"
    )


def _bubble(values) -> str:
    return (
        "<?php\n"
        "const VALUES = " + _array(values) + ";\n\n"
        "function bubble(array $values): array\n"
        "{\n"
        "    $items = $values;\n"
        "    $count = count($items);\n"
        "    for ($i = 0; $i < $count; $i++) {\n"
        "        for ($j = 0; $j < $count - 1 - $i; $j++) {\n"
        "            if ($items[$j] > $items[$j + 1]) {\n"
        "                $held = $items[$j];\n"
        "                $items[$j] = $items[$j + 1];\n"
        "                $items[$j + 1] = $held;\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "    return $items;\n"
        "}\n\n"
        "echo implode(',', bubble(VALUES)) . PHP_EOL;\n"
    )


def _stats(values) -> str:
    return (
        "<?php\n"
        "const VALUES = " + _array(values) + ";\n\n"
        "function stats(array $values): array\n"
        "{\n"
        "    return [min($values), max($values), array_sum($values) / count($values)];\n"
        "}\n\n"
        "$parts = stats(VALUES);\n"
        "echo $parts[0] . ' ' . $parts[1] . ' ' . sprintf('%.2f', $parts[2]) . PHP_EOL;\n"
    )


def _table(n: int) -> str:
    return (
        "<?php\n"
        "function table(int $n): void\n"
        "{\n"
        "    for ($i = 1; $i <= 5; $i++) {\n"
        "        echo $n . ' x ' . $i . ' = ' . ($n * $i) . PHP_EOL;\n"
        "    }\n"
        "}\n\n"
        "table(" + str(n) + ");\n"
    )


def programs() -> list[dict]:
    rows: list[dict] = []
    for n in Numbers:
        rows.append({"title": f"sum to {n}", "template": "sum",
                     "code": _sum_to_n(n)})
    for n in Numbers:
        rows.append({"title": f"factorial {n}", "template": "factorial",
                     "code": _factorial(n)})
    for n in Numbers:
        rows.append({"title": f"first {n} fibonacci", "template": "fibonacci",
                     "code": _fibonacci(n)})
    for n in Numbers:
        rows.append({"title": f"primes up to {n}", "template": "primes",
                     "code": _primes(n)})
    for n in Tables:
        rows.append({"title": f"{n} times table", "template": "table",
                     "code": _table(n)})
    for a, b in Pairs:
        rows.append({"title": f"gcd {a} {b}", "template": "gcd",
                     "code": _gcd(a, b)})
    for text in Words:
        rows.append({"title": f"count vowels in '{text}'", "template": "vowels",
                     "code": _vowels(text)})
    for text in Words:
        rows.append({"title": f"reverse words in '{text}'", "template": "reverse",
                     "code": _reverse_words(text)})
    for values in Arrays:
        rows.append({"title": f"sort {list(values)}", "template": "sort",
                     "code": _bubble(values)})
    for values in Arrays:
        rows.append({"title": f"stats of {list(values)}", "template": "stats",
                     "code": _stats(values)})
    return rows
