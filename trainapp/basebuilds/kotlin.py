"""Kotlin base builds — ten templates, ten parameter variants each.

Same contract as the Python module: one deterministic result per program, no
imports, no stdin, no clock, no network, no filesystem. `minOrNull()`/`maxOrNull`
are avoided because their availability depends on the compiler version; the
aggregates are computed with a plain loop instead.
"""
from __future__ import annotations

LANGUAGE = "kotlin"

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
    return ("fun total(n: Int): Int {\n"
            "    var sum = 0\n"
            "    for (value in 1..n) {\n"
            "        sum += value\n"
            "    }\n"
            "    return sum\n"
            "}\n\n"
            "fun main() {\n"
            "    println(total(" + str(n) + "))\n"
            "}\n")


def _factorial(n: int) -> str:
    return ("fun factorial(n: Int): Long {\n"
            "    var result = 1L\n"
            "    for (value in 2..n) {\n"
            "        result *= value\n"
            "    }\n"
            "    return result\n"
            "}\n\n"
            "fun main() {\n"
            "    println(factorial(" + str(n) + "))\n"
            "}\n")


def _fibonacci(n: int) -> str:
    return ("fun fib(n: Int): List<Int> {\n"
            "    var a = 0\n"
            "    var b = 1\n"
            "    val out = mutableListOf<Int>()\n"
            "    for (i in 1..n) {\n"
            "        out.add(a)\n"
            "        val next = a + b\n"
            "        a = b\n"
            "        b = next\n"
            "    }\n"
            "    return out\n"
            "}\n\n"
            "fun main() {\n"
            "    println(fib(" + str(n) + ").joinToString(\" \"))\n"
            "}\n")


def _primes(n: int) -> str:
    return ("fun isPrime(value: Int): Boolean {\n"
            "    if (value < 2) {\n"
            "        return false\n"
            "    }\n"
            "    var factor = 2\n"
            "    while (factor * factor <= value) {\n"
            "        if (value % factor == 0) {\n"
            "            return false\n"
            "        }\n"
            "        factor += 1\n"
            "    }\n"
            "    return true\n"
            "}\n\n"
            "fun main() {\n"
            "    val found = (2.." + str(n) + ").filter { isPrime(it) }\n"
            "    println(found.joinToString(\",\"))\n"
            "}\n")


def _gcd(a: int, b: int) -> str:
    return ("fun gcd(a: Int, b: Int): Int {\n"
            "    var x = a\n"
            "    var y = b\n"
            "    while (y != 0) {\n"
            "        val remainder = x % y\n"
            "        x = y\n"
            "        y = remainder\n"
            "    }\n"
            "    return x\n"
            "}\n\n"
            "fun main() {\n"
            "    println(gcd(" + str(a) + ", " + str(b) + "))\n"
            "}\n")


def _vowels(text: str) -> str:
    return ("const val TEXT = \"" + text + "\"\n\n"
            "fun vowels(text: String): Int {\n"
            "    var found = 0\n"
            "    for (character in text) {\n"
            "        if (\"aeiou\".indexOf(character) >= 0) {\n"
            "            found += 1\n"
            "        }\n"
            "    }\n"
            "    return found\n"
            "}\n\n"
            "fun main() {\n"
            "    println(vowels(TEXT))\n"
            "}\n")


def _reverse_words(text: str) -> str:
    return ("const val TEXT = \"" + text + "\"\n\n"
            "fun main() {\n"
            "    val words = TEXT.split(\" \").reversed()\n"
            "    println(words.joinToString(\" \"))\n"
            "}\n")


def _bubble(values: tuple[int, ...]) -> str:
    return ("val VALUES = listOf(" + ", ".join(str(v) for v in values) + ")\n\n"
            "fun bubble(values: List<Int>): List<Int> {\n"
            "    val items = values.toMutableList()\n"
            "    for (i in items.indices) {\n"
            "        for (j in 0 until items.size - 1 - i) {\n"
            "            if (items[j] > items[j + 1]) {\n"
            "                val swap = items[j]\n"
            "                items[j] = items[j + 1]\n"
            "                items[j + 1] = swap\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    return items\n"
            "}\n\n"
            "fun main() {\n"
            "    println(bubble(VALUES).joinToString(\",\"))\n"
            "}\n")


def _stats(values: tuple[int, ...]) -> str:
    return ("val VALUES = listOf(" + ", ".join(str(v) for v in values) + ")\n\n"
            "fun main() {\n"
            "    var low = VALUES[0]\n"
            "    var high = VALUES[0]\n"
            "    var total = 0\n"
            "    for (value in VALUES) {\n"
            "        if (value < low) {\n"
            "            low = value\n"
            "        }\n"
            "        if (value > high) {\n"
            "            high = value\n"
            "        }\n"
            "        total += value\n"
            "    }\n"
            "    val mean = total.toDouble() / VALUES.size\n"
            "    println(\"$low $high $mean\")\n"
            "}\n")


def _table(n: int) -> str:
    return ("fun table(n: Int) {\n"
            "    for (i in 1..5) {\n"
            "        println(\"$n x $i = ${n * i}\")\n"
            "    }\n"
            "}\n\n"
            "fun main() {\n"
            "    table(" + str(n) + ")\n"
            "}\n")


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
