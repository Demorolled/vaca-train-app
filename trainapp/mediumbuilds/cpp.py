"""C++ medium builds — five multi-function templates, twenty variants each."""
from __future__ import annotations

LANGUAGE = "cpp"

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
    "pipe filter map pipe filter pipe",
    "open close open save save open",
    "left right left up down left right",
    "fast slow fast fast quick quick slow",
    "ping pong ping ping serve serve pong",
    "add add remove add edit edit remove",
    "start stop start restart stop start",
    "load parse load render render parse load",
    "send wait send send ack ack wait",
    "in out in in over over out",
)

RECORDS = (
    (("bolt", 12, 0.5), ("nut", 40, 0.1), ("washer", 0, 0.05)),
    (("hammer", 3, 12.0), ("saw", 0, 18.5), ("drill", 2, 45.0)),
    (("pen", 100, 1.2), ("ink", 4, 6.0), ("pad", 25, 2.5)),
    (("cpu", 2, 199.0), ("ram", 4, 79.0), ("ssd", 0, 120.0)),
    (("apple", 30, 0.4), ("pear", 0, 0.5), ("plum", 11, 0.8)),
    (("cup", 6, 3.0), ("plate", 6, 4.0), ("fork", 0, 2.0)),
    (("rope", 2, 15.0), ("hook", 9, 4.5), ("glove", 1, 22.0)),
    (("map", 1, 8.0), ("compass", 0, 30.0), ("whistle", 5, 3.5)),
    (("tile", 200, 1.0), ("grout", 3, 9.0), ("seal", 0, 7.0)),
    (("lamp", 4, 25.0), ("bulb", 0, 4.0), ("cable", 12, 3.0)),
    (("screw", 60, 0.08), ("anchor", 2, 1.4), ("plug", 0, 0.9)),
    (("brush", 7, 2.2), ("paint", 0, 19.0), ("tape", 14, 1.1)),
    (("bowl", 9, 6.5), ("spoon", 0, 1.8), ("knife", 3, 12.9)),
    (("fan", 5, 34.0), ("filter", 1, 12.0), ("duct", 0, 26.0)),
    (("seed", 300, 0.02), ("soil", 2, 8.5), ("pot", 0, 4.4)),
    (("bike", 1, 420.0), ("helmet", 2, 65.0), ("lock", 0, 22.0)),
    (("note", 45, 0.3), ("folder", 6, 1.5), ("clip", 0, 0.4)),
    (("brick", 500, 0.7), ("sand", 4, 12.0), ("cement", 0, 18.0)),
    (("chip", 25, 3.2), ("board", 2, 88.0), ("wire", 0, 0.6)),
    (("mug", 11, 7.0), ("tea", 18, 4.2), ("sugar", 0, 2.3)),
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
    ((2, 2, 2), (3, 3, 3), (4, 4, 4)),
    ((1, 0, 1), (0, 1, 0), (1, 0, 1)),
    ((6, 1, 8), (7, 5, 3), (2, 9, 4)),
    ((0, 0, 1), (0, 1, 0), (1, 0, 0)),
    ((10, 20, 30), (40, 50, 60), (70, 80, 90)),
    ((5, 5, 5), (6, 6, 6), (7, 7, 7)),
    ((1, 3, 5), (7, 9, 11), (13, 15, 17)),
    ((8, 6, 4), (2, 0, 2), (4, 6, 8)),
    ((2, 4, 8), (16, 32, 64), (128, 256, 512)),
    ((9, 0, 9), (0, 9, 0), (9, 0, 9)),
)

STACK_OPS = (
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
    ("push 11", "push 12", "pop", "pop", "push 13", "peek", "pop"),
    ("push 7", "peek", "pop", "peek", "push 14", "pop", "pop"),
    ("push 15", "push 16", "push 17", "peek", "pop", "pop", "pop"),
    ("push 1", "pop", "push 1", "pop", "push 1", "pop", "pop"),
    ("push 20", "push 21", "pop", "push 22", "pop", "peek", "pop"),
    ("push 2", "push 3", "pop", "peek", "push 4", "pop", "peek"),
    ("push 30", "pop", "push 31", "push 32", "peek", "pop", "pop"),
    ("push 8", "push 9", "pop", "pop", "push 10", "peek", "pop"),
    ("push 5", "push 5", "pop", "push 5", "pop", "peek", "pop"),
    ("push 40", "push 41", "push 42", "pop", "peek", "pop", "pop"),
)

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
    (("open", 500), ("withdraw", 100), ("withdraw", 400), ("deposit", 25)),
    (("open", 12), ("deposit", 3), ("withdraw", 15), ("deposit", 1)),
    (("open", 90), ("withdraw", 45), ("withdraw", 45), ("withdraw", 0)),
    (("open", 7), ("deposit", 70), ("withdraw", 77), ("deposit", 7)),
    (("open", 300), ("withdraw", 150), ("deposit", 150), ("withdraw", 300)),
    (("open", 2), ("deposit", 2), ("withdraw", 2), ("withdraw", 2)),
    (("open", 60), ("withdraw", 61), ("deposit", 2), ("withdraw", 1)),
    (("open", 45), ("deposit", 5), ("withdraw", 50), ("withdraw", 0)),
    (("open", 18), ("withdraw", 9), ("withdraw", 9), ("deposit", 9)),
    (("open", 400), ("deposit", 100), ("withdraw", 500), ("withdraw", 1)),
)


def _word_freq(text: str) -> str:
    return f"""#include <algorithm>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

std::vector<std::string> tokens(const std::string& text) {{
    std::istringstream stream(text);
    std::vector<std::string> out;
    std::string word;
    while (stream >> word) out.push_back(word);
    return out;
}}

std::map<std::string, int> counts(const std::vector<std::string>& words) {{
    std::map<std::string, int> table;
    for (const auto& word : words) table[word] += 1;
    return table;
}}

std::vector<std::pair<std::string, int>> ranked(const std::map<std::string, int>& table) {{
    std::vector<std::pair<std::string, int>> rows(table.begin(), table.end());
    std::sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) {{
        if (a.second != b.second) return a.second > b.second;
        return a.first < b.first;
    }});
    return rows;
}}

int main() {{
    const std::string text = "{text}";
    auto rows = ranked(counts(tokens(text)));
    for (size_t i = 0; i < rows.size() && i < 4; ++i)
        std::cout << rows[i].first << ": " << rows[i].second << "\\n";
    return 0;
}}
"""


def _inventory(records: tuple) -> str:
    items = "\n".join(f'        {{"{name}", {qty}, {price}}},' for name, qty, price in records)
    return f"""#include <cstdio>
#include <string>
#include <vector>

struct Item {{
    std::string name;
    int qty;
    double price;
}};

std::vector<Item> available(const std::vector<Item>& stock) {{
    std::vector<Item> out;
    for (const auto& item : stock)
        if (item.qty > 0) out.push_back(item);
    return out;
}}

double total_value(const std::vector<Item>& rows) {{
    double sum = 0.0;
    for (const auto& row : rows) sum += row.qty * row.price;
    return sum;
}}

void render(const std::vector<Item>& rows) {{
    for (const auto& row : rows)
        printf("%-8s %3d x %6.2f = %8.2f\\n", row.name.c_str(), row.qty,
               row.price, row.qty * row.price);
}}

int main() {{
    std::vector<Item> stock = {{
{items}
    }};
    auto rows = available(stock);
    render(rows);
    printf("total %.2f\\n", total_value(rows));
    return 0;
}}
"""


def _matrix(matrix: tuple) -> str:
    rows = "\n".join(f"        {{{', '.join(str(v) for v in row)}}}," for row in matrix)
    return f"""#include <array>
#include <cstdio>

using Matrix = std::array<std::array<int, 3>, 3>;

Matrix transpose(const Matrix& m) {{
    Matrix out{{}};
    for (size_t r = 0; r < 3; ++r)
        for (size_t c = 0; c < 3; ++c) out[c][r] = m[r][c];
    return out;
}}

std::array<int, 3> row_sums(const Matrix& m) {{
    std::array<int, 3> sums{{}};
    for (size_t r = 0; r < 3; ++r)
        for (size_t c = 0; c < 3; ++c) sums[r] += m[r][c];
    return sums;
}}

void render(const Matrix& m) {{
    for (const auto& row : m) {{
        for (int value : row) printf("%4d", value);
        printf("\\n");
    }}
}}

int main() {{
    Matrix m = {{{{
{rows}
    }}}};
    render(transpose(m));
    auto sums = row_sums(m);
    printf("sums %d %d %d\\n", sums[0], sums[1], sums[2]);
    return 0;
}}
"""


def _stack(ops: tuple) -> str:
    calls = "\n".join(f'        "{op}",' for op in ops)
    return f"""#include <cstdio>
#include <string>
#include <vector>

struct Stack {{
    std::vector<int> items;

    void push(int value) {{ items.push_back(value); }}
    bool pop(int& out) {{
        if (items.empty()) return false;
        out = items.back();
        items.pop_back();
        return true;
    }}
    bool peek(int& out) const {{
        if (items.empty()) return false;
        out = items.back();
        return true;
    }}
}};

std::vector<std::string> run(Stack& stack, const std::vector<std::string>& ops) {{
    std::vector<std::string> out;
    for (const auto& op : ops) {{
        auto space = op.find(' ');
        std::string name = op.substr(0, space);
        if (name == "push") {{
            int value = std::stoi(op.substr(space + 1));
            stack.push(value);
            out.push_back("push " + std::to_string(value));
        }} else {{
            int value = 0;
            bool ok = name == "pop" ? stack.pop(value) : stack.peek(value);
            out.push_back(name + (ok ? " " + std::to_string(value) : " none"));
        }}
    }}
    return out;
}}

int main() {{
    Stack stack;
    std::vector<std::string> ops = {{
{calls}
    }};
    for (const auto& line : run(stack, ops)) printf("%s\\n", line.c_str());
    return 0;
}}
"""


def _bank(ledger: tuple) -> str:
    calls = "\n".join(f'        {{"{kind}", {amount}}},' for kind, amount in ledger)
    return f"""#include <cstdio>
#include <string>
#include <utility>
#include <vector>

struct Entry {{
    std::string kind;
    int amount;
    int balance;
}};

struct Account {{
    int balance;
    std::vector<Entry> log;

    Account(int opening) : balance(opening) {{}}

    void deposit(int amount) {{
        balance += amount;
        log.push_back({{"deposit", amount, balance}});
    }}

    bool withdraw(int amount) {{
        if (amount > balance) {{
            log.push_back({{"refused", amount, balance}});
            return false;
        }}
        balance -= amount;
        log.push_back({{"withdraw", amount, balance}});
        return true;
    }}
}};

std::vector<Entry> run(int opening, const std::vector<std::pair<std::string, int>>& ops) {{
    Account account(opening);
    account.log.push_back({{"open", opening, opening}});
    for (size_t i = 1; i < ops.size(); ++i) {{
        if (ops[i].first == "deposit") account.deposit(ops[i].second);
        else account.withdraw(ops[i].second);
    }}
    return account.log;
}}

int main() {{
    std::vector<std::pair<std::string, int>> ops = {{
{calls}
    }};
    for (const auto& row : run(ops.front().second, ops))
        printf("%-9s %4d -> %4d\\n", row.kind.c_str(), row.amount, row.balance);
    return 0;
}}
"""


def programs() -> list[dict]:
    rows: list[dict] = []
    for text in TEXTS:
        rows.append({"title": f"word frequency: {text[:22]}", "template": "word-freq",
                     "code": _word_freq(text)})
    for records in RECORDS:
        rows.append({"title": f"inventory: {records[0][0]}", "template": "inventory",
                     "code": _inventory(records)})
    for matrix in MATRICES:
        rows.append({"title": f"matrix {matrix[0]}", "template": "matrix",
                     "code": _matrix(matrix)})
    for ops in STACK_OPS:
        rows.append({"title": f"stack {ops[0]}", "template": "stack",
                     "code": _stack(ops)})
    for ledger in LEDGERS:
        rows.append({"title": f"ledger from {ledger[0][1]}", "template": "bank",
                     "code": _bank(ledger)})
    return rows
