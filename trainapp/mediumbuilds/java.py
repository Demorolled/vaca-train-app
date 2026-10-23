"""Java medium builds — five multi-function templates, twenty variants each."""
from __future__ import annotations

from .data import LEDGERS, MATRICES, RECORDS, STACK_OPS, TEXTS

LANGUAGE = "java"


def _word_freq(text: str) -> str:
    return f"""import java.util.*;

public class WordFreq {{
    static List<String> tokens(String text) {{
        List<String> out = new ArrayList<>();
        for (String word : text.split("\\\\s+")) {{
            if (!word.isEmpty()) out.add(word);
        }}
        return out;
    }}

    static Map<String, Integer> counts(List<String> words) {{
        Map<String, Integer> table = new HashMap<>();
        for (String word : words) table.merge(word, 1, Integer::sum);
        return table;
    }}

    static List<Map.Entry<String, Integer>> ranked(Map<String, Integer> table) {{
        List<Map.Entry<String, Integer>> rows = new ArrayList<>(table.entrySet());
        rows.sort((a, b) -> a.getValue().equals(b.getValue())
                ? a.getKey().compareTo(b.getKey())
                : b.getValue() - a.getValue());
        return rows;
    }}

    public static void main(String[] args) {{
        String text = "{text}";
        List<Map.Entry<String, Integer>> rows = ranked(counts(tokens(text)));
        for (int i = 0; i < rows.size() && i < 4; i++) {{
            System.out.println(rows.get(i).getKey() + ": " + rows.get(i).getValue());
        }}
    }}
}}
"""


def _inventory(records: tuple) -> str:
    items = ",\n".join(f'            new Item("{name}", {qty}, {price})'
                       for name, qty, price in records)
    return f"""import java.util.*;

public class Inventory {{
    static class Item {{
        final String name;
        final int qty;
        final double price;

        Item(String name, int qty, double price) {{
            this.name = name;
            this.qty = qty;
            this.price = price;
        }}
    }}

    static List<Item> available(List<Item> stock) {{
        List<Item> out = new ArrayList<>();
        for (Item item : stock) {{
            if (item.qty > 0) out.add(item);
        }}
        return out;
    }}

    static double totalValue(List<Item> rows) {{
        double sum = 0.0;
        for (Item row : rows) sum += row.qty * row.price;
        return sum;
    }}

    static void render(List<Item> rows) {{
        for (Item row : rows) {{
            System.out.printf("%-8s %3d x %6.2f = %8.2f%n",
                    row.name, row.qty, row.price, row.qty * row.price);
        }}
    }}

    public static void main(String[] args) {{
        List<Item> stock = List.of(
{items}
        );
        List<Item> rows = available(stock);
        render(rows);
        System.out.printf("total %.2f%n", totalValue(rows));
    }}
}}
"""


def _matrix(matrix: tuple) -> str:
    rows = "\n".join("            {" + ", ".join(str(v) for v in row) + "}," for row in matrix)
    return f"""public class MatrixOps {{
    static int[][] transpose(int[][] m) {{
        int size = m.length;
        int[][] out = new int[size][size];
        for (int r = 0; r < size; r++) {{
            for (int c = 0; c < size; c++) out[c][r] = m[r][c];
        }}
        return out;
    }}

    static int[] rowSums(int[][] m) {{
        int[] sums = new int[m.length];
        for (int r = 0; r < m.length; r++) {{
            for (int value : m[r]) sums[r] += value;
        }}
        return sums;
    }}

    static void render(int[][] m) {{
        for (int[] row : m) {{
            StringBuilder line = new StringBuilder();
            for (int value : row) line.append(String.format("%4d", value));
            System.out.println(line);
        }}
    }}

    public static void main(String[] args) {{
        int[][] m = {{
{rows}
        }};
        render(transpose(m));
        int[] sums = rowSums(m);
        System.out.println("sums " + sums[0] + " " + sums[1] + " " + sums[2]);
    }}
}}
"""


def _stack(ops: tuple) -> str:
    calls = ",\n".join(f'            "{op}"' for op in ops)
    return f"""import java.util.*;

public class StackGame {{
    static class Stack {{
        private final List<Integer> items = new ArrayList<>();

        void push(int value) {{ items.add(value); }}

        Integer pop() {{
            return items.isEmpty() ? null : items.remove(items.size() - 1);
        }}

        Integer peek() {{
            return items.isEmpty() ? null : items.get(items.size() - 1);
        }}
    }}

    static List<String> run(Stack stack, List<String> ops) {{
        List<String> out = new ArrayList<>();
        for (String op : ops) {{
            String[] parts = op.split(" ");
            switch (parts[0]) {{
                case "push" -> {{
                    stack.push(Integer.parseInt(parts[1]));
                    out.add("push " + parts[1]);
                }}
                case "pop" -> {{
                    Integer value = stack.pop();
                    out.add(value == null ? "pop none" : "pop " + value);
                }}
                default -> {{
                    Integer value = stack.peek();
                    out.add(value == null ? "peek none" : "peek " + value);
                }}
            }}
        }}
        return out;
    }}

    public static void main(String[] args) {{
        List<String> ops = List.of(
{calls}
        );
        for (String line : run(new Stack(), ops)) System.out.println(line);
    }}
}}
"""


def _bank(ledger: tuple) -> str:
    calls = ",\n".join(f'            new String[]{{"{kind}", "{amount}"}}'
                      for kind, amount in ledger)
    return f"""import java.util.*;

public class BankLedger {{
    static class Account {{
        int balance;
        final List<String[]> log = new ArrayList<>();

        Account(int opening) {{ this.balance = opening; }}

        void deposit(int amount) {{
            balance += amount;
            log.add(new String[]{{"deposit", String.valueOf(amount), String.valueOf(balance)}});
        }}

        boolean withdraw(int amount) {{
            if (amount > balance) {{
                log.add(new String[]{{"refused", String.valueOf(amount), String.valueOf(balance)}});
                return false;
            }}
            balance -= amount;
            log.add(new String[]{{"withdraw", String.valueOf(amount), String.valueOf(balance)}});
            return true;
        }}
    }}

    public static void main(String[] args) {{
        List<String[]> ops = List.of(
{calls}
        );
        int opening = Integer.parseInt(ops.get(0)[1]);
        Account account = new Account(opening);
        account.log.add(new String[]{{"open", String.valueOf(opening), String.valueOf(opening)}});
        for (int i = 1; i < ops.size(); i++) {{
            String kind = ops.get(i)[0];
            int amount = Integer.parseInt(ops.get(i)[1]);
            if (kind.equals("deposit")) account.deposit(amount);
            else account.withdraw(amount);
        }}
        for (String[] row : account.log) {{
            System.out.printf("%-9s %4s -> %4s%n", row[0], row[1], row[2]);
        }}
    }}
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
