"""java.py — the five family programs, in Java.

These are the siblings that keep a family measurable now that the corpus is
scoped to five lanes: each program already exists in JavaScript, Python and Go,
and a family needs two in-focus sets before its score means anything.

The layout follows the one the toolchain requires rather than the one that looks
tidy: the entry file is `main.java` (the set schema only recognises `main`,
`index` or `app` as entries), which javac accepts because `Main` is not public.
Everything is in the default package, so `javac -d .out *.java` followed by
`java -cp .out Main` runs it.

Each set prints exactly what its siblings print — the family is one program, and
the byte-for-byte contract is what makes a sibling a sibling.
"""
from __future__ import annotations

import textwrap


def _content(source: str) -> str:
    return textwrap.dedent(source).strip() + "\n"


def _binary_search() -> dict:
    return {
        "title": "java cli set — binary search trace",
        "description": "Prints every probe a binary search makes against a sorted list, "
                       "then the index it found or a not-found line.",
        "family": "binary-search-trace",
        "target": "Search.java",
        "files": [
            {"path": "main.java", "content": _content("""
                class Main {
                    public static void main(String[] args) {
                        int[] values = {2, 4, 6, 8, 10, 12, 14};
                        int[] targets = {8, 5};
                        System.out.print(Report.join(Search.trace(values, targets)));
                    }
                }
            """)},
            {"path": "Search.java", "content": _content("""
                import java.util.ArrayList;
                import java.util.List;

                public class Search {
                    public static List<String> trace(int[] values, int[] targets) {
                        List<String> lines = new ArrayList<String>();
                        for (int target : targets) {
                            lines.add("search " + target);
                            int lo = 0;
                            int hi = values.length - 1;
                            int found = -1;
                            while (lo <= hi) {
                                int mid = lo + (hi - lo) / 2;
                                lines.add("probe " + mid + " value " + values[mid]);
                                if (values[mid] == target) {
                                    found = mid;
                                    break;
                                }
                                if (values[mid] < target) {
                                    lo = mid + 1;
                                } else {
                                    hi = mid - 1;
                                }
                            }
                            if (found < 0) {
                                lines.add("not found " + target);
                            } else {
                                lines.add("found " + target + " at index " + found);
                            }
                        }
                        return lines;
                    }
                }
            """)},
            {"path": "Report.java", "content": _content("""
                import java.util.List;

                public class Report {
                    public static String join(List<String> lines) {
                        StringBuilder out = new StringBuilder();
                        for (String line : lines) {
                            out.append(line).append('\\n');
                        }
                        return out.toString();
                    }
                }
            """)},
        ],
    }


def _lru_cache() -> dict:
    return {
        "title": "java cli set — lru cache simulation",
        "description": "Runs a six-operation sequence through a capacity-two LRU cache "
                       "and prints each hit, miss, insert and eviction.",
        "family": "lru-cache-simulation",
        "target": "Cache.java",
        "files": [
            {"path": "main.java", "content": _content("""
                class Main {
                    public static void main(String[] args) {
                        Cache.Op[] ops = {
                            new Cache.Op("get", "a"),
                            new Cache.Op("put", "b"),
                            new Cache.Op("get", "a"),
                            new Cache.Op("put", "c"),
                            new Cache.Op("get", "b"),
                            new Cache.Op("get", "a"),
                        };
                        System.out.print(Report.join(Cache.play(ops, 2)));
                    }
                }
            """)},
            {"path": "Cache.java", "content": _content("""
                import java.util.ArrayList;
                import java.util.List;

                public class Cache {
                    public static class Op {
                        public final String kind;
                        public final String key;

                        public Op(String kind, String key) {
                            this.kind = kind;
                            this.key = key;
                        }
                    }

                    public static List<String> play(Op[] ops, int capacity) {
                        List<String> lines = new ArrayList<String>();
                        List<String> keys = new ArrayList<String>();
                        List<Integer> used = new ArrayList<Integer>();
                        int clock = 0;
                        for (Op op : ops) {
                            clock++;
                            int index = keys.indexOf(op.key);
                            if (op.kind.equals("get")) {
                                if (index >= 0) {
                                    used.set(index, clock);
                                    lines.add("get " + op.key + " hit");
                                    continue;
                                }
                                lines.add("get " + op.key + " miss");
                                if (keys.size() < capacity) {
                                    keys.add(op.key);
                                    used.add(clock);
                                }
                                continue;
                            }
                            if (index >= 0) {
                                used.set(index, clock);
                                lines.add("put " + op.key);
                                continue;
                            }
                            if (keys.size() < capacity) {
                                keys.add(op.key);
                                used.add(clock);
                                lines.add("put " + op.key);
                                continue;
                            }
                            int oldest = 0;
                            for (int i = 1; i < used.size(); i++) {
                                if (used.get(i) < used.get(oldest)) {
                                    oldest = i;
                                }
                            }
                            lines.add("put " + op.key + " evict " + keys.get(oldest));
                            keys.set(oldest, op.key);
                            used.set(oldest, clock);
                        }
                        return lines;
                    }
                }
            """)},
            {"path": "Report.java", "content": _content("""
                import java.util.List;

                public class Report {
                    public static String join(List<String> lines) {
                        StringBuilder out = new StringBuilder();
                        for (String line : lines) {
                            out.append(line).append('\\n');
                        }
                        return out.toString();
                    }
                }
            """)},
        ],
    }


def _isbn() -> dict:
    return {
        "title": "java cli set — isbn checksum",
        "description": "Recomputes the ISBN-10 check digit for two codes and reports "
                       "each one as valid or invalid.",
        "family": "isbn-checksum",
        "target": "Isbn.java",
        "files": [
            {"path": "main.java", "content": _content("""
                class Main {
                    public static void main(String[] args) {
                        String[] codes = {"0306406152", "0306406153"};
                        System.out.print(Report.isbn(codes));
                    }
                }
            """)},
            {"path": "Isbn.java", "content": _content("""
                public class Isbn {
                    public static int expected(String code) {
                        int sum = 0;
                        for (int i = 0; i < 9; i++) {
                            sum += (code.charAt(i) - '0') * (10 - i);
                        }
                        return (11 - sum % 11) % 11;
                    }

                    public static boolean valid(String code) {
                        int expected = expected(code);
                        char last = code.charAt(9);
                        if (last == 'X') {
                            return expected == 10;
                        }
                        return expected == last - '0';
                    }
                }
            """)},
            {"path": "Report.java", "content": _content("""
                public class Report {
                    public static String isbn(String[] codes) {
                        StringBuilder out = new StringBuilder();
                        for (String code : codes) {
                            String status = Isbn.valid(code) ? "valid" : "invalid";
                            int expected = Isbn.expected(code);
                            String digit = expected == 10 ? "X" : Integer.toString(expected);
                            out.append(code).append(' ')
                               .append(status).append(" check ")
                               .append(digit).append('\\n');
                        }
                        return out.toString();
                    }
                }
            """)},
        ],
    }


def _vending() -> dict:
    return {
        "title": "java cli set — vending change",
        "description": "Breaks the change for two purchases into the fewest coins "
                       "from a 50/25/20/10 set and prints the count of each.",
        "family": "vending-change",
        "target": "Vending.java",
        "files": [
            {"path": "main.java", "content": _content("""
                class Main {
                    public static void main(String[] args) {
                        Vending.Purchase[] purchases = {
                            new Vending.Purchase(65, 100),
                            new Vending.Purchase(130, 200),
                        };
                        System.out.print(Report.change(purchases));
                    }
                }
            """)},
            {"path": "Vending.java", "content": _content("""
                import java.util.ArrayList;
                import java.util.List;

                public class Vending {
                    public static final int[] COINS = {50, 25, 20, 10};

                    public static class Purchase {
                        public final int price;
                        public final int paid;

                        public Purchase(int price, int paid) {
                            this.price = price;
                            this.paid = paid;
                        }
                    }

                    public static List<String> change(int price, int paid) {
                        List<String> lines = new ArrayList<String>();
                        lines.add("price " + price + " paid " + paid
                                  + " change " + (paid - price));
                        int rest = paid - price;
                        for (int coin : COINS) {
                            int count = rest / coin;
                            if (count == 0) {
                                continue;
                            }
                            rest -= count * coin;
                            lines.add(count + " x " + coin);
                        }
                        if (rest != 0) {
                            lines.add("leftover " + rest);
                        }
                        return lines;
                    }
                }
            """)},
            {"path": "Report.java", "content": _content("""
                import java.util.List;

                public class Report {
                    public static String change(Vending.Purchase[] purchases) {
                        StringBuilder out = new StringBuilder();
                        for (Vending.Purchase purchase : purchases) {
                            for (String line : Vending.change(purchase.price, purchase.paid)) {
                                out.append(line).append('\\n');
                            }
                        }
                        return out.toString();
                    }
                }
            """)},
        ],
    }


def _life() -> dict:
    return {
        "title": "java cli set — game of life step",
        "description": "Applies one Conway step to a 4x4 grid with a three-cell "
                       "vertical blinker and prints the rows and the live count.",
        "family": "game-of-life-step",
        "target": "Life.java",
        "files": [
            {"path": "main.java", "content": _content("""
                class Main {
                    public static void main(String[] args) {
                        boolean[][] grid = new boolean[4][4];
                        grid[0][1] = true;
                        grid[1][1] = true;
                        grid[2][1] = true;
                        System.out.print(Report.life(Life.step(grid)));
                    }
                }
            """)},
            {"path": "Life.java", "content": _content("""
                public class Life {
                    public static boolean[][] step(boolean[][] grid) {
                        int rows = grid.length;
                        int cols = grid[0].length;
                        boolean[][] next = new boolean[rows][cols];
                        for (int row = 0; row < rows; row++) {
                            for (int col = 0; col < cols; col++) {
                                int live = 0;
                                for (int dr = -1; dr <= 1; dr++) {
                                    for (int dc = -1; dc <= 1; dc++) {
                                        if (dr == 0 && dc == 0) {
                                            continue;
                                        }
                                        int r = row + dr;
                                        int c = col + dc;
                                        if (r < 0 || c < 0 || r >= rows || c >= cols) {
                                            continue;
                                        }
                                        if (grid[r][c]) {
                                            live++;
                                        }
                                    }
                                }
                                if (grid[row][col]) {
                                    next[row][col] = live == 2 || live == 3;
                                } else {
                                    next[row][col] = live == 3;
                                }
                            }
                        }
                        return next;
                    }
                }
            """)},
            {"path": "Report.java", "content": _content("""
                public class Report {
                    public static String life(boolean[][] grid) {
                        StringBuilder out = new StringBuilder();
                        int live = 0;
                        for (boolean[] row : grid) {
                            out.append("row ");
                            for (boolean cell : row) {
                                if (cell) {
                                    out.append('1');
                                    live++;
                                } else {
                                    out.append('0');
                                }
                            }
                            out.append('\\n');
                        }
                        out.append("live ").append(live).append('\\n');
                        return out.toString();
                    }
                }
            """)},
        ],
    }


def sets() -> list[dict]:
    return [_binary_search(), _lru_cache(), _isbn(), _vending(), _life()]
