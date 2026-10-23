"""Java base builds — ten templates, ten parameter variants each.

Each program is one `public class` with a `main`, named after the template, which
is what the launcher needs (`java Foo` only resolves a class whose file is
`Foo.java`). Standard library only, no imports beyond `java.lang`.
"""
from __future__ import annotations

LANGUAGE = "java"

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


JAVA_SUM = """public class SumToN {
    static int total(int n) {
        int sum = 0;
        for (int i = 1; i <= n; i++) {
            sum += i;
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println(total(@N@));
    }
}
"""

JAVA_FACTORIAL = """public class Factorial {
    static long factorial(int n) {
        long result = 1;
        for (int i = 2; i <= n; i++) {
            result *= i;
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(factorial(@N@));
    }
}
"""

JAVA_FIB = """public class Fibonacci {
    static long[] fib(int n) {
        long[] out = new long[n];
        long a = 0;
        long b = 1;
        for (int i = 0; i < n; i++) {
            out[i] = a;
            long next = a + b;
            a = b;
            b = next;
        }
        return out;
    }

    public static void main(String[] args) {
        long[] values = fib(@N@);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < values.length; i++) {
            if (i > 0) {
                sb.append(' ');
            }
            sb.append(values[i]);
        }
        System.out.println(sb.toString());
    }
}
"""

JAVA_PRIMES = """public class Primes {
    static boolean isPrime(int value) {
        if (value < 2) {
            return false;
        }
        for (int p = 2; p * p <= value; p++) {
            if (value % p == 0) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder();
        boolean first = true;
        for (int value = 2; value <= @N@; value++) {
            if (isPrime(value)) {
                if (!first) {
                    sb.append(',');
                }
                sb.append(value);
                first = false;
            }
        }
        System.out.println(sb.toString());
    }
}
"""

JAVA_GCD = """public class Gcd {
    static int gcd(int a, int b) {
        while (b != 0) {
            int next = a % b;
            a = b;
            b = next;
        }
        return a;
    }

    public static void main(String[] args) {
        System.out.println(gcd(@A@, @B@));
    }
}
"""

JAVA_VOWELS = """public class Vowels {
    static int countVowels(String text) {
        int count = 0;
        String lower = text.toLowerCase();
        for (int i = 0; i < lower.length(); i++) {
            char ch = lower.charAt(i);
            if (ch == 'a' || ch == 'e' || ch == 'i' || ch == 'o' || ch == 'u') {
                count++;
            }
        }
        return count;
    }

    public static void main(String[] args) {
        System.out.println(countVowels("@TEXT@"));
    }
}
"""

JAVA_REVERSE = """public class ReverseWords {
    public static void main(String[] args) {
        String text = "@TEXT@";
        String[] words = text.split(" ");
        StringBuilder sb = new StringBuilder();
        for (int i = words.length - 1; i >= 0; i--) {
            if (sb.length() > 0) {
                sb.append(' ');
            }
            sb.append(words[i]);
        }
        System.out.println(sb.toString());
    }
}
"""

JAVA_SORT = """public class BubbleSort {
    static int[] sort(int[] items) {
        int[] values = items.clone();
        for (int i = 0; i < values.length; i++) {
            for (int j = 0; j + 1 < values.length - i; j++) {
                if (values[j] > values[j + 1]) {
                    int tmp = values[j];
                    values[j] = values[j + 1];
                    values[j + 1] = tmp;
                }
            }
        }
        return values;
    }

    public static void main(String[] args) {
        int[] values = {@ARR@};
        int[] sorted = sort(values);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < sorted.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append(sorted[i]);
        }
        System.out.println(sb.toString());
    }
}
"""

JAVA_STATS = """public class Stats {
    public static void main(String[] args) {
        int[] values = {@ARR@};
        int low = values[0];
        int high = values[0];
        double total = 0;
        for (int value : values) {
            if (value < low) {
                low = value;
            }
            if (value > high) {
                high = value;
            }
            total += value;
        }
        System.out.printf("%d %d %.2f%n", low, high, total / values.length);
    }
}
"""

JAVA_TABLE = """public class Table {
    public static void main(String[] args) {
        int n = @N@;
        for (int i = 1; i <= 5; i++) {
            System.out.println(n + " x " + i + " = " + (n * i));
        }
    }
}
"""


def programs() -> list[dict]:
    rows: list[dict] = []
    for n in Numbers:
        rows.append({"title": f"sum to {n}", "template": "sum",
                     "code": _fill(JAVA_SUM, n=n)})
        rows.append({"title": f"first {n} fibonacci", "template": "fibonacci",
                     "code": _fill(JAVA_FIB, n=n)})
        rows.append({"title": f"primes up to {n}", "template": "primes",
                     "code": _fill(JAVA_PRIMES, n=n)})
        rows.append({"title": f"{n} times table", "template": "table",
                     "code": _fill(JAVA_TABLE, n=n)})
    for n in Factorials:
        rows.append({"title": f"factorial {n}", "template": "factorial",
                     "code": _fill(JAVA_FACTORIAL, n=n)})
    for a, b in Pairs:
        rows.append({"title": f"gcd {a} {b}", "template": "gcd",
                     "code": _fill(JAVA_GCD, a=a, b=b)})
    for text in Words:
        rows.append({"title": f"count vowels in '{text}'", "template": "vowels",
                     "code": _fill(JAVA_VOWELS, text=text)})
        rows.append({"title": f"reverse words in '{text}'", "template": "reverse",
                     "code": _fill(JAVA_REVERSE, text=text)})
    for values in Arrays:
        joined = ", ".join(str(v) for v in values)
        rows.append({"title": f"sort {list(values)}", "template": "sort",
                     "code": _fill(JAVA_SORT, arr=joined)})
        rows.append({"title": f"stats of {list(values)}", "template": "stats",
                     "code": _fill(JAVA_STATS, arr=joined)})
    return rows
