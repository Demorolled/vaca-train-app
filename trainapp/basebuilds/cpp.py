"""C++ base builds — ten templates, ten parameter variants each.

Same pattern as `python.py`: small strings, one deterministic printed result,
standard library only. Every program is a complete translation unit with its own
`main`, so the real compiler can prove it without any harness glue.
"""
from __future__ import annotations

LANGUAGE = "cpp"

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


CPP_SUM = """#include <iostream>

int total(int n) {
    int sum = 0;
    for (int i = 1; i <= n; ++i) {
        sum += i;
    }
    return sum;
}

int main() {
    std::cout << total(@N@) << "\\n";
    return 0;
}
"""

CPP_FACTORIAL = """#include <iostream>

long long factorial(int n) {
    long long result = 1;
    for (int i = 2; i <= n; ++i) {
        result *= i;
    }
    return result;
}

int main() {
    std::cout << factorial(@N@) << "\\n";
    return 0;
}
"""

CPP_FIB = """#include <cstddef>
#include <iostream>
#include <vector>

std::vector<long long> fib(int n) {
    std::vector<long long> out;
    long long a = 0;
    long long b = 1;
    for (int i = 0; i < n; ++i) {
        out.push_back(a);
        long long next = a + b;
        a = b;
        b = next;
    }
    return out;
}

int main() {
    std::vector<long long> values = fib(@N@);
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i) {
            std::cout << ' ';
        }
        std::cout << values[i];
    }
    std::cout << "\\n";
    return 0;
}
"""

CPP_PRIMES = """#include <cstddef>
#include <iostream>
#include <vector>

bool is_prime(int value) {
    if (value < 2) {
        return false;
    }
    for (int p = 2; p * p <= value; ++p) {
        if (value % p == 0) {
            return false;
        }
    }
    return true;
}

int main() {
    std::vector<int> found;
    for (int value = 2; value <= @N@; ++value) {
        if (is_prime(value)) {
            found.push_back(value);
        }
    }
    for (std::size_t i = 0; i < found.size(); ++i) {
        if (i) {
            std::cout << ',';
        }
        std::cout << found[i];
    }
    std::cout << "\\n";
    return 0;
}
"""

CPP_GCD = """#include <iostream>

int gcd(int a, int b) {
    while (b != 0) {
        int next = a % b;
        a = b;
        b = next;
    }
    return a;
}

int main() {
    std::cout << gcd(@A@, @B@) << "\\n";
    return 0;
}
"""

CPP_VOWELS = """#include <cctype>
#include <iostream>
#include <string>

int count_vowels(const std::string& text) {
    int count = 0;
    for (char ch : text) {
        char lower = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
        if (lower == 'a' || lower == 'e' || lower == 'i' || lower == 'o' || lower == 'u') {
            ++count;
        }
    }
    return count;
}

int main() {
    std::string text = "@TEXT@";
    std::cout << count_vowels(text) << "\\n";
    return 0;
}
"""

CPP_REVERSE = """#include <algorithm>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

int main() {
    std::string text = "@TEXT@";
    std::istringstream stream(text);
    std::vector<std::string> words;
    std::string word;
    while (stream >> word) {
        words.push_back(word);
    }
    std::reverse(words.begin(), words.end());
    for (std::size_t i = 0; i < words.size(); ++i) {
        if (i) {
            std::cout << ' ';
        }
        std::cout << words[i];
    }
    std::cout << "\\n";
    return 0;
}
"""

CPP_SORT = """#include <cstddef>
#include <iostream>
#include <vector>

std::vector<int> sort_values(std::vector<int> items) {
    for (std::size_t i = 0; i < items.size(); ++i) {
        for (std::size_t j = 0; j + 1 < items.size() - i; ++j) {
            if (items[j] > items[j + 1]) {
                int tmp = items[j];
                items[j] = items[j + 1];
                items[j + 1] = tmp;
            }
        }
    }
    return items;
}

int main() {
    std::vector<int> values{@ARR@};
    std::vector<int> sorted = sort_values(values);
    for (std::size_t i = 0; i < sorted.size(); ++i) {
        if (i) {
            std::cout << ',';
        }
        std::cout << sorted[i];
    }
    std::cout << "\\n";
    return 0;
}
"""

CPP_STATS = """#include <iomanip>
#include <iostream>
#include <vector>

int main() {
    std::vector<int> values{@ARR@};
    int low = values[0];
    int high = values[0];
    double total = 0.0;
    for (int value : values) {
        if (value < low) {
            low = value;
        }
        if (value > high) {
            high = value;
        }
        total += value;
    }
    std::cout << low << ' ' << high << ' ' << std::fixed << std::setprecision(2)
              << total / static_cast<double>(values.size()) << "\\n";
    return 0;
}
"""

CPP_TABLE = """#include <iostream>

int main() {
    int n = @N@;
    for (int i = 1; i <= 5; ++i) {
        std::cout << n << " x " << i << " = " << n * i << "\\n";
    }
    return 0;
}
"""


def programs() -> list[dict]:
    rows: list[dict] = []
    for n in Numbers:
        rows.append({"title": f"sum to {n}", "template": "sum",
                     "code": _fill(CPP_SUM, n=n)})
        rows.append({"title": f"first {n} fibonacci", "template": "fibonacci",
                     "code": _fill(CPP_FIB, n=n)})
        rows.append({"title": f"primes up to {n}", "template": "primes",
                     "code": _fill(CPP_PRIMES, n=n)})
        rows.append({"title": f"{n} times table", "template": "table",
                     "code": _fill(CPP_TABLE, n=n)})
    for n in Factorials:
        rows.append({"title": f"factorial {n}", "template": "factorial",
                     "code": _fill(CPP_FACTORIAL, n=n)})
    for a, b in Pairs:
        rows.append({"title": f"gcd {a} {b}", "template": "gcd",
                     "code": _fill(CPP_GCD, a=a, b=b)})
    for text in Words:
        rows.append({"title": f"count vowels in '{text}'", "template": "vowels",
                     "code": _fill(CPP_VOWELS, text=text)})
        rows.append({"title": f"reverse words in '{text}'", "template": "reverse",
                     "code": _fill(CPP_REVERSE, text=text)})
    for values in Arrays:
        joined = ", ".join(str(v) for v in values)
        rows.append({"title": f"sort {list(values)}", "template": "sort",
                     "code": _fill(CPP_SORT, arr=joined)})
        rows.append({"title": f"stats of {list(values)}", "template": "stats",
                     "code": _fill(CPP_STATS, arr=joined)})
    return rows
