"""Swift base builds — ten templates, ten parameter variants each.

Same contract as the Python module. Formatting helpers that need Foundation are
avoided on purpose: these programs print with `print(...)` (which separates its
arguments with spaces) so the toolchain stays standard-library only.
"""
from __future__ import annotations

LANGUAGE = "swift"

Numbers = (5, 7, 9, 10, 12, 15, 16, 20, 25, 30)
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
    return ("func total(_ n: Int) -> Int {\n"
            "    var sum = 0\n"
            "    for value in 1...n {\n"
            "        sum += value\n"
            "    }\n"
            "    return sum\n"
            "}\n\n"
            "print(total(" + str(n) + "))\n")


def _factorial(n: int) -> str:
    return ("func factorial(_ n: Int) -> Int {\n"
            "    var result = 1\n"
            "    for value in 2...n {\n"
            "        result *= value\n"
            "    }\n"
            "    return result\n"
            "}\n\n"
            "print(factorial(" + str(n) + "))\n")


def _fibonacci(n: int) -> str:
    return ("func fib(_ n: Int) -> [Int] {\n"
            "    var a = 0\n"
            "    var b = 1\n"
            "    var out: [Int] = []\n"
            "    for _ in 0..<n {\n"
            "        out.append(a)\n"
            "        let next = a + b\n"
            "        a = b\n"
            "        b = next\n"
            "    }\n"
            "    return out\n"
            "}\n\n"
            "let sequence = fib(" + str(n) + ").map { String($0) }\n"
            "print(sequence.joined(separator: \" \"))\n")


def _primes(n: int) -> str:
    return ("func isPrime(_ value: Int) -> Bool {\n"
            "    if value < 2 {\n"
            "        return false\n"
            "    }\n"
            "    var factor = 2\n"
            "    while factor * factor <= value {\n"
            "        if value % factor == 0 {\n"
            "            return false\n"
            "        }\n"
            "        factor += 1\n"
            "    }\n"
            "    return true\n"
            "}\n\n"
            "let found = (2..." + str(n) + ").filter { isPrime($0) }\n"
            "print(found.map { String($0) }.joined(separator: \",\"))\n")


def _gcd(a: int, b: int) -> str:
    return ("func gcd(_ a: Int, _ b: Int) -> Int {\n"
            "    var x = a\n"
            "    var y = b\n"
            "    while y != 0 {\n"
            "        let remainder = x % y\n"
            "        x = y\n"
            "        y = remainder\n"
            "    }\n"
            "    return x\n"
            "}\n\n"
            "print(gcd(" + str(a) + ", " + str(b) + "))\n")


def _vowels(text: str) -> str:
    return ("let text = " + repr(text).replace("'", '"') + "\n\n"
            "func vowels(_ text: String) -> Int {\n"
            "    let letters: Set<Character> = Set(\"aeiou\")\n"
            "    var found = 0\n"
            "    for character in text {\n"
            "        if letters.contains(character) {\n"
            "            found += 1\n"
            "        }\n"
            "    }\n"
            "    return found\n"
            "}\n\n"
            "print(vowels(text))\n")


def _reverse_words(text: str) -> str:
    return ("let text = " + repr(text).replace("'", '"') + "\n\n"
            "func reverseWords(_ text: String) -> String {\n"
            "    let words = text.split(separator: \" \").map { String($0) }\n"
            "    return words.reversed().joined(separator: \" \")\n"
            "}\n\n"
            "print(reverseWords(text))\n")


def _bubble(values: tuple[int, ...]) -> str:
    return ("let values = " + repr(list(values)) + "\n\n"
            "func bubble(_ values: [Int]) -> [Int] {\n"
            "    var items = values\n"
            "    let count = items.count\n"
            "    for i in 0..<count {\n"
            "        for j in 0..<(count - 1 - i) {\n"
            "            if items[j] > items[j + 1] {\n"
            "                items.swapAt(j, j + 1)\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    return items\n"
            "}\n\n"
            "print(bubble(values).map { String($0) }.joined(separator: \",\"))\n")


def _stats(values: tuple[int, ...]) -> str:
    return ("let values = " + repr(list(values)) + "\n\n"
            "func stats(_ values: [Int]) -> (Int, Int, Double) {\n"
            "    let low = values.min() ?? 0\n"
            "    let high = values.max() ?? 0\n"
            "    let total = values.reduce(0, +)\n"
            "    return (low, high, Double(total) / Double(values.count))\n"
            "}\n\n"
            "let (low, high, mean) = stats(values)\n"
            "print(low, high, mean)\n")


def _table(n: int) -> str:
    return ("func table(_ n: Int) {\n"
            "    for i in 1...5 {\n"
            "        print(n, \"x\", i, \"=\", n * i)\n"
            "    }\n"
            "}\n\n"
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
