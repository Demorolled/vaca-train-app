"""TypeScript base builds — ten templates, ten parameter variants each.

These are typechecked by `tsc --noEmit` with `strict: false`, target es2020 and
the DOM lib, so declarations are explicit (`number`, `number[]`, `string`) and
nothing imports a package: the program must stand alone with no `@types/node`.
"""
from __future__ import annotations

LANGUAGE = "typescript"

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
        "function total(n: number): number {\n"
        "  let sum: number = 0;\n"
        "  for (let i: number = 1; i <= n; i += 1) {\n"
        "    sum += i;\n"
        "  }\n"
        "  return sum;\n"
        "}\n\n"
        "console.log(total(" + str(n) + "));\n"
    )


def _factorial(n: int) -> str:
    return (
        "function factorial(n: number): number {\n"
        "  let result: number = 1;\n"
        "  for (let i: number = 2; i <= n; i += 1) {\n"
        "    result *= i;\n"
        "  }\n"
        "  return result;\n"
        "}\n\n"
        "console.log(factorial(" + str(n) + "));\n"
    )


def _fibonacci(n: int) -> str:
    return (
        "function fib(n: number): number[] {\n"
        "  const out: number[] = [];\n"
        "  let a: number = 0;\n"
        "  let b: number = 1;\n"
        "  for (let i: number = 0; i < n; i += 1) {\n"
        "    out.push(a);\n"
        "    const next: number = a + b;\n"
        "    a = b;\n"
        "    b = next;\n"
        "  }\n"
        "  return out;\n"
        "}\n\n"
        "console.log(fib(" + str(n) + ").join(' '));\n"
    )


def _primes(n: int) -> str:
    return (
        "function primes(n: number): number[] {\n"
        "  const found: number[] = [];\n"
        "  for (let value: number = 2; value <= n; value += 1) {\n"
        "    let isPrime: boolean = true;\n"
        "    for (let d: number = 2; d < value; d += 1) {\n"
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
        "function gcd(a: number, b: number): number {\n"
        "  let x: number = a;\n"
        "  let y: number = b;\n"
        "  while (y !== 0) {\n"
        "    const next: number = x % y;\n"
        "    x = y;\n"
        "    y = next;\n"
        "  }\n"
        "  return x;\n"
        "}\n\n"
        "console.log(gcd(" + str(a) + ", " + str(b) + "));\n"
    )


def _vowels(text: str) -> str:
    return (
        "const TEXT: string = '" + text + "';\n\n"
        "function vowels(text: string): number {\n"
        "  let count: number = 0;\n"
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
        "const TEXT: string = '" + text + "';\n\n"
        "function reverseWords(text: string): string {\n"
        "  return text.split(' ').reverse().join(' ');\n"
        "}\n\n"
        "console.log(reverseWords(TEXT));\n"
    )


def _bubble(values) -> str:
    return (
        "const VALUES: number[] = " + _array(values) + ";\n\n"
        "function bubble(values: number[]): number[] {\n"
        "  const items: number[] = values.slice();\n"
        "  for (let i: number = 0; i < items.length; i += 1) {\n"
        "    for (let j: number = 0; j < items.length - 1 - i; j += 1) {\n"
        "      if (items[j] > items[j + 1]) {\n"
        "        const held: number = items[j];\n"
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
        "const VALUES: number[] = " + _array(values) + ";\n\n"
        "function stats(values: number[]): number[] {\n"
        "  let low: number = values[0];\n"
        "  let high: number = values[0];\n"
        "  let sum: number = 0;\n"
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
        "const parts: number[] = stats(VALUES);\n"
        "console.log(parts[0] + ' ' + parts[1] + ' ' + parts[2].toFixed(2));\n"
    )


def _table(n: int) -> str:
    return (
        "function table(n: number): void {\n"
        "  for (let i: number = 1; i <= 5; i += 1) {\n"
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
