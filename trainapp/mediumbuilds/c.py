"""C medium builds — ten templates with structs, arrays and several functions.

No malloc, no dynamic strings, no undefined behaviour: fixed arrays with explicit
capacities, `strtok` on a writable buffer, and `printf` specifiers matched to the
argument types. Every program returns 0 from `main`.
"""
from __future__ import annotations

LANGUAGE = "c"

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
    return r"""#include <stdio.h>
#include <string.h>

#define MAX_WORDS 64
#define MAX_LEN 32
#define TOP 4

static char words[MAX_WORDS][MAX_LEN];
static int counts[MAX_WORDS];
static int total = 0;

static int find(const char *word) {
    for (int i = 0; i < total; i++) {
        if (strcmp(words[i], word) == 0) {
            return i;
        }
    }
    return -1;
}

static void add(const char *word) {
    int index = find(word);
    if (index >= 0) {
        counts[index] += 1;
        return;
    }
    if (total < MAX_WORDS) {
        strncpy(words[total], word, MAX_LEN - 1);
        words[total][MAX_LEN - 1] = '\0';
        counts[total] = 1;
        total += 1;
    }
}

static int best(void) {
    int index = 0;
    for (int i = 1; i < total; i++) {
        if (counts[i] > counts[index] ||
            (counts[i] == counts[index] && strcmp(words[i], words[index]) < 0)) {
            index = i;
        }
    }
    return index;
}

int main(void) {
    char text[] = "@TEXT@";
    for (char *word = strtok(text, " "); word != NULL; word = strtok(NULL, " ")) {
        add(word);
    }
    for (int printed = 0; printed < TOP && printed < total; printed++) {
        int index = best();
        if (counts[index] < 0) {
            break;
        }
        printf("%s: %d\n", words[index], counts[index]);
        counts[index] = -1;
    }
    return 0;
}
""".replace("@TEXT@", text)


def _inventory(records: tuple) -> str:
    stock = "\n".join(f'    {{"{name}", {qty}, {price}}},' for name, qty, price in records)
    return r"""#include <stdio.h>

#define COUNT 3

struct item {
    char name[12];
    int qty;
    double price;
};

static int available(const struct item *items, int count, int *picked) {
    int found = 0;
    for (int i = 0; i < count; i++) {
        if (items[i].qty > 0) {
            picked[found] = i;
            found += 1;
        }
    }
    return found;
}

static double total(const struct item *items, const int *picked, int found) {
    double sum = 0.0;
    for (int i = 0; i < found; i++) {
        sum += items[picked[i]].qty * items[picked[i]].price;
    }
    return sum;
}

int main(void) {
    struct item stock[COUNT] = {
@STOCK@
    };
    int picked[COUNT];
    int found = available(stock, COUNT, picked);
    for (int i = 0; i < found; i++) {
        struct item entry = stock[picked[i]];
        printf("%-8s %3d x %6.2f = %8.2f\n", entry.name, entry.qty, entry.price,
               entry.qty * entry.price);
    }
    printf("total %.2f\n", total(stock, picked, found));
    return 0;
}
""".replace("@STOCK@", stock)


def _matrix(matrix: tuple) -> str:
    rows = ",\n    ".join("{" + ", ".join(str(v) for v in row) + "}" for row in matrix)
    return r"""#include <stdio.h>

static void transpose(const int in[3][3], int out[3][3]) {
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            out[j][i] = in[i][j];
        }
    }
}

static void row_sums(const int matrix[3][3], int sums[3]) {
    for (int i = 0; i < 3; i++) {
        sums[i] = 0;
        for (int j = 0; j < 3; j++) {
            sums[i] += matrix[i][j];
        }
    }
}

int main(void) {
    int matrix[3][3] = {
    @ROWS@,
    };
    int flipped[3][3];
    int sums[3];
    transpose(matrix, flipped);
    row_sums(matrix, sums);
    for (int i = 0; i < 3; i++) {
        printf("%3d %3d %3d\n", flipped[i][0], flipped[i][1], flipped[i][2]);
    }
    printf("sums %d %d %d\n", sums[0], sums[1], sums[2]);
    return 0;
}
""".replace("@ROWS@", rows)


def _stack(ops: tuple) -> str:
    lines = "\n".join(f'    "{op}",' for op in ops)
    return r"""#include <stdio.h>
#include <string.h>

#define CAPACITY 32

struct stack {
    int items[CAPACITY];
    int size;
};

static void push(struct stack *s, int value) {
    if (s->size < CAPACITY) {
        s->items[s->size] = value;
        s->size += 1;
    }
}

static int pop(struct stack *s, int *value) {
    if (s->size == 0) {
        return 0;
    }
    *value = s->items[s->size - 1];
    s->size -= 1;
    return 1;
}

static int peek(const struct stack *s, int *value) {
    if (s->size == 0) {
        return 0;
    }
    *value = s->items[s->size - 1];
    return 1;
}

int main(void) {
    const char *ops[] = {
@OPS@
    };
    struct stack s = {{0}, 0};
    char name[8];
    int value = 0;
    int count = (int)(sizeof(ops) / sizeof(ops[0]));
    for (int i = 0; i < count; i++) {
        if (sscanf(ops[i], "%7s %d", name, &value) == 2) {
            push(&s, value);
            printf("push %d\n", value);
        } else if (strcmp(ops[i], "pop") == 0) {
            if (pop(&s, &value)) {
                printf("pop %d\n", value);
            } else {
                printf("pop empty\n");
            }
        } else {
            if (peek(&s, &value)) {
                printf("peek %d\n", value);
            } else {
                printf("peek empty\n");
            }
        }
    }
    return 0;
}
""".replace("@OPS@", lines)


def _linked_list(values: tuple) -> str:
    return r"""#include <stdio.h>

#define MAX_NODES 16

struct node {
    int value;
    int next;
};

static struct node pool[MAX_NODES];
static int used = 0;

static int push_front(int head, int value) {
    if (used >= MAX_NODES) {
        return head;
    }
    pool[used].value = value;
    pool[used].next = head;
    used += 1;
    return used - 1;
}

static int reverse(int head) {
    int previous = -1;
    int current = head;
    while (current != -1) {
        int next = pool[current].next;
        pool[current].next = previous;
        previous = current;
        current = next;
    }
    return previous;
}

static void render(int head) {
    int current = head;
    while (current != -1) {
        printf("%d", pool[current].value);
        current = pool[current].next;
        if (current != -1) {
            printf(" -> ");
        }
    }
    printf("\n");
}

int main(void) {
    int values[] = {@VALUES@};
    int count = (int)(sizeof(values) / sizeof(values[0]));
    int head = -1;
    for (int i = count - 1; i >= 0; i--) {
        head = push_front(head, values[i]);
    }
    render(head);
    render(reverse(head));
    return 0;
}
""".replace("@VALUES@", ", ".join(str(v) for v in values))


def _csv(data: str) -> str:
    return r"""#include <stdio.h>
#include <string.h>

#define MAX_ROWS 8

static int parse(const char *data, char first[16], char second[16],
                 int *left, int *right) {
    char buffer[512];
    strncpy(buffer, data, sizeof(buffer) - 1);
    buffer[sizeof(buffer) - 1] = '\0';
    int rows = 0;
    char *line = strtok(buffer, "\n");
    if (line == NULL) {
        return 0;
    }
    sscanf(line, "%*[^,],%15[^,],%15[^,]", first, second);
    while ((line = strtok(NULL, "\n")) != NULL && rows < MAX_ROWS) {
        int a = 0;
        int b = 0;
        if (sscanf(line, "%*[^,],%d,%d", &a, &b) == 2) {
            *left += a;
            *right += b;
            rows += 1;
        }
    }
    return rows;
}

int main(void) {
    char first[16] = "";
    char second[16] = "";
    int left = 0;
    int right = 0;
    int rows = parse("@CSV@", first, second, &left, &right);
    printf("columns %s,%s\n", first, second);
    printf("%s: %d\n", first, left);
    printf("%s: %d\n", second, right);
    printf("rows %d\n", rows);
    return 0;
}
""".replace("@CSV@", data.replace("\n", "\\n"))


def _sort_records(records: tuple) -> str:
    stock = "\n".join(f'    {{"{name}", {qty}, {price}}},' for name, qty, price in records)
    return r"""#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define COUNT 3

struct record {
    char name[12];
    int qty;
    double price;
};

static double value(const struct record *entry) {
    return entry->qty * entry->price;
}

static int by_value(const void *left, const void *right) {
    const struct record *a = (const struct record *)left;
    const struct record *b = (const struct record *)right;
    double va = value(a);
    double vb = value(b);
    if (va > vb) {
        return -1;
    }
    if (va < vb) {
        return 1;
    }
    return strcmp(a->name, b->name);
}

static int by_name(const void *left, const void *right) {
    const struct record *a = (const struct record *)left;
    const struct record *b = (const struct record *)right;
    return strcmp(a->name, b->name);
}

static void render(const struct record *rows, int count) {
    for (int i = 0; i < count; i++) {
        if (i > 0) {
            printf(", ");
        }
        printf("%s(%d)", rows[i].name, rows[i].qty);
    }
    printf("\n");
}

int main(void) {
    struct record rows[COUNT] = {
@STOCK@
    };
    struct record copy[COUNT];
    memcpy(copy, rows, sizeof(rows));
    qsort(copy, COUNT, sizeof(struct record), by_value);
    printf("value ");
    render(copy, COUNT);
    memcpy(copy, rows, sizeof(rows));
    qsort(copy, COUNT, sizeof(struct record), by_name);
    printf("name  ");
    render(copy, COUNT);
    return 0;
}
""".replace("@STOCK@", stock)


def _factors(n: int) -> str:
    numbers = [n // 2, n - 1, n, 7, 11, 13, 17, 19]
    return r"""#include <stdio.h>

#define MAX_PARTS 16
#define COUNT 8

static int factorise(int value, int *parts) {
    int found = 0;
    int divisor = 2;
    while (divisor * divisor <= value && found < MAX_PARTS) {
        while (value % divisor == 0 && found < MAX_PARTS) {
            parts[found] = divisor;
            found += 1;
            value /= divisor;
        }
        divisor += 1;
    }
    if (value > 1 && found < MAX_PARTS) {
        parts[found] = value;
        found += 1;
    }
    return found;
}

static void render(const int *parts, int found) {
    for (int i = 0; i < found; i++) {
        if (i > 0) {
            printf(" x ");
        }
        printf("%d", parts[i]);
    }
}

int main(void) {
    int numbers[COUNT] = {@NUMBERS@};
    int parts[MAX_PARTS];
    for (int i = 0; i < COUNT; i++) {
        int found = factorise(numbers[i], parts);
        printf("%d: ", numbers[i]);
        render(parts, found);
        printf("\n");
    }
    return 0;
}
""".replace("@NUMBERS@", ", ".join(str(v) for v in numbers))


def _bank(ledger: tuple) -> str:
    ops = "\n".join(f'    {{"{kind}", {amount}}},' for kind, amount in ledger[1:])
    opening = ledger[0][1]
    return r"""#include <stdio.h>
#include <string.h>

#define MAX_ENTRIES 16

struct entry {
    char kind[10];
    int amount;
    int balance;
};

struct account {
    int balance;
    struct entry log[MAX_ENTRIES];
    int count;
};

static void record(struct account *a, const char *kind, int amount) {
    if (a->count < MAX_ENTRIES) {
        strncpy(a->log[a->count].kind, kind, sizeof(a->log[a->count].kind) - 1);
        a->log[a->count].kind[sizeof(a->log[a->count].kind) - 1] = '\0';
        a->log[a->count].amount = amount;
        a->log[a->count].balance = a->balance;
        a->count += 1;
    }
}

static void deposit(struct account *a, int amount) {
    a->balance += amount;
    record(a, "deposit", amount);
}

static void withdraw(struct account *a, int amount) {
    if (amount > a->balance) {
        record(a, "refused", amount);
        return;
    }
    a->balance -= amount;
    record(a, "withdraw", amount);
}

int main(void) {
    struct account a;
    a.balance = @OPENING@;
    a.count = 0;
    record(&a, "open", a.balance);
    struct { const char *kind; int amount; } ops[] = {
@OPS@
    };
    int count = (int)(sizeof(ops) / sizeof(ops[0]));
    for (int i = 0; i < count; i++) {
        if (strcmp(ops[i].kind, "deposit") == 0) {
            deposit(&a, ops[i].amount);
        } else {
            withdraw(&a, ops[i].amount);
        }
    }
    for (int i = 0; i < a.count; i++) {
        printf("%-9s %4d -> %4d\n", a.log[i].kind, a.log[i].amount, a.log[i].balance);
    }
    return 0;
}
""".replace("@OPS@", ops).replace("@OPENING@", str(opening))


def _pipeline(text: str) -> str:
    return r"""#include <stdio.h>
#include <string.h>

#define MAX_WORDS 16
#define MAX_LEN 32

static int split(char *text, char words[MAX_WORDS][MAX_LEN]) {
    int found = 0;
    char *word = strtok(text, " ");
    while (word != NULL && found < MAX_WORDS) {
        strncpy(words[found], word, MAX_LEN - 1);
        words[found][MAX_LEN - 1] = '\0';
        found += 1;
        word = strtok(NULL, " ");
    }
    return found;
}

static void capitalise(char *word) {
    if (word[0] >= 'a' && word[0] <= 'z') {
        word[0] = (char)(word[0] - 'a' + 'A');
    }
}

static int longest(char words[MAX_WORDS][MAX_LEN], int count) {
    int best = 0;
    for (int i = 1; i < count; i++) {
        if (strlen(words[i]) > strlen(words[best])) {
            best = i;
        }
    }
    return best;
}

static int total_letters(char words[MAX_WORDS][MAX_LEN], int count) {
    int sum = 0;
    for (int i = 0; i < count; i++) {
        sum += (int)strlen(words[i]);
    }
    return sum;
}

int main(void) {
    char text[] = "@TEXT@";
    char words[MAX_WORDS][MAX_LEN];
    int count = split(text, words);
    for (int i = 0; i < count; i++) {
        capitalise(words[i]);
    }
    for (int i = 0; i < count; i++) {
        if (i > 0) {
            printf(" | ");
        }
        printf("%s", words[i]);
    }
    printf("\n%d %s %d\n", count, words[longest(words, count)],
           total_letters(words, count));
    return 0;
}
""".replace("@TEXT@", text)


def programs() -> list[dict]:
    rows: list[dict] = []
    for text in TEXTS:
        rows.append({"title": f"c word frequency: {text[:24]}", "template": "word-freq",
                     "code": _word_freq(text)})
    for records in RECORDS:
        rows.append({"title": f"c inventory: {records[0][0]}", "template": "inventory",
                     "code": _inventory(records)})
    for matrix in MATRICES:
        rows.append({"title": f"c matrix {matrix[0]}", "template": "matrix",
                     "code": _matrix(matrix)})
    for ops in STACKS:
        rows.append({"title": f"c stack: {' '.join(ops[:2])}", "template": "stack",
                     "code": _stack(ops)})
    for values in LISTS:
        rows.append({"title": f"c list {list(values)}", "template": "linked-list",
                     "code": _linked_list(values)})
    for data in CSVS:
        rows.append({"title": f"c csv totals: {data.split(',')[0]}", "template": "csv",
                     "code": _csv(data)})
    for records in RECORDS:
        rows.append({"title": f"c sort records: {records[0][0]}", "template": "sort-records",
                     "code": _sort_records(records)})
    for n in NUMBERS:
        rows.append({"title": f"c factors up to {n}", "template": "factors",
                     "code": _factors(n)})
    for ledger in LEDGERS:
        rows.append({"title": f"c ledger from {ledger[0][1]}", "template": "bank",
                     "code": _bank(ledger)})
    for text in TEXTS:
        rows.append({"title": f"c pipeline: {text[:20]}", "template": "pipeline",
                     "code": _pipeline(text)})
    return rows
