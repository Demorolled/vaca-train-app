"""Rust base builds — ten templates, ten parameter variants each.

Kept deliberately borrow-checker-free: owned `Vec`s, `&[T]` slices accepted by
value copies, `iter().sum()` and `saturating_sub` instead of index arithmetic
that could panic. Nothing here needs a crate, so `rustc file.rs` is the whole
gate.
"""
from __future__ import annotations

LANGUAGE = "rust"

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

SUM = r"""fn total(n: u64) -> u64 {
    (1..=n).sum()
}

fn main() {
    println!("{}", total(__N__));
}
"""

FACTORIAL = r"""fn factorial(n: u64) -> u64 {
    let mut result = 1;
    for i in 2..=n {
        result *= i;
    }
    result
}

fn main() {
    println!("{}", factorial(__N__));
}
"""

FIBONACCI = r"""fn fib(n: usize) -> Vec<u64> {
    let mut out = Vec::new();
    let (mut a, mut b) = (0, 1);
    for _ in 0..n {
        out.push(a);
        let next = a + b;
        a = b;
        b = next;
    }
    out
}

fn main() {
    let values = fib(__N__);
    let text: Vec<String> = values.iter().map(|v| v.to_string()).collect();
    println!("{}", text.join(" "));
}
"""

PRIMES = r"""fn is_prime(n: u64) -> bool {
    if n < 2 {
        return false;
    }
    for p in 2..=((n as f64).sqrt() as u64) {
        if n % p == 0 {
            return false;
        }
    }
    true
}

fn main() {
    let limit = __N__;
    let primes: Vec<String> = (2..=limit)
        .filter(|v| is_prime(*v))
        .map(|v| v.to_string())
        .collect();
    println!("{}", primes.join(","));
}
"""

GCD = r"""fn gcd(a: u64, b: u64) -> u64 {
    let (mut a, mut b) = (a, b);
    while b != 0 {
        let remainder = a % b;
        a = b;
        b = remainder;
    }
    a
}

fn main() {
    println!("{}", gcd(__A__, __B__));
}
"""

VOWELS = r"""fn count_vowels(text: &str) -> usize {
    text.chars()
        .filter(|ch| "aeiou".contains(ch.to_ascii_lowercase()))
        .count()
}

fn main() {
    println!("{}", count_vowels("__TEXT__"));
}
"""

REVERSE = r"""fn main() {
    let text = "__TEXT__";
    let words: Vec<&str> = text.split_whitespace().rev().collect();
    println!("{}", words.join(" "));
}
"""

SORT = r"""fn bubble(values: &[i64]) -> Vec<i64> {
    let mut items = values.to_vec();
    for i in 0..items.len() {
        for j in 0..items.len().saturating_sub(1 + i) {
            if items[j] > items[j + 1] {
                items.swap(j, j + 1);
            }
        }
    }
    items
}

fn main() {
    let values = [__VALUES__];
    let sorted = bubble(&values);
    let text: Vec<String> = sorted.iter().map(|v| v.to_string()).collect();
    println!("{}", text.join(","));
}
"""

STATS = r"""fn main() {
    let values = [__VALUES__];
    let low = *values.iter().min().unwrap();
    let high = *values.iter().max().unwrap();
    let sum: i64 = values.iter().sum();
    let mean = sum as f64 / values.len() as f64;
    println!("{} {} {:.2}", low, high, mean);
}
"""

TABLE = r"""fn main() {
    let n = __N__;
    for i in 1..=5 {
        println!("{} x {} = {}", n, i, n * i);
    }
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
