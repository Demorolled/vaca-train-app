"""Go medium builds — ten templates with real functions and data structures.

Every program is a standalone `package main`: a map, slice or struct carries
state between at least three functions, and the report on stdout is deterministic.
Templates are raw strings with `@PLACEHOLDERS@`, so Go's own `%` verbs and braces
reach the output untouched.
"""
from __future__ import annotations

LANGUAGE = "go"

TEXTS = (
    "the quick brown fox jumps over the lazy dog the fox",
    "a small step for man a giant leap for mankind",
    "one two two three three three four four four four",
    "red green blue red green red",
    "build test ship build test build",
    "alpha beta gamma alpha beta alpha",
    "data data model model model view view view view",
    "cat dog cat bird cat dog",
    "read read write write write refactor",
    "north south east west north south north",
)

RECORDS = (
    (("bolt", 12, "0.50"), ("nut", 40, "0.10"), ("washer", 0, "0.05")),
    (("hammer", 3, "12.00"), ("saw", 0, "18.50"), ("drill", 2, "45.00")),
    (("pen", 100, "1.20"), ("ink", 4, "6.00"), ("pad", 25, "2.50")),
    (("cpu", 2, "199.00"), ("ram", 4, "79.00"), ("ssd", 0, "120.00")),
    (("apple", 30, "0.40"), ("pear", 0, "0.50"), ("plum", 11, "0.80")),
    (("cup", 6, "3.00"), ("plate", 6, "4.00"), ("fork", 0, "2.00")),
    (("rope", 2, "15.00"), ("hook", 9, "4.50"), ("glove", 1, "22.00")),
    (("map", 1, "8.00"), ("compass", 0, "30.00"), ("whistle", 5, "3.50")),
    (("tile", 200, "1.00"), ("grout", 3, "9.00"), ("seal", 0, "7.00")),
    (("lamp", 4, "25.00"), ("bulb", 0, "4.00"), ("cable", 12, "3.00")),
)

MATRICES = (
    ((1, 2, 3), (4, 5, 6), (7, 8, 9)),
    ((2, 0, 1), (0, 3, 0), (1, 0, 2)),
    ((5, 1, 9), (2, 6, 3), (8, 4, 7)),
    ((1, 1, 1), (2, 2, 2), (3, 3, 3)),
    ((0, 2, 4), (6, 8, 10), (12, 14, 16)),
    ((9, 8, 7), (6, 5, 4), (3, 2, 1)),
    ((4, 4, 0), (0, 4, 4), (4, 0, 4)),
    ((11, 12, 13), (21, 22, 23), (31, 32, 33)),
    ((3, 0, 0), (0, 3, 0), (0, 0, 3)),
    ((7, 5, 3), (1, 9, 2), (4, 6, 8)),
)

CSVS = (
    "name,qty,price\nbolt,12,1\nnut,40,2\nwasher,0,3",
    "item,units,cost\nhammer,3,36\nsaw,0,18\ndrill,2,90",
    "city,pop,area\naustin,964,704\nboston,695,232\ndenver,715,401",
    "lang,year,stars\npython,1991,9\nrust,2010,7\ngo,2009,8",
    "day,high,low\nmon,21,9\ntue,19,8\nwed,23,12",
    "sku,stock,reorder\na1,4,10\nb2,0,5\nc3,18,10",
    "team,wins,losses\nred,7,3\nblue,5,5\ngreen,9,1",
    "route,km,minutes\nalpha,12,18\nbeta,7,9\ngamma,25,31",
    "book,parts,pages\none,3,120\ntwo,1,40\nthree,5,260",
    "part,width,height\nframe,80,120\npanel,40,60\ndoor,90,200",
)

NUMBERS = (12, 18, 28, 30, 36, 45, 60, 84, 97, 120)
LISTS = ((3, 1, 4), (7, 2, 9, 5), (1, 2, 3, 4, 5), (9,), (4, 4, 6),
         (8, 3, 1, 7), (2, 6, 5, 3, 8), (11, 4), (5, 9, 2, 6, 1),
         (10, 20, 30, 40))
LEDGERS = (
    (("open", 100), ("deposit", 50), ("withdraw", 30), ("withdraw", 500)),
    (("open", 20), ("withdraw", 5), ("withdraw", 15), ("deposit", 7)),
    (("open", 0), ("deposit", 12), ("withdraw", 12), ("withdraw", 1)),
    (("open", 250), ("withdraw", 249), ("deposit", 3), ("withdraw", 4)),
    (("open", 40), ("deposit", 0), ("withdraw", 40), ("deposit", 1)),
    (("open", 75), ("withdraw", 25), ("withdraw", 25), ("withdraw", 25)),
    (("open", 5), ("deposit", 500), ("withdraw", 250), ("withdraw", 255)),
    (("open", 1000), ("withdraw", 999), ("deposit", 1), ("withdraw", 2)),
    (("open", 33), ("deposit", 33), ("withdraw", 66), ("deposit", 34)),
    (("open", 8), ("withdraw", 4), ("deposit", 10), ("withdraw", 14)),
)
STACKS = (
    ("push 3", "push 1", "peek", "pop", "push 4", "pop", "pop"),
    ("push 9", "push 9", "pop", "peek", "pop", "pop", "peek"),
    ("push 2", "pop", "push 7", "push 8", "peek", "pop", "pop"),
    ("push 5", "push 6", "push 7", "pop", "pop", "pop", "pop"),
    ("push 1", "push 2", "pop", "push 3", "push 4", "pop", "peek"),
    ("push 10", "peek", "push 20", "peek", "pop", "peek", "pop"),
    ("push 8", "push 3", "pop", "push 9", "pop", "pop", "peek"),
    ("push 4", "push 4", "push 4", "pop", "pop", "pop", "pop"),
    ("push 0", "pop", "pop", "push 1", "peek", "push 2", "pop"),
    ("push 6", "push 5", "peek", "pop", "push 7", "pop", "pop"),
)


def _word_freq(text: str) -> str:
    return r"""package main

import (
	"fmt"
	"sort"
	"strings"
)

type pair struct {
	word  string
	count int
}

func counts(text string) map[string]int {
	table := map[string]int{}
	for _, word := range strings.Fields(text) {
		table[word]++
	}
	return table
}

func ranked(table map[string]int) []pair {
	rows := make([]pair, 0, len(table))
	for word, count := range table {
		rows = append(rows, pair{word: word, count: count})
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].count != rows[j].count {
			return rows[i].count > rows[j].count
		}
		return rows[i].word < rows[j].word
	})
	return rows
}

func main() {
	text := "@TEXT@"
	rows := ranked(counts(text))
	limit := 4
	if len(rows) < limit {
		limit = len(rows)
	}
	for _, row := range rows[:limit] {
		fmt.Printf("%s: %d\n", row.word, row.count)
	}
}
""".replace("@TEXT@", text)


def _inventory(records: tuple) -> str:
    stock = "\n".join(f'\t\t{{"{name}", {qty}, {price}}},'
                      for name, qty, price in records)
    return r"""package main

import "fmt"

type item struct {
	name  string
	qty   int
	price float64
}

func available(items []item) []item {
	out := []item{}
	for _, entry := range items {
		if entry.qty > 0 {
			out = append(out, entry)
		}
	}
	return out
}

func total(items []item) float64 {
	sum := 0.0
	for _, entry := range items {
		sum += float64(entry.qty) * entry.price
	}
	return sum
}

func main() {
	stock := []item{
@STOCK@
	}
	rows := available(stock)
	for _, entry := range rows {
		fmt.Printf("%-8s %3d x %6.2f = %8.2f\n",
			entry.name, entry.qty, entry.price, float64(entry.qty)*entry.price)
	}
	fmt.Printf("total %.2f\n", total(rows))
}
""".replace("@STOCK@", stock)


def _matrix(matrix: tuple) -> str:
    rows = ",\n\t".join("{" + ", ".join(str(v) for v in row) + "}" for row in matrix)
    return r"""package main

import "fmt"

func transpose(m [3][3]int) [3][3]int {
	var out [3][3]int
	for i := 0; i < 3; i++ {
		for j := 0; j < 3; j++ {
			out[j][i] = m[i][j]
		}
	}
	return out
}

func rowSums(m [3][3]int) [3]int {
	var sums [3]int
	for i := 0; i < 3; i++ {
		for j := 0; j < 3; j++ {
			sums[i] += m[i][j]
		}
	}
	return sums
}

func main() {
	m := [3][3]int{
	@ROWS@,
	}
	for _, row := range transpose(m) {
		fmt.Printf("%3d %3d %3d\n", row[0], row[1], row[2])
	}
	sums := rowSums(m)
	fmt.Printf("sums %d %d %d\n", sums[0], sums[1], sums[2])
}
""".replace("@ROWS@", rows)


def _stack(ops: tuple) -> str:
    lines = "\n".join(f'\t\t"{op}",' for op in ops)
    return r"""package main

import (
	"fmt"
	"strconv"
	"strings"
)

type Stack struct {
	items []int
}

func (s *Stack) Push(value int) {
	s.items = append(s.items, value)
}

func (s *Stack) Pop() (int, bool) {
	if len(s.items) == 0 {
		return 0, false
	}
	value := s.items[len(s.items)-1]
	s.items = s.items[:len(s.items)-1]
	return value, true
}

func (s *Stack) Peek() (int, bool) {
	if len(s.items) == 0 {
		return 0, false
	}
	return s.items[len(s.items)-1], true
}

func main() {
	ops := []string{
@OPS@
	}
	stack := &Stack{}
	for _, op := range ops {
		parts := strings.Fields(op)
		switch parts[0] {
		case "push":
			pushed, _ := strconv.Atoi(parts[1])
			stack.Push(pushed)
			fmt.Printf("push %d\n", pushed)
		case "pop":
			popped, ok := stack.Pop()
			if ok {
				fmt.Printf("pop %d\n", popped)
			} else {
				fmt.Println("pop empty")
			}
		default:
			peeked, ok := stack.Peek()
			if ok {
				fmt.Printf("peek %d\n", peeked)
			} else {
				fmt.Println("peek empty")
			}
		}
	}
}
""".replace("@OPS@", lines)


def _linked_list(values: tuple) -> str:
    return r"""package main

import (
	"fmt"
	"strconv"
	"strings"
)

type Node struct {
	value int
	next  *Node
}

func build(values []int) *Node {
	var head *Node
	for i := len(values) - 1; i >= 0; i-- {
		head = &Node{value: values[i], next: head}
	}
	return head
}

func reverse(head *Node) *Node {
	var prev *Node
	for head != nil {
		next := head.next
		head.next = prev
		prev = head
		head = next
	}
	return prev
}

func render(head *Node) string {
	parts := []string{}
	for node := head; node != nil; node = node.next {
		parts = append(parts, strconv.Itoa(node.value))
	}
	return strings.Join(parts, " -> ")
}

func main() {
	head := build([]int{@VALUES@})
	fmt.Println(render(head))
	fmt.Println(render(reverse(head)))
}
""".replace("@VALUES@", ", ".join(str(v) for v in values))


def _csv(data: str) -> str:
    return r"""package main

import (
	"fmt"
	"strconv"
	"strings"
)

func parse(data string) ([]string, [][2]int) {
	lines := []string{}
	for _, line := range strings.Split(strings.TrimSpace(data), "\n") {
		if line != "" {
			lines = append(lines, line)
		}
	}
	header := strings.Split(lines[0], ",")
	rows := [][2]int{}
	for _, line := range lines[1:] {
		fields := strings.Split(line, ",")
		first, _ := strconv.Atoi(fields[1])
		second, _ := strconv.Atoi(fields[2])
		rows = append(rows, [2]int{first, second})
	}
	return header, rows
}

func totals(rows [][2]int) (int, int) {
	left, right := 0, 0
	for _, row := range rows {
		left += row[0]
		right += row[1]
	}
	return left, right
}

func main() {
	header, rows := parse("@CSV@")
	left, right := totals(rows)
	fmt.Printf("columns %s,%s\n", header[1], header[2])
	fmt.Printf("%s: %d\n", header[1], left)
	fmt.Printf("%s: %d\n", header[2], right)
}
""".replace("@CSV@", data.replace("\n", "\\n"))


def _sort_records(records: tuple) -> str:
    stock = "\n".join(f'\t\t{{"{name}", {qty}, {price}}},'
                      for name, qty, price in records)
    return r"""package main

import (
	"fmt"
	"sort"
)

type record struct {
	name  string
	qty   int
	price float64
}

func byValue(rows []record) []record {
	out := append([]record{}, rows...)
	sort.Slice(out, func(i, j int) bool {
		left := float64(out[i].qty) * out[i].price
		right := float64(out[j].qty) * out[j].price
		if left != right {
			return left > right
		}
		return out[i].name < out[j].name
	})
	return out
}

func byName(rows []record) []record {
	out := append([]record{}, rows...)
	sort.Slice(out, func(i, j int) bool { return out[i].name < out[j].name })
	return out
}

func render(rows []record) string {
	out := ""
	for index, entry := range rows {
		if index > 0 {
			out += ", "
		}
		out += fmt.Sprintf("%s(%d)", entry.name, entry.qty)
	}
	return out
}

func main() {
	rows := []record{
@STOCK@
	}
	fmt.Println("value", render(byValue(rows)))
	fmt.Println("name ", render(byName(rows)))
}
""".replace("@STOCK@", stock)


def _factors(n: int) -> str:
    numbers = [n // 2, n - 1, n, 7, 11, 13, 17, 19]
    return r"""package main

import (
	"fmt"
	"strconv"
	"strings"
)

func factorise(value int) []int {
	out := []int{}
	divisor := 2
	for divisor*divisor <= value {
		for value%divisor == 0 {
			out = append(out, divisor)
			value /= divisor
		}
		divisor++
	}
	if value > 1 {
		out = append(out, value)
	}
	return out
}

func render(parts []int) string {
	text := make([]string, 0, len(parts))
	for _, part := range parts {
		text = append(text, strconv.Itoa(part))
	}
	return strings.Join(text, " x ")
}

func main() {
	numbers := []int{@NUMBERS@}
	for _, number := range numbers {
		fmt.Printf("%d: %s\n", number, render(factorise(number)))
	}
}
""".replace("@NUMBERS@", ", ".join(str(v) for v in numbers))


def _bank(ledger: tuple) -> str:
    ops = "\n".join(f'\t\t{{"{kind}", {amount}}},' for kind, amount in ledger[1:])
    opening = ledger[0][1]
    return r"""package main

import "fmt"

type entry struct {
	kind    string
	amount  int
	balance int
}

type step struct {
	kind   string
	amount int
}

type Account struct {
	balance int
	log     []entry
}

func open(amount int) *Account {
	account := &Account{balance: amount}
	account.log = append(account.log, entry{"open", amount, amount})
	return account
}

func (a *Account) Deposit(amount int) {
	a.balance += amount
	a.log = append(a.log, entry{"deposit", amount, a.balance})
}

func (a *Account) Withdraw(amount int) {
	if amount > a.balance {
		a.log = append(a.log, entry{"refused", amount, a.balance})
		return
	}
	a.balance -= amount
	a.log = append(a.log, entry{"withdraw", amount, a.balance})
}

func main() {
	account := open(@OPENING@)
	ops := []step{
@OPS@
	}
	for _, op := range ops {
		if op.kind == "deposit" {
			account.Deposit(op.amount)
		} else {
			account.Withdraw(op.amount)
		}
	}
	for _, row := range account.log {
		fmt.Printf("%-9s %4d -> %4d\n", row.kind, row.amount, row.balance)
	}
}
""".replace("@OPS@", ops).replace("@OPENING@", str(opening))


def _pipeline(text: str) -> str:
    return r"""package main

import (
	"fmt"
	"strings"
)

func words(text string) []string {
	return strings.Fields(text)
}

func capitalise(word string) string {
	if word == "" {
		return word
	}
	return strings.ToUpper(word[:1]) + word[1:]
}

func transform(items []string) []string {
	out := make([]string, 0, len(items))
	for _, word := range items {
		out = append(out, capitalise(word))
	}
	return out
}

func longest(items []string) string {
	best := ""
	for _, word := range items {
		if len(word) > len(best) {
			best = word
		}
	}
	return best
}

func totalLetters(items []string) int {
	sum := 0
	for _, word := range items {
		sum += len(word)
	}
	return sum
}

func main() {
	items := words("@TEXT@")
	fmt.Println(strings.Join(transform(items), " | "))
	fmt.Println(len(items), longest(items), totalLetters(items))
}
""".replace("@TEXT@", text)


def programs() -> list[dict]:
    rows: list[dict] = []
    for text in TEXTS:
        rows.append({"title": f"go word frequency: {text[:24]}", "template": "word-freq",
                     "code": _word_freq(text)})
    for records in RECORDS:
        rows.append({"title": f"go inventory: {records[0][0]}", "template": "inventory",
                     "code": _inventory(records)})
    for matrix in MATRICES:
        rows.append({"title": f"go matrix {matrix[0]}", "template": "matrix",
                     "code": _matrix(matrix)})
    for ops in STACKS:
        rows.append({"title": f"go stack {ops[0]}", "template": "stack",
                     "code": _stack(ops)})
    for values in LISTS:
        rows.append({"title": f"go list {list(values)}", "template": "linked-list",
                     "code": _linked_list(values)})
    for data in CSVS:
        rows.append({"title": f"go csv totals: {data.split(',')[0]}", "template": "csv",
                     "code": _csv(data)})
    for records in RECORDS:
        rows.append({"title": f"go sort records: {records[0][0]}", "template": "sort-records",
                     "code": _sort_records(records)})
    for n in NUMBERS:
        rows.append({"title": f"go factors up to {n}", "template": "factors",
                     "code": _factors(n)})
    for ledger in LEDGERS:
        rows.append({"title": f"go ledger from {ledger[0][1]}", "template": "bank",
                     "code": _bank(ledger)})
    for text in TEXTS:
        rows.append({"title": f"go pipeline: {text[:20]}", "template": "pipeline",
                     "code": _pipeline(text)})
    return rows
