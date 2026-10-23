"""Ruby base builds — ten templates, ten parameter variants each.

Same contract as the Python module: one deterministic result per program, no
stdin, no clock, no network, no filesystem, standard library only.
"""
from __future__ import annotations

LANGUAGE = "ruby"

Numbers = (5, 7, 9, 10, 12, 15, 16, 20, 25, 30)
# Small enough that every language's integer type can hold the result, and all
# ten values distinct so the ten programs cannot collapse into duplicates.
Factorials = (5, 7, 9, 10, 12, 13, 15, 16, 18, 20)
Pairs = ((12, 18), (14, 21), (22, 33), (17, 5), (81, 27), (45, 60),
         (13, 39), (64, 48), (100, 35), (121, 11))
Words = ("the quick brown fox", "one two three", "hello brave new world",
         "go build something", "a b c d e", "ship it today",
         "read the fine manual", "small steps daily", "test then commit",
         "keep it simple")
Arrays = ([5, 3, 9, 1, 7], [10, 2, 33, 4], [8, 8, 2, 6], [1, 2, 3],
          [9, 5, 5, 1, 0], [42, 7, 13], [3, 1, 4, 1, 5], [2, 6, 4],
          [11, 22, 33, 44], [7, 0, 9, 2])


def _sum_to_n(n: int) -> str:
    return ("def total(n)\n"
            "  (1..n).sum\n"
            "end\n\n"
            "puts total(" + str(n) + ")\n")


def _factorial(n: int) -> str:
    return ("def factorial(n)\n"
            "  result = 1\n"
            "  (2..n).each { |i| result *= i }\n"
            "  result\n"
            "end\n\n"
            "puts factorial(" + str(n) + ")\n")


def _fibonacci(n: int) -> str:
    return ("def fib(n)\n"
            "  a = 0\n"
            "  b = 1\n"
            "  out = []\n"
            "  n.times do\n"
            "    out << a\n"
            "    a, b = b, a + b\n"
            "  end\n"
            "  out\n"
            "end\n\n"
            "puts fib(" + str(n) + ").join(' ')\n")


def _primes(n: int) -> str:
    return ("def primes(n)\n"
            "  (2..n).select { |v| (2...v).none? { |d| (v % d).zero? } }\n"
            "end\n\n"
            "puts primes(" + str(n) + ").join(',')\n")


def _gcd(a: int, b: int) -> str:
    return ("def gcd(a, b)\n"
            "  while b > 0\n"
            "    a, b = b, a % b\n"
            "  end\n"
            "  a\n"
            "end\n\n"
            "puts gcd(" + str(a) + ", " + str(b) + ")\n")


def _vowels(text: str) -> str:
    return ("TEXT = " + repr(text) + "\n\n"
            "def vowels(text)\n"
            "  text.downcase.count('aeiou')\n"
            "end\n\n"
            "puts vowels(TEXT)\n")


def _reverse_words(text: str) -> str:
    return ("TEXT = " + repr(text) + "\n\n"
            "def reverse_words(text)\n"
            "  text.split(' ').reverse.join(' ')\n"
            "end\n\n"
            "puts reverse_words(TEXT)\n")


def _bubble(values: tuple[int, ...]) -> str:
    return ("VALUES = " + repr(list(values)) + "\n\n"
            "def bubble(values)\n"
            "  items = values.dup\n"
            "  loop do\n"
            "    swapped = false\n"
            "    (items.length - 1).times do |i|\n"
            "      if items[i] > items[i + 1]\n"
            "        items[i], items[i + 1] = items[i + 1], items[i]\n"
            "        swapped = true\n"
            "      end\n"
            "    end\n"
            "    break unless swapped\n"
            "  end\n"
            "  items\n"
            "end\n\n"
            "puts bubble(VALUES).join(',')\n")


def _stats(values: tuple[int, ...]) -> str:
    return ("VALUES = " + repr(list(values)) + "\n\n"
            "def stats(values)\n"
            "  mean = values.sum.to_f / values.length\n"
            "  [values.min, values.max, mean]\n"
            "end\n\n"
            "low, high, mean = stats(VALUES)\n"
            "puts format('%d %d %.2f', low, high, mean)\n")


def _table(n: int) -> str:
    return ("def table(n)\n"
            "  (1..5).each do |i|\n"
            "    puts \"#{n} x #{i} = #{n * i}\"\n"
            "  end\n"
            "end\n\n"
            "table(" + str(n) + ")\n")


def programs() -> list[dict]:
    rows: list[dict] = []
    for n in Numbers:
        rows.append({"title": "sum to " + str(n), "template": "sum",
                     "code": _sum_to_n(n)})
        rows.append({"title": "first " + str(n) + " fibonacci", "template": "fibonacci",
                     "code": _fibonacci(n)})
        rows.append({"title": "primes up to " + str(n), "template": "primes",
                     "code": _primes(n)})
        rows.append({"title": str(n) + " times table", "template": "table",
                     "code": _table(n)})
    for n in Factorials:
        rows.append({"title": "factorial " + str(n), "template": "factorial",
                     "code": _factorial(n)})
    for a, b in Pairs:
        rows.append({"title": "gcd " + str(a) + " " + str(b), "template": "gcd",
                     "code": _gcd(a, b)})
    for text in Words:
        rows.append({"title": "count vowels in '" + text + "'", "template": "vowels",
                     "code": _vowels(text)})
        rows.append({"title": "reverse words in '" + text + "'", "template": "reverse",
                     "code": _reverse_words(text)})
    for values in Arrays:
        rows.append({"title": "sort " + str(list(values)), "template": "sort",
                     "code": _bubble(values)})
        rows.append({"title": "stats of " + str(list(values)), "template": "stats",
                     "code": _stats(values)})
    return rows
