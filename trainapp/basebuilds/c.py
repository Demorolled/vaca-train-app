"""C base builds — ten templates, ten parameter variants each.

Raw strings matter here: a C `printf("%d\\n", ...)` has to reach the compiler with
a literal backslash-n, so the templates are written raw and the parameters are
substituted, never formatted. Everything is `main` + one helper, `printf` only,
and the format specifier is matched to the argument type at every call.
"""
from __future__ import annotations

LANGUAGE = "c"

Numbers = (5, 7, 9, 10, 12, 15, 16, 20, 25, 30)
Factorials = (5, 7, 8, 9, 10, 11, 12, 13, 15, 18)
Pairs = ((12, 18), (14, 21), (22, 33), (17, 5), (81, 27), (45, 60),
         (13, 39), (64, 48), (100, 35), (121, 11))
Words = ("the quick brown fox", "one two three", "hello brave new world",
         "go build something", "a b c d e", "ship it today",
         "read the fine manual", "small steps daily", "test then commit",
         "keep it simple")
Arrays = ((5, 3, 9, 1, 7), (10, 2, 33, 4), (8, 8, 2, 6), (1, 2, 3),
          (9, 5, 5, 1, 0), (42, 7, 13), (3, 1, 4, 1, 5), (2, 6, 4),
          (11, 22, 33, 44), (7, 0, 9, 2))
Tables = (3, 4, 5, 6, 7, 8, 9, 11, 12, 13)

SUM = r"""#include <stdio.h>

int total(int n) {
    int sum = 0;
    for (int i = 1; i <= n; i++) {
        sum += i;
    }
    return sum;
}

int main(void) {
    printf("%d\n", total(__N__));
    return 0;
}
"""

FACTORIAL = r"""#include <stdio.h>

long long factorial(int n) {
    long long result = 1;
    for (int i = 2; i <= n; i++) {
        result *= i;
    }
    return result;
}

int main(void) {
    printf("%lld\n", factorial(__N__));
    return 0;
}
"""

FIBONACCI = r"""#include <stdio.h>

int main(void) {
    int n = __N__;
    long long a = 0;
    long long b = 1;
    for (int i = 0; i < n; i++) {
        if (i > 0) {
            printf(" ");
        }
        printf("%lld", a);
        long long next = a + b;
        a = b;
        b = next;
    }
    printf("\n");
    return 0;
}
"""

PRIMES = r"""#include <stdio.h>

int is_prime(int n) {
    if (n < 2) {
        return 0;
    }
    for (int p = 2; p * p <= n; p++) {
        if (n % p == 0) {
            return 0;
        }
    }
    return 1;
}

int main(void) {
    int printed = 0;
    for (int value = 2; value <= __N__; value++) {
        if (is_prime(value)) {
            printf(printed ? ",%d" : "%d", value);
            printed++;
        }
    }
    printf("\n");
    return 0;
}
"""

GCD = r"""#include <stdio.h>

int gcd(int a, int b) {
    while (b != 0) {
        int remainder = a % b;
        a = b;
        b = remainder;
    }
    return a;
}

int main(void) {
    printf("%d\n", gcd(__A__, __B__));
    return 0;
}
"""

VOWELS = r"""#include <stdio.h>

int is_vowel(char ch) {
    return ch == 'a' || ch == 'e' || ch == 'i' || ch == 'o' || ch == 'u';
}

int main(void) {
    const char *text = "__TEXT__";
    int count = 0;
    for (int i = 0; text[i] != '\0'; i++) {
        char ch = text[i];
        if (ch >= 'A' && ch <= 'Z') {
            ch = (char)(ch - 'A' + 'a');
        }
        if (is_vowel(ch)) {
            count++;
        }
    }
    printf("%d\n", count);
    return 0;
}
"""

REVERSE = r"""#include <stdio.h>
#include <string.h>

int main(void) {
    char text[] = "__TEXT__";
    char *words[16];
    int count = 0;
    char *token = strtok(text, " ");
    while (token != NULL && count < 16) {
        words[count] = token;
        count++;
        token = strtok(NULL, " ");
    }
    for (int i = count - 1; i >= 0; i--) {
        printf("%s", words[i]);
        printf(i > 0 ? " " : "\n");
    }
    return 0;
}
"""

SORT = r"""#include <stdio.h>

int main(void) {
    int values[] = {__VALUES__};
    int length = (int)(sizeof(values) / sizeof(values[0]));
    for (int i = 0; i < length; i++) {
        for (int j = 0; j < length - 1 - i; j++) {
            if (values[j] > values[j + 1]) {
                int tmp = values[j];
                values[j] = values[j + 1];
                values[j + 1] = tmp;
            }
        }
    }
    for (int i = 0; i < length; i++) {
        printf(i ? ",%d" : "%d", values[i]);
    }
    printf("\n");
    return 0;
}
"""

STATS = r"""#include <stdio.h>

int main(void) {
    int values[] = {__VALUES__};
    int length = (int)(sizeof(values) / sizeof(values[0]));
    int low = values[0];
    int high = values[0];
    int sum = 0;
    for (int i = 0; i < length; i++) {
        if (values[i] < low) {
            low = values[i];
        }
        if (values[i] > high) {
            high = values[i];
        }
        sum += values[i];
    }
    printf("%d %d %.2f\n", low, high, (double)sum / (double)length);
    return 0;
}
"""

TABLE = r"""#include <stdio.h>

int main(void) {
    int n = __N__;
    for (int i = 1; i <= 5; i++) {
        printf("%d x %d = %d\n", n, i, n * i);
    }
    return 0;
}
"""


def _fill(template: str, **values: str) -> str:
    code = template
    for key, value in values.items():
        code = code.replace(f"__{key}__", value)
    return code


def programs() -> list[dict]:
    rows: list[dict] = []
    for n in Numbers:
        rows.append({"title": f"sum to {n}", "template": "sum",
                     "code": _fill(SUM, N=str(n))})
        rows.append({"title": f"first {n} fibonacci", "template": "fibonacci",
                     "code": _fill(FIBONACCI, N=str(n))})
        rows.append({"title": f"primes up to {n}", "template": "primes",
                     "code": _fill(PRIMES, N=str(n))})
        rows.append({"title": f"{n} times table", "template": "table",
                     "code": _fill(TABLE, N=str(n))})
    for n in Factorials:
        rows.append({"title": f"factorial {n}", "template": "factorial",
                     "code": _fill(FACTORIAL, N=str(n))})
    for a, b in Pairs:
        rows.append({"title": f"gcd {a} {b}", "template": "gcd",
                     "code": _fill(GCD, A=str(a), B=str(b))})
    for text in Words:
        rows.append({"title": f"count vowels in '{text}'", "template": "vowels",
                     "code": _fill(VOWELS, TEXT=text)})
        rows.append({"title": f"reverse words in '{text}'", "template": "reverse",
                     "code": _fill(REVERSE, TEXT=text)})
    for values in Arrays:
        literal = ", ".join(str(v) for v in values)
        rows.append({"title": f"sort {list(values)}", "template": "sort",
                     "code": _fill(SORT, VALUES=literal)})
        rows.append({"title": f"stats of {list(values)}", "template": "stats",
                     "code": _fill(STATS, VALUES=literal)})
    return rows
