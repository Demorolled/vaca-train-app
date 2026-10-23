"""Python base builds — ten templates, ten parameter variants each.

The pattern every language module follows: build the code as a string, keep it
small enough to read at a glance, make it print exactly one deterministic
result, and never touch stdin, the clock, the network or the filesystem.
"""
from __future__ import annotations

LANGUAGE = "python"

Numbers = (5, 7, 9, 10, 12, 15, 16, 20, 25, 30)
# Factorials need their own tuple: clamping the shared numbers at 20 would emit
# the same program three times and dedupe below the 100-per-language target.
Factorials = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
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


def _sum_to_n(n: int) -> str:
    return (f"def total(n):\n"
            f"    return sum(range(1, n + 1))\n\n"
            f"print(total({n}))\n")


def _factorial(n: int) -> str:
    return (f"def factorial(n):\n"
            f"    result = 1\n"
            f"    for i in range(2, n + 1):\n"
            f"        result *= i\n"
            f"    return result\n\n"
            f"print(factorial({n}))\n")


def _fibonacci(n: int) -> str:
    return (f"def fib(n):\n"
            f"    a, b = 0, 1\n"
            f"    out = []\n"
            f"    for _ in range(n):\n"
            f"        out.append(a)\n"
            f"        a, b = b, a + b\n"
            f"    return out\n\n"
            f"print(' '.join(str(x) for x in fib({n})))\n")


def _primes(n: int) -> str:
    return (f"def primes(n):\n"
            f"    found = []\n"
            f"    for value in range(2, n + 1):\n"
            f"        if all(value % p for p in range(2, value)):\n"
            f"            found.append(value)\n"
            f"    return found\n\n"
            f"print(','.join(str(p) for p in primes({n})))\n")


def _gcd(a: int, b: int) -> str:
    return (f"def gcd(a, b):\n"
            f"    while b:\n"
            f"        a, b = b, a % b\n"
            f"    return a\n\n"
            f"print(gcd({a}, {b}))\n")


def _vowels(text: str) -> str:
    return (f"TEXT = {text!r}\n\n"
            f"def vowels(text):\n"
            f"    return sum(1 for ch in text.lower() if ch in 'aeiou')\n\n"
            f"print(vowels(TEXT))\n")


def _reverse_words(text: str) -> str:
    return (f"TEXT = {text!r}\n\n"
            f"def reverse_words(text):\n"
            f"    return ' '.join(reversed(text.split()))\n\n"
            f"print(reverse_words(TEXT))\n")


def _bubble(values: tuple[int, ...]) -> str:
    return (f"VALUES = {list(values)!r}\n\n"
            f"def bubble(values):\n"
            f"    items = list(values)\n"
            f"    for i in range(len(items)):\n"
            f"        for j in range(len(items) - 1 - i):\n"
            f"            if items[j] > items[j + 1]:\n"
            f"                items[j], items[j + 1] = items[j + 1], items[j]\n"
            f"    return items\n\n"
            f"print(','.join(str(v) for v in bubble(VALUES)))\n")


def _stats(values: tuple[int, ...]) -> str:
    return (f"VALUES = {list(values)!r}\n\n"
            f"def stats(values):\n"
            f"    return min(values), max(values), sum(values) / len(values)\n\n"
            f"low, high, mean = stats(VALUES)\n"
            f"print(f'{{low}} {{high}} {{mean:.2f}}')\n")


def _table(n: int) -> str:
    return (f"def table(n):\n"
            f"    for i in range(1, 6):\n"
            f"        print(f'{{n}} x {{i}} = {{n * i}}')\n\n"
            f"table({n})\n")


def programs() -> list[dict]:
    rows: list[dict] = []
    for n in Numbers:
        rows.append({"title": f"sum to {n}", "template": "sum",
                     "code": _sum_to_n(n)})
        rows.append({"title": f"first {n} fibonacci", "template": "fibonacci",
                     "code": _fibonacci(n)})
        rows.append({"title": f"primes up to {n}", "template": "primes",
                     "code": _primes(n)})
        rows.append({"title": f"{n} times table", "template": "table",
                     "code": _table(n)})
    for n in Factorials:
        rows.append({"title": f"factorial {n}", "template": "factorial",
                     "code": _factorial(n)})
    for a, b in Pairs:
        rows.append({"title": f"gcd {a} {b}", "template": "gcd",
                     "code": _gcd(a, b)})
    for text in Words:
        rows.append({"title": f"count vowels in '{text}'", "template": "vowels",
                     "code": _vowels(text)})
        rows.append({"title": f"reverse words in '{text}'", "template": "reverse",
                     "code": _reverse_words(text)})
    for values in Arrays:
        rows.append({"title": f"sort {list(values)}", "template": "sort",
                     "code": _bubble(values)})
        rows.append({"title": f"stats of {list(values)}", "template": "stats",
                     "code": _stats(values)})
    return rows
