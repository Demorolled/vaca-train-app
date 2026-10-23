"""Go base builds — ten templates, ten parameter variants each.

Same contract as `python.py`: one small program per entry, deterministic output,
standard library only, no stdin / files / clock / randomness. Templates are raw
strings so the `\\n` inside a `Printf` format reaches Go as an escape, and the
parameters are substituted rather than formatted, which keeps every `%` and
brace in the generated code untouched.
"""
from __future__ import annotations

LANGUAGE = "go"

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

SUM = r"""package main

import "fmt"

func total(n int) int {
	sum := 0
	for i := 1; i <= n; i++ {
		sum += i
	}
	return sum
}

func main() {
	fmt.Println(total(__N__))
}
"""

FACTORIAL = r"""package main

import "fmt"

func factorial(n int64) int64 {
	result := int64(1)
	for i := int64(2); i <= n; i++ {
		result *= i
	}
	return result
}

func main() {
	fmt.Println(factorial(__N__))
}
"""

FIBONACCI = r"""package main

import "fmt"

func fib(n int) []int64 {
	out := make([]int64, 0, n)
	a, b := int64(0), int64(1)
	for i := 0; i < n; i++ {
		out = append(out, a)
		a, b = b, a+b
	}
	return out
}

func main() {
	for i, value := range fib(__N__) {
		if i > 0 {
			fmt.Print(" ")
		}
		fmt.Print(value)
	}
	fmt.Println()
}
"""

PRIMES = r"""package main

import "fmt"

func isPrime(n int) bool {
	if n < 2 {
		return false
	}
	for p := 2; p*p <= n; p++ {
		if n%p == 0 {
			return false
		}
	}
	return true
}

func main() {
	printed := 0
	for value := 2; value <= __N__; value++ {
		if isPrime(value) {
			if printed > 0 {
				fmt.Print(",")
			}
			fmt.Print(value)
			printed++
		}
	}
	fmt.Println()
}
"""

GCD = r"""package main

import "fmt"

func gcd(a, b int) int {
	for b != 0 {
		a, b = b, a%b
	}
	return a
}

func main() {
	fmt.Println(gcd(__A__, __B__))
}
"""

VOWELS = r"""package main

import (
	"fmt"
	"strings"
)

func countVowels(text string) int {
	count := 0
	for _, ch := range strings.ToLower(text) {
		switch ch {
		case 'a', 'e', 'i', 'o', 'u':
			count++
		}
	}
	return count
}

func main() {
	fmt.Println(countVowels("__TEXT__"))
}
"""

REVERSE = r"""package main

import (
	"fmt"
	"strings"
)

func main() {
	words := strings.Fields("__TEXT__")
	for i := len(words) - 1; i >= 0; i-- {
		fmt.Print(words[i])
		if i > 0 {
			fmt.Print(" ")
		}
	}
	fmt.Println()
}
"""

SORT = r"""package main

import "fmt"

func bubble(values []int) []int {
	items := make([]int, len(values))
	copy(items, values)
	for i := 0; i < len(items); i++ {
		for j := 0; j < len(items)-1-i; j++ {
			if items[j] > items[j+1] {
				items[j], items[j+1] = items[j+1], items[j]
			}
		}
	}
	return items
}

func main() {
	fmt.Println(bubble([]int{__VALUES__}))
}
"""

STATS = r"""package main

import "fmt"

func main() {
	values := []int{__VALUES__}
	low, high, sum := values[0], values[0], 0
	for _, value := range values {
		if value < low {
			low = value
		}
		if value > high {
			high = value
		}
		sum += value
	}
	mean := float64(sum) / float64(len(values))
	fmt.Printf("%d %d %.2f\n", low, high, mean)
}
"""

TABLE = r"""package main

import "fmt"

func main() {
	n := __N__
	for i := 1; i <= 5; i++ {
		fmt.Printf("%d x %d = %d\n", n, i, n*i)
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
