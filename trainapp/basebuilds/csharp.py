"""C# base builds — ten templates, ten parameter variants each.

Top-level statements rather than a `Program` class: the runner accepts both, and
this keeps every file to the code that matters. `using` directives stay first,
which is the only ordering top-level statements require.
"""
from __future__ import annotations

LANGUAGE = "csharp"

Numbers = (5, 7, 9, 10, 12, 15, 16, 20, 25, 30)
Pairs = ((12, 18), (14, 21), (22, 33), (17, 5), (81, 27), (45, 60),
         (13, 39), (64, 48), (100, 35), (121, 11))
Words = ("the quick brown fox", "one two three", "hello brave new world",
         "go build something", "a b c d e", "ship it today",
         "read the fine manual", "small steps daily", "test then commit",
         "keep it simple")
Arrays = ((5, 3, 9, 1, 7), (10, 2, 33, 4), (8, 8, 2, 6), (1, 2, 3),
          (9, 5, 5, 1, 0), (42, 7, 13), (3, 1, 4, 1, 5), (2, 6, 4),
          (11, 22, 33, 44), (7, 0, 9, 2))
# Factorial has its own argument list: `20!` fits a 64-bit integer, `30!` does
# not. Ten distinct arguments keep every program unique without an overflow.
Factorials = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11)

Tables = (3, 4, 5, 6, 7, 8, 9, 11, 12, 13)


def _fill(template: str, **values: str) -> str:
    text = template
    for key, value in values.items():
        text = text.replace(f"@{key.upper()}@", str(value))
    return text


CS_SUM = """using System;

int total(int n)
{
    int sum = 0;
    for (int i = 1; i <= n; i++)
    {
        sum += i;
    }
    return sum;
}

Console.WriteLine(total(@N@));
"""

CS_FACTORIAL = """using System;

long factorial(int n)
{
    long result = 1;
    for (int i = 2; i <= n; i++)
    {
        result *= i;
    }
    return result;
}

Console.WriteLine(factorial(@N@));
"""

CS_FIB = """using System;
using System.Collections.Generic;

List<long> fib(int n)
{
    var values = new List<long>();
    long a = 0;
    long b = 1;
    for (int i = 0; i < n; i++)
    {
        values.Add(a);
        long next = a + b;
        a = b;
        b = next;
    }
    return values;
}

Console.WriteLine(string.Join(" ", fib(@N@)));
"""

CS_PRIMES = """using System;
using System.Collections.Generic;

bool isPrime(int value)
{
    if (value < 2)
    {
        return false;
    }
    for (int p = 2; p * p <= value; p++)
    {
        if (value % p == 0)
        {
            return false;
        }
    }
    return true;
}

var found = new List<int>();
for (int value = 2; value <= @N@; value++)
{
    if (isPrime(value))
    {
        found.Add(value);
    }
}
Console.WriteLine(string.Join(",", found));
"""

CS_GCD = """using System;

int gcd(int a, int b)
{
    while (b != 0)
    {
        int next = a % b;
        a = b;
        b = next;
    }
    return a;
}

Console.WriteLine(gcd(@A@, @B@));
"""

CS_VOWELS = """using System;

int countVowels(string text)
{
    int count = 0;
    foreach (char ch in text.ToLower())
    {
        if ("aeiou".IndexOf(ch) >= 0)
        {
            count++;
        }
    }
    return count;
}

Console.WriteLine(countVowels("@TEXT@"));
"""

CS_REVERSE = """using System;

string text = "@TEXT@";
string[] words = text.Split(' ');
Array.Reverse(words);
Console.WriteLine(string.Join(" ", words));
"""

CS_SORT = """using System;

int[] sortValues(int[] items)
{
    int[] values = (int[])items.Clone();
    for (int i = 0; i < values.Length; i++)
    {
        for (int j = 0; j + 1 < values.Length - i; j++)
        {
            if (values[j] > values[j + 1])
            {
                int tmp = values[j];
                values[j] = values[j + 1];
                values[j + 1] = tmp;
            }
        }
    }
    return values;
}

int[] sorted = sortValues(new[] { @ARR@ });
Console.WriteLine(string.Join(",", sorted));
"""

CS_STATS = """using System;
using System.Linq;

int[] values = { @ARR@ };
Console.WriteLine($"{values.Min()} {values.Max()} {values.Average():F2}");
"""

CS_TABLE = """using System;

int n = @N@;
for (int i = 1; i <= 5; i++)
{
    Console.WriteLine($"{n} x {i} = {n * i}");
}
"""


def programs() -> list[dict]:
    rows: list[dict] = []
    for n in Numbers:
        rows.append({"title": f"sum to {n}", "template": "sum",
                     "code": _fill(CS_SUM, n=n)})
        rows.append({"title": f"first {n} fibonacci", "template": "fibonacci",
                     "code": _fill(CS_FIB, n=n)})
        rows.append({"title": f"primes up to {n}", "template": "primes",
                     "code": _fill(CS_PRIMES, n=n)})
        rows.append({"title": f"{n} times table", "template": "table",
                     "code": _fill(CS_TABLE, n=n)})
    for n in Factorials:
        rows.append({"title": f"factorial {n}", "template": "factorial",
                     "code": _fill(CS_FACTORIAL, n=n)})
    for a, b in Pairs:
        rows.append({"title": f"gcd {a} {b}", "template": "gcd",
                     "code": _fill(CS_GCD, a=a, b=b)})
    for text in Words:
        rows.append({"title": f"count vowels in '{text}'", "template": "vowels",
                     "code": _fill(CS_VOWELS, text=text)})
        rows.append({"title": f"reverse words in '{text}'", "template": "reverse",
                     "code": _fill(CS_REVERSE, text=text)})
    for values in Arrays:
        joined = ", ".join(str(v) for v in values)
        rows.append({"title": f"sort {list(values)}", "template": "sort",
                     "code": _fill(CS_SORT, arr=joined)})
        rows.append({"title": f"stats of {list(values)}", "template": "stats",
                     "code": _fill(CS_STATS, arr=joined)})
    return rows
