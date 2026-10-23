"""Rust medium builds — ten templates with real functions and data structures.

Borrow-checker-friendly by construction: owned data, `&str`/slices in signatures,
no lifetimes spelled out, and the linked list is an index arena rather than a web
of `Box`es.
"""
from __future__ import annotations

LANGUAGE = "rust"

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
    return """use std::collections::BTreeMap;

fn counts(text: &str) -> BTreeMap<&str, usize> {
    let mut table = BTreeMap::new();
    for word in text.split_whitespace() {
        *table.entry(word).or_insert(0) += 1;
    }
    table
}

fn ranked<'a>(table: &BTreeMap<&'a str, usize>) -> Vec<(&'a str, usize)> {
    let mut rows: Vec<(&str, usize)> = table.iter().map(|(w, c)| (*w, *c)).collect();
    rows.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    rows
}

fn main() {
    let text = "@TEXT@";
    let table = counts(text);
    for (word, count) in ranked(&table).into_iter().take(4) {
        println!("{}: {}", word, count);
    }
}
""".replace("@TEXT@", text)


def _inventory(records: tuple) -> str:
    stock = "\n".join(f'        Item {{ name: "{name}", qty: {qty}, price: {price} }},'
                      for name, qty, price in records)
    return """struct Item {
    name: &'static str,
    qty: i32,
    price: f64,
}

fn available(items: &[Item]) -> Vec<&Item> {
    items.iter().filter(|item| item.qty > 0).collect()
}

fn total(items: &[&Item]) -> f64 {
    items.iter().map(|item| item.qty as f64 * item.price).sum()
}

fn render(items: &[&Item]) -> Vec<String> {
    items
        .iter()
        .map(|item| {
            format!(
                "{:<8} {:>3} x {:>6.2} = {:>8.2}",
                item.name,
                item.qty,
                item.price,
                item.qty as f64 * item.price
            )
        })
        .collect()
}

fn main() {
    let stock = vec![
@STOCK@
    ];
    let rows = available(&stock);
    for line in render(&rows) {
        println!("{}", line);
    }
    println!("total {:.2}", total(&rows));
}
""".replace("@STOCK@", stock)


def _matrix(matrix: tuple) -> str:
    rows = ",\n    ".join("[" + ", ".join(str(v) for v in row) + "]" for row in matrix)
    return """fn transpose(m: &[[i32; 3]; 3]) -> [[i32; 3]; 3] {
    let mut out = [[0i32; 3]; 3];
    for i in 0..3 {
        for j in 0..3 {
            out[j][i] = m[i][j];
        }
    }
    out
}

fn row_sums(m: &[[i32; 3]; 3]) -> [i32; 3] {
    let mut sums = [0i32; 3];
    for i in 0..3 {
        for j in 0..3 {
            sums[i] += m[i][j];
        }
    }
    sums
}

fn main() {
    let m: [[i32; 3]; 3] = [
    @ROWS@,
    ];
    for row in transpose(&m) {
        println!("{:>3} {:>3} {:>3}", row[0], row[1], row[2]);
    }
    let sums = row_sums(&m);
    println!("sums {} {} {}", sums[0], sums[1], sums[2]);
}
""".replace("@ROWS@", rows)


def _stack(ops: tuple) -> str:
    lines = "\n".join(f'        "{op}".to_string(),' for op in ops)
    return """struct Stack {
    items: Vec<i32>,
}

impl Stack {
    fn new() -> Stack {
        Stack { items: Vec::new() }
    }

    fn push(&mut self, value: i32) {
        self.items.push(value);
    }

    fn pop(&mut self) -> Option<i32> {
        self.items.pop()
    }

    fn peek(&self) -> Option<i32> {
        self.items.last().copied()
    }
}

fn main() {
    let ops: Vec<String> = vec![
@OPS@
    ];
    let mut stack = Stack::new();
    for op in &ops {
        let parts: Vec<&str> = op.split_whitespace().collect();
        match parts[0] {
            "push" => {
                let pushed: i32 = parts[1].parse().unwrap_or(0);
                stack.push(pushed);
                println!("push {}", pushed);
            }
            "pop" => match stack.pop() {
                Some(value) => println!("pop {}", value),
                None => println!("pop empty"),
            },
            _ => match stack.peek() {
                Some(value) => println!("peek {}", value),
                None => println!("peek empty"),
            },
        }
    }
}
""".replace("@OPS@", lines)


def _linked_list(values: tuple) -> str:
    return """struct Node {
    value: i32,
    next: Option<usize>,
}

struct List {
    nodes: Vec<Node>,
    head: Option<usize>,
}

impl List {
    fn new() -> List {
        List { nodes: Vec::new(), head: None }
    }

    fn push_front(&mut self, value: i32) {
        let next = self.head;
        self.nodes.push(Node { value, next });
        self.head = Some(self.nodes.len() - 1);
    }

    fn reverse(&mut self) {
        let mut prev: Option<usize> = None;
        let mut current = self.head;
        while let Some(index) = current {
            let next = self.nodes[index].next;
            self.nodes[index].next = prev;
            prev = Some(index);
            current = next;
        }
        self.head = prev;
    }

    fn render(&self) -> String {
        let mut parts: Vec<String> = Vec::new();
        let mut current = self.head;
        while let Some(index) = current {
            parts.push(self.nodes[index].value.to_string());
            current = self.nodes[index].next;
        }
        parts.join(" -> ")
    }
}

fn main() {
    let mut list = List::new();
    for value in [@VALUES@] {
        list.push_front(value);
    }
    println!("{}", list.render());
    list.reverse();
    println!("{}", list.render());
}
""".replace("@VALUES@", ", ".join(str(v) for v in values))


def _csv(data: str) -> str:
    return """fn parse(data: &str) -> (Vec<&str>, Vec<(i32, i32)>) {
    let lines: Vec<&str> = data.trim().split('\\n').filter(|line| !line.is_empty()).collect();
    let header: Vec<&str> = lines[0].split(',').collect();
    let rows: Vec<(i32, i32)> = lines[1..]
        .iter()
        .map(|line| {
            let fields: Vec<&str> = line.split(',').collect();
            (
                fields[1].parse().unwrap_or(0),
                fields[2].parse().unwrap_or(0),
            )
        })
        .collect();
    (header, rows)
}

fn totals(rows: &[(i32, i32)]) -> (i32, i32) {
    rows.iter().fold((0, 0), |acc, row| (acc.0 + row.0, acc.1 + row.1))
}

fn main() {
    let (header, rows) = parse("@CSV@");
    let (left, right) = totals(&rows);
    println!("columns {},{}", header[1], header[2]);
    println!("{}: {}", header[1], left);
    println!("{}: {}", header[2], right);
}
""".replace("@CSV@", data.replace("\n", "\\n"))


def _sort_records(records: tuple) -> str:
    stock = "\n".join(f'        Item {{ name: "{name}", qty: {qty}, price: {price} }},'
                      for name, qty, price in records)
    return """struct Item {
    name: &'static str,
    qty: i32,
    price: f64,
}

fn by_value(rows: &[Item]) -> Vec<&Item> {
    let mut out: Vec<&Item> = rows.iter().collect();
    out.sort_by(|a, b| {
        let left = a.qty as f64 * a.price;
        let right = b.qty as f64 * b.price;
        right.partial_cmp(&left).unwrap_or(std::cmp::Ordering::Equal).then(a.name.cmp(&b.name))
    });
    out
}

fn by_name(rows: &[Item]) -> Vec<&Item> {
    let mut out: Vec<&Item> = rows.iter().collect();
    out.sort_by(|a, b| a.name.cmp(&b.name));
    out
}

fn render(rows: &[&Item]) -> String {
    rows.iter()
        .map(|item| format!("{}({})", item.name, item.qty))
        .collect::<Vec<String>>()
        .join(", ")
}

fn main() {
    let rows = vec![
@STOCK@
    ];
    println!("value {}", render(&by_value(&rows)));
    println!("name  {}", render(&by_name(&rows)));
}
""".replace("@STOCK@", stock)


def _factors(n: int) -> str:
    numbers = [n // 2, n - 1, n, 7, 11, 13, 17, 19]
    return """fn factorise(mut value: i32) -> Vec<i32> {
    let mut out = Vec::new();
    let mut divisor = 2;
    while divisor * divisor <= value {
        while value % divisor == 0 {
            out.push(divisor);
            value /= divisor;
        }
        divisor += 1;
    }
    if value > 1 {
        out.push(value);
    }
    out
}

fn render(parts: &[i32]) -> String {
    parts
        .iter()
        .map(|part| part.to_string())
        .collect::<Vec<String>>()
        .join(" x ")
}

fn main() {
    let numbers: Vec<i32> = vec![@NUMBERS@];
    for number in numbers {
        println!("{}: {}", number, render(&factorise(number)));
    }
}
""".replace("@NUMBERS@", ", ".join(str(v) for v in numbers))


def _bank(ledger: tuple) -> str:
    ops = "\n".join(f'        ("{kind}", {amount}),' for kind, amount in ledger[1:])
    opening = ledger[0][1]
    return """struct Entry {
    kind: String,
    amount: i32,
    balance: i32,
}

struct Account {
    balance: i32,
    log: Vec<Entry>,
}

impl Account {
    fn open(amount: i32) -> Account {
        Account {
            balance: amount,
            log: vec![Entry { kind: "open".to_string(), amount, balance: amount }],
        }
    }

    fn deposit(&mut self, amount: i32) {
        self.balance += amount;
        self.log.push(Entry {
            kind: "deposit".to_string(),
            amount,
            balance: self.balance,
        });
    }

    fn withdraw(&mut self, amount: i32) {
        if amount > self.balance {
            self.log.push(Entry {
                kind: "refused".to_string(),
                amount,
                balance: self.balance,
            });
            return;
        }
        self.balance -= amount;
        self.log.push(Entry {
            kind: "withdraw".to_string(),
            amount,
            balance: self.balance,
        });
    }
}

fn main() {
    let ops: Vec<(&str, i32)> = vec![
@OPS@
    ];
    let mut account = Account::open(@OPENING@);
    for (kind, amount) in ops {
        if kind == "deposit" {
            account.deposit(amount);
        } else {
            account.withdraw(amount);
        }
    }
    for entry in &account.log {
        println!("{:<9} {:>4} -> {:>4}", entry.kind, entry.amount, entry.balance);
    }
}
""".replace("@OPS@", ops).replace("@OPENING@", str(opening))


def _pipeline(text: str) -> str:
    return """fn words(text: &str) -> Vec<&str> {
    text.split_whitespace().collect()
}

fn capitalise(word: &str) -> String {
    let mut chars = word.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
        None => String::new(),
    }
}

fn transform(items: &[&str]) -> Vec<String> {
    items.iter().map(|word| capitalise(word)).collect()
}

fn longest<'a>(items: &[&'a str]) -> &'a str {
    items.iter().max_by_key(|word| word.len()).copied().unwrap_or("")
}

fn total_letters(items: &[&str]) -> usize {
    items.iter().map(|word| word.len()).sum()
}

fn main() {
    let items = words("@TEXT@");
    println!("{}", transform(&items).join(" | "));
    println!("{} {} {}", items.len(), longest(&items), total_letters(&items));
}
""".replace("@TEXT@", text)


def programs() -> list[dict]:
    rows: list[dict] = []
    for text in TEXTS:
        rows.append({"title": f"rust word frequency: {text[:24]}", "template": "word-freq",
                     "code": _word_freq(text)})
    for records in RECORDS:
        rows.append({"title": f"rust inventory: {records[0][0]}", "template": "inventory",
                     "code": _inventory(records)})
    for matrix in MATRICES:
        rows.append({"title": f"rust matrix {matrix[0]}", "template": "matrix",
                     "code": _matrix(matrix)})
    for ops in STACKS:
        rows.append({"title": f"rust stack: {' '.join(ops[:2])}", "template": "stack",
                     "code": _stack(ops)})
    for values in LISTS:
        rows.append({"title": f"rust list {list(values)}", "template": "linked-list",
                     "code": _linked_list(values)})
    for data in CSVS:
        rows.append({"title": f"rust csv totals: {data.split(',')[0]}", "template": "csv",
                     "code": _csv(data)})
    for records in RECORDS:
        rows.append({"title": f"rust sort records: {records[0][0]}", "template": "sort-records",
                     "code": _sort_records(records)})
    for n in NUMBERS:
        rows.append({"title": f"rust factors up to {n}", "template": "factors",
                     "code": _factors(n)})
    for ledger in LEDGERS:
        rows.append({"title": f"rust ledger from {ledger[0][1]}", "template": "bank",
                     "code": _bank(ledger)})
    for text in TEXTS:
        rows.append({"title": f"rust pipeline: {text[:20]}", "template": "pipeline",
                     "code": _pipeline(text)})
    return rows
