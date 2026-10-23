"""c.py — the five family programs, in C.

C is one of the five lanes and, before this file, had the thinnest part of the
judgeable pool: four sets, none of them in a family with siblings. These are the
same five programs the JavaScript, Python, Go and Java sets implement, so each
family goes from three in-focus siblings to five.

Layout: `main.c` holds the fixed input, `<program>.c` is the target the model is
asked to complete, and `report.c` is the formatting sibling. The set is built as
`gcc *.c -o .node-bin`, so the headers travel with the sources.

Each set prints exactly what its siblings print.
"""
from __future__ import annotations

import textwrap


def _content(source: str) -> str:
    return textwrap.dedent(source).strip() + "\n"


_APPEND = """
static int append(char *out, size_t cap, int used, const char *fmt, ...) {
    va_list args;
    int written;
    if (used < 0 || (size_t)used >= cap) {
        return (int)cap - 1;
    }
    va_start(args, fmt);
    written = vsnprintf(out + used, cap - (size_t)used, fmt, args);
    va_end(args);
    if (written < 0) {
        return used;
    }
    if ((size_t)(used + written) >= cap) {
        return (int)cap - 1;
    }
    return used + written;
}
"""


def _binary_search() -> dict:
    return {
        "title": "c cli set — binary search trace",
        "description": "Prints every probe a binary search makes against a sorted list, "
                       "then the index it found or a not-found line.",
        "family": "binary-search-trace",
        "target": "search.c",
        "files": [
            {"path": "main.c", "content": _content("""
                #include <stdio.h>

                #include "search.h"
                #include "report.h"

                int main(void) {
                    int values[] = {2, 4, 6, 8, 10, 12, 14};
                    int targets[] = {8, 5};
                    char out[1024];
                    search_trace(values, 7, targets, 2, out, sizeof(out));
                    report_text(out);
                    return 0;
                }
            """)},
            {"path": "search.h", "content": _content("""
                #ifndef SEARCH_H
                #define SEARCH_H

                #include <stddef.h>

                int search_trace(const int *values, int count, const int *targets,
                                 int target_count, char *out, size_t cap);

                #endif
            """)},
            {"path": "search.c", "content": _content("""
                #include <stdarg.h>
                #include <stdio.h>

                #include "search.h"
            """ + _APPEND + """
                int search_trace(const int *values, int count, const int *targets,
                                 int target_count, char *out, size_t cap) {
                    int used = 0;
                    int t;
                    for (t = 0; t < target_count; t++) {
                        int lo = 0;
                        int hi = count - 1;
                        int found = -1;
                        used = append(out, cap, used, "search %d\\n", targets[t]);
                        while (lo <= hi) {
                            int mid = lo + (hi - lo) / 2;
                            used = append(out, cap, used, "probe %d value %d\\n",
                                          mid, values[mid]);
                            if (values[mid] == targets[t]) {
                                found = mid;
                                break;
                            }
                            if (values[mid] < targets[t]) {
                                lo = mid + 1;
                            } else {
                                hi = mid - 1;
                            }
                        }
                        if (found < 0) {
                            used = append(out, cap, used, "not found %d\\n", targets[t]);
                        } else {
                            used = append(out, cap, used, "found %d at index %d\\n",
                                          targets[t], found);
                        }
                    }
                    out[used] = '\\0';
                    return used;
                }
            """)},
            {"path": "report.h", "content": _content("""
                #ifndef REPORT_H
                #define REPORT_H

                void report_text(const char *text);

                #endif
            """)},
            {"path": "report.c", "content": _content("""
                #include <stdio.h>

                #include "report.h"

                void report_text(const char *text) {
                    fputs(text, stdout);
                }
            """)},
        ],
    }


def _lru_cache() -> dict:
    return {
        "title": "c cli set — lru cache simulation",
        "description": "Runs a six-operation sequence through a capacity-two LRU cache "
                       "and prints each hit, miss, insert and eviction.",
        "family": "lru-cache-simulation",
        "target": "cache.c",
        "files": [
            {"path": "main.c", "content": _content("""
                #include <stdio.h>

                #include "cache.h"
                #include "report.h"

                int main(void) {
                    Op ops[] = {
                        {"get", "a"},
                        {"put", "b"},
                        {"get", "a"},
                        {"put", "c"},
                        {"get", "b"},
                        {"get", "a"},
                    };
                    char out[1024];
                    cache_play(ops, 6, 2, out, sizeof(out));
                    report_text(out);
                    return 0;
                }
            """)},
            {"path": "cache.h", "content": _content("""
                #ifndef CACHE_H
                #define CACHE_H

                #include <stddef.h>

                typedef struct {
                    const char *kind;
                    const char *key;
                } Op;

                int cache_play(const Op *ops, int count, int capacity,
                               char *out, size_t cap);

                #endif
            """)},
            {"path": "cache.c", "content": _content("""
                #include <stdarg.h>
                #include <stdio.h>
                #include <string.h>

                #include "cache.h"
            """ + _APPEND + """
                int cache_play(const Op *ops, int count, int capacity,
                               char *out, size_t cap) {
                    const char *keys[8];
                    int used_at[8];
                    int size = 0;
                    int clock = 0;
                    int used = 0;
                    int i;
                    if (capacity > 8) {
                        capacity = 8;
                    }
                    for (i = 0; i < count; i++) {
                        int index = -1;
                        int slot;
                        clock++;
                        for (slot = 0; slot < size; slot++) {
                            if (strcmp(keys[slot], ops[i].key) == 0) {
                                index = slot;
                                break;
                            }
                        }
                        if (strcmp(ops[i].kind, "get") == 0) {
                            if (index >= 0) {
                                used_at[index] = clock;
                                used = append(out, cap, used, "get %s hit\\n", ops[i].key);
                                continue;
                            }
                            used = append(out, cap, used, "get %s miss\\n", ops[i].key);
                            if (size < capacity) {
                                keys[size] = ops[i].key;
                                used_at[size] = clock;
                                size++;
                            }
                            continue;
                        }
                        if (index >= 0) {
                            used_at[index] = clock;
                            used = append(out, cap, used, "put %s\\n", ops[i].key);
                            continue;
                        }
                        if (size < capacity) {
                            keys[size] = ops[i].key;
                            used_at[size] = clock;
                            size++;
                            used = append(out, cap, used, "put %s\\n", ops[i].key);
                            continue;
                        }
                        {
                            int oldest = 0;
                            for (slot = 1; slot < size; slot++) {
                                if (used_at[slot] < used_at[oldest]) {
                                    oldest = slot;
                                }
                            }
                            used = append(out, cap, used, "put %s evict %s\\n",
                                          ops[i].key, keys[oldest]);
                            keys[oldest] = ops[i].key;
                            used_at[oldest] = clock;
                        }
                    }
                    out[used] = '\\0';
                    return used;
                }
            """)},
            {"path": "report.h", "content": _content("""
                #ifndef REPORT_H
                #define REPORT_H

                void report_text(const char *text);

                #endif
            """)},
            {"path": "report.c", "content": _content("""
                #include <stdio.h>

                #include "report.h"

                void report_text(const char *text) {
                    fputs(text, stdout);
                }
            """)},
        ],
    }


def _isbn() -> dict:
    return {
        "title": "c cli set — isbn checksum",
        "description": "Recomputes the ISBN-10 check digit for two codes and reports "
                       "each one as valid or invalid.",
        "family": "isbn-checksum",
        "target": "isbn.c",
        "files": [
            {"path": "main.c", "content": _content("""
                #include <stdio.h>

                #include "isbn.h"
                #include "report.h"

                int main(void) {
                    const char *codes[] = {"0306406152", "0306406153"};
                    char out[512];
                    report_isbn(codes, 2, out, sizeof(out));
                    report_text(out);
                    return 0;
                }
            """)},
            {"path": "isbn.h", "content": _content("""
                #ifndef ISBN_H
                #define ISBN_H

                int isbn_expected(const char *code);
                int isbn_valid(const char *code);

                #endif
            """)},
            {"path": "isbn.c", "content": _content("""
                #include "isbn.h"

                int isbn_expected(const char *code) {
                    int sum = 0;
                    int i;
                    for (i = 0; i < 9; i++) {
                        sum += (code[i] - '0') * (10 - i);
                    }
                    return (11 - sum % 11) % 11;
                }

                int isbn_valid(const char *code) {
                    int expected = isbn_expected(code);
                    char last = code[9];
                    if (last == 'X') {
                        return expected == 10;
                    }
                    return expected == last - '0';
                }
            """)},
            {"path": "report.h", "content": _content("""
                #ifndef REPORT_H
                #define REPORT_H

                #include <stddef.h>

                void report_text(const char *text);
                int report_isbn(const char *const *codes, int count,
                                char *out, size_t cap);

                #endif
            """)},
            {"path": "report.c", "content": _content("""
                #include <stdarg.h>
                #include <stdio.h>

                #include "isbn.h"
                #include "report.h"
            """ + _APPEND + """
                void report_text(const char *text) {
                    fputs(text, stdout);
                }

                int report_isbn(const char *const *codes, int count,
                                char *out, size_t cap) {
                    int used = 0;
                    int i;
                    for (i = 0; i < count; i++) {
                        int expected = isbn_expected(codes[i]);
                        char digit[4];
                        if (expected == 10) {
                            snprintf(digit, sizeof(digit), "X");
                        } else {
                            snprintf(digit, sizeof(digit), "%d", expected);
                        }
                        used = append(out, cap, used, "%s %s check %s\\n", codes[i],
                                      isbn_valid(codes[i]) ? "valid" : "invalid", digit);
                    }
                    out[used] = '\\0';
                    return used;
                }
            """)},
        ],
    }


def _vending() -> dict:
    return {
        "title": "c cli set — vending change",
        "description": "Breaks the change for two purchases into the fewest coins "
                       "from a 50/25/20/10 set and prints the count of each.",
        "family": "vending-change",
        "target": "vending.c",
        "files": [
            {"path": "main.c", "content": _content("""
                #include <stdio.h>

                #include "vending.h"
                #include "report.h"

                int main(void) {
                    Purchase purchases[] = {{65, 100}, {130, 200}};
                    char out[1024];
                    change_report(purchases, 2, out, sizeof(out));
                    report_text(out);
                    return 0;
                }
            """)},
            {"path": "vending.h", "content": _content("""
                #ifndef VENDING_H
                #define VENDING_H

                #include <stddef.h>

                typedef struct {
                    int price;
                    int paid;
                } Purchase;

                int change( int price, int paid, char *out, size_t cap);

                #endif
            """)},
            {"path": "vending.c", "content": _content("""
                #include <stdarg.h>
                #include <stdio.h>

                #include "vending.h"

                static const int COINS[] = {50, 25, 20, 10};
            """ + _APPEND + """
                int change(int price, int paid, char *out, size_t cap) {
                    int used = 0;
                    int rest = paid - price;
                    int i;
                    used = append(out, cap, used, "price %d paid %d change %d\\n",
                                  price, paid, paid - price);
                    for (i = 0; i < 4; i++) {
                        int count = rest / COINS[i];
                        if (count == 0) {
                            continue;
                        }
                        rest -= count * COINS[i];
                        used = append(out, cap, used, "%d x %d\\n", count, COINS[i]);
                    }
                    if (rest != 0) {
                        used = append(out, cap, used, "leftover %d\\n", rest);
                    }
                    out[used] = '\\0';
                    return used;
                }
            """)},
            {"path": "report.h", "content": _content("""
                #ifndef REPORT_H
                #define REPORT_H

                #include <stddef.h>

                #include "vending.h"

                void report_text(const char *text);
                int change_report(const Purchase *items, int count,
                                  char *out, size_t cap);

                #endif
            """)},
            {"path": "report.c", "content": _content("""
                #include <stdio.h>
                #include <string.h>

                #include "report.h"

                void report_text(const char *text) {
                    fputs(text, stdout);
                }

                int change_report(const Purchase *items, int count,
                                  char *out, size_t cap) {
                    int used = 0;
                    int i;
                    for (i = 0; i < count; i++) {
                        char block[256];
                        int written = change(items[i].price, items[i].paid,
                                             block, sizeof(block));
                        if (written < 0 || (size_t)written >= sizeof(block)) {
                            written = (int)sizeof(block) - 1;
                        }
                        if ((size_t)(used + written) >= cap) {
                            written = (int)cap - 1 - used;
                        }
                        if (written > 0) {
                            memcpy(out + used, block, (size_t)written);
                            used += written;
                        }
                    }
                    out[used] = '\\0';
                    return used;
                }
            """)},
        ],
    }


def _life() -> dict:
    return {
        "title": "c cli set — game of life step",
        "description": "Applies one Conway step to a 4x4 grid with a three-cell "
                       "vertical blinker and prints the rows and the live count.",
        "family": "game-of-life-step",
        "target": "life.c",
        "files": [
            {"path": "main.c", "content": _content("""
                #include <stdio.h>

                #include "life.h"
                #include "report.h"

                int main(void) {
                    int grid[4][4] = {{0, 1, 0, 0},
                                      {0, 1, 0, 0},
                                      {0, 1, 0, 0},
                                      {0, 0, 0, 0}};
                    int next[4][4];
                    char out[512];
                    life_step(grid, next);
                    report_life(next, out, sizeof(out));
                    report_text(out);
                    return 0;
                }
            """)},
            {"path": "life.h", "content": _content("""
                #ifndef LIFE_H
                #define LIFE_H

                void life_step(const int grid[4][4], int next[4][4]);

                #endif
            """)},
            {"path": "life.c", "content": _content("""
                #include "life.h"

                void life_step(const int grid[4][4], int next[4][4]) {
                    int row;
                    int col;
                    for (row = 0; row < 4; row++) {
                        for (col = 0; col < 4; col++) {
                            int live = 0;
                            int dr;
                            int dc;
                            for (dr = -1; dr <= 1; dr++) {
                                for (dc = -1; dc <= 1; dc++) {
                                    int r;
                                    int c;
                                    if (dr == 0 && dc == 0) {
                                        continue;
                                    }
                                    r = row + dr;
                                    c = col + dc;
                                    if (r < 0 || c < 0 || r >= 4 || c >= 4) {
                                        continue;
                                    }
                                    if (grid[r][c]) {
                                        live++;
                                    }
                                }
                            }
                            if (grid[row][col]) {
                                next[row][col] = (live == 2 || live == 3);
                            } else {
                                next[row][col] = (live == 3);
                            }
                        }
                    }
                }
            """)},
            {"path": "report.h", "content": _content("""
                #ifndef REPORT_H
                #define REPORT_H

                #include <stddef.h>

                void report_text(const char *text);
                int report_life(const int grid[4][4], char *out, size_t cap);

                #endif
            """)},
            {"path": "report.c", "content": _content("""
                #include <stdarg.h>
                #include <stdio.h>

                #include "report.h"
            """ + _APPEND + """
                void report_text(const char *text) {
                    fputs(text, stdout);
                }

                int report_life(const int grid[4][4], char *out, size_t cap) {
                    int used = 0;
                    int live = 0;
                    int row;
                    int col;
                    for (row = 0; row < 4; row++) {
                        used = append(out, cap, used, "row ");
                        for (col = 0; col < 4; col++) {
                            if (grid[row][col]) {
                                used = append(out, cap, used, "1");
                                live++;
                            } else {
                                used = append(out, cap, used, "0");
                            }
                        }
                        used = append(out, cap, used, "\\n");
                    }
                    used = append(out, cap, used, "live %d\\n", live);
                    out[used] = '\\0';
                    return used;
                }
            """)},
        ],
    }


def sets() -> list[dict]:
    return [_binary_search(), _lru_cache(), _isbn(), _vending(), _life()]
