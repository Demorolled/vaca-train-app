"""JavaScript base builds — ten templates, ten parameter variants each.

Same contract as every module here: one file, standard library only, no stdin,
no clock, no randomness, exactly one deterministic result on stdout. Node runs
these directly, so nothing needs compiling or a package.json.
"""
from __future__ import annotations

LANGUAGE = "javascript"

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
        "function total(n) {\n"
        "  let sum = 0;\n"
        "  for (let i = 1; i <= n; i += 1) {\n"
        "    sum += i;\n"
        "  }\n"
        "  return sum;\n"
        "}\n\n"
        "console.log(total(" + str(n) + "));\n"
    )


def _factorial(n: int) -> str:
    return (
        "function factorial(n) {\n"
        "  let result = 1;\n"
        "  for (let i = 2; i <= n; i += 1) {\n"
        "    result *= i;\n"
        "  }\n"
        "  return result;\n"
        "}\n\n"
        "console.log(factorial(" + str(n) + "));\n"
    )


def _fibonacci(n: int) -> str:
    return (
        "function fib(n) {\n"
        "  const out = [];\n"
        "  let a = 0;\n"
        "  let b = 1;\n"
        "  for (let i = 0; i < n; i += 1) {\n"
        "    out.push(a);\n"
        "    const next = a + b;\n"
        "    a = b;\n"
        "    b = next;\n"
        "  }\n"
        "  return out;\n"
        "}\n\n"
        "console.log(fib(" + str(n) + ").join(' '));\n"
    )


def _primes(n: int) -> str:
    return (
        "function primes(n) {\n"
        "  const found = [];\n"
        "  for (let value = 2; value <= n; value += 1) {\n"
        "    let isPrime = true;\n"
        "    for (let d = 2; d < value; d += 1) {\n"
        "      if (value % d === 0) {\n"
        "        isPrime = false;\n"
        "        break;\n"
        "      }\n"
        "    }\n"
        "    if (isPrime) {\n"
        "      found.push(value);\n"
        "    }\n"
        "  }\n"
        "  return found;\n"
        "}\n\n"
        "console.log(primes(" + str(n) + ").join(','));\n"
    )


def _gcd(a: int, b: int) -> str:
    return (
        "function gcd(a, b) {\n"
        "  let x = a;\n"
        "  let y = b;\n"
        "  while (y !== 0) {\n"
        "    const next = x % y;\n"
        "    x = y;\n"
        "    y = next;\n"
        "  }\n"
        "  return x;\n"
        "}\n\n"
        "console.log(gcd(" + str(a) + ", " + str(b) + "));\n"
    )


def _vowels(text: str) -> str:
    return (
        "const TEXT = '" + text + "';\n\n"
        "function vowels(text) {\n"
        "  let count = 0;\n"
        "  for (const ch of text.toLowerCase()) {\n"
        "    if ('aeiou'.includes(ch)) {\n"
        "      count += 1;\n"
        "    }\n"
        "  }\n"
        "  return count;\n"
        "}\n\n"
        "console.log(vowels(TEXT));\n"
    )


def _reverse_words(text: str) -> str:
    return (
        "const TEXT = '" + text + "';\n\n"
        "function reverseWords(text) {\n"
        "  return text.split(' ').reverse().join(' ');\n"
        "}\n\n"
        "console.log(reverseWords(TEXT));\n"
    )


def _bubble(values) -> str:
    return (
        "const VALUES = " + _array(values) + ";\n\n"
        "function bubble(values) {\n"
        "  const items = values.slice();\n"
        "  for (let i = 0; i < items.length; i += 1) {\n"
        "    for (let j = 0; j < items.length - 1 - i; j += 1) {\n"
        "      if (items[j] > items[j + 1]) {\n"
        "        const held = items[j];\n"
        "        items[j] = items[j + 1];\n"
        "        items[j + 1] = held;\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "  return items;\n"
        "}\n\n"
        "console.log(bubble(VALUES).join(','));\n"
    )


def _stats(values) -> str:
    return (
        "const VALUES = " + _array(values) + ";\n\n"
        "function stats(values) {\n"
        "  let low = values[0];\n"
        "  let high = values[0];\n"
        "  let sum = 0;\n"
        "  for (const value of values) {\n"
        "    if (value < low) {\n"
        "      low = value;\n"
        "    }\n"
        "    if (value > high) {\n"
        "      high = value;\n"
        "    }\n"
        "    sum += value;\n"
        "  }\n"
        "  return [low, high, sum / values.length];\n"
        "}\n\n"
        "const parts = stats(VALUES);\n"
        "console.log(parts[0] + ' ' + parts[1] + ' ' + parts[2].toFixed(2));\n"
    )


def _table(n: int) -> str:
    return (
        "function table(n) {\n"
        "  for (let i = 1; i <= 5; i += 1) {\n"
        "    console.log(n + ' x ' + i + ' = ' + n * i);\n"
        "  }\n"
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
