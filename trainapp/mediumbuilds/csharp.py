"""C# medium builds — five multi-function templates, twenty variants each."""
from __future__ import annotations

from .data import LEDGERS, MATRICES, RECORDS, STACK_OPS, TEXTS

LANGUAGE = "csharp"


def _word_freq(text: str) -> str:
    return f"""using System;
using System.Collections.Generic;
using System.Linq;

class WordFreq
{{
    static List<string> Tokens(string text) =>
        text.Split(' ', StringSplitOptions.RemoveEmptyEntries).ToList();

    static Dictionary<string, int> Counts(List<string> words)
    {{
        var table = new Dictionary<string, int>();
        foreach (var word in words)
            table[word] = table.TryGetValue(word, out var n) ? n + 1 : 1;
        return table;
    }}

    static List<KeyValuePair<string, int>> Ranked(Dictionary<string, int> table) =>
        table.OrderByDescending(pair => pair.Value)
             .ThenBy(pair => pair.Key, StringComparer.Ordinal)
             .ToList();

    static void Main()
    {{
        var text = "{text}";
        foreach (var row in Ranked(Counts(Tokens(text))).Take(4))
            Console.WriteLine($"{{row.Key}}: {{row.Value}}");
    }}
}}
"""


def _inventory(records: tuple) -> str:
    items = "\n".join(f'            ("{name}", {qty}, {price}),' for name, qty, price in records)
    return f"""using System;
using System.Collections.Generic;
using System.Linq;

class Inventory
{{
    static List<(string Name, int Qty, double Price)> Available(
        List<(string Name, int Qty, double Price)> stock) =>
        stock.Where(item => item.Qty > 0).ToList();

    static double TotalValue(List<(string Name, int Qty, double Price)> rows) =>
        rows.Sum(row => row.Qty * row.Price);

    static void Render(List<(string Name, int Qty, double Price)> rows)
    {{
        foreach (var row in rows)
            Console.WriteLine($"{{row.Name,-8}} {{row.Qty,3}} x {{row.Price,6:F2}} = {{row.Qty * row.Price,8:F2}}");
    }}

    static void Main()
    {{
        var stock = new List<(string, int, double)>
        {{
{items}
        }};
        var rows = Available(stock);
        Render(rows);
        Console.WriteLine($"total {{TotalValue(rows):F2}}");
    }}
}}
"""


def _matrix(matrix: tuple) -> str:
    rows = "\n".join("            { " + ", ".join(str(v) for v in row) + " }," for row in matrix)
    return f"""using System;

class MatrixOps
{{
    static int[,] Transpose(int[,] m)
    {{
        int size = m.GetLength(0);
        var outm = new int[size, size];
        for (int r = 0; r < size; r++)
            for (int c = 0; c < size; c++)
                outm[c, r] = m[r, c];
        return outm;
    }}

    static int[] RowSums(int[,] m)
    {{
        int size = m.GetLength(0);
        var sums = new int[size];
        for (int r = 0; r < size; r++)
            for (int c = 0; c < size; c++)
                sums[r] += m[r, c];
        return sums;
    }}

    static void Render(int[,] m)
    {{
        int size = m.GetLength(0);
        for (int r = 0; r < size; r++)
        {{
            var line = "";
            for (int c = 0; c < size; c++) line += $"{{m[r, c],4}}";
            Console.WriteLine(line);
        }}
    }}

    static void Main()
    {{
        int[,] m = {{
{rows}
        }};
        Render(Transpose(m));
        var sums = RowSums(m);
        Console.WriteLine($"sums {{sums[0]}} {{sums[1]}} {{sums[2]}}");
    }}
}}
"""


def _stack(ops: tuple) -> str:
    calls = "\n".join(f'            "{op}",' for op in ops)
    return f"""using System;
using System.Collections.Generic;

class StackGame
{{
    class Stack
    {{
        private readonly List<int> items = new List<int>();

        public void Push(int value) => items.Add(value);

        public int? Pop()
        {{
            if (items.Count == 0) return null;
            int value = items[^1];
            items.RemoveAt(items.Count - 1);
            return value;
        }}

        public int? Peek() => items.Count == 0 ? null : items[^1];
    }}

    static List<string> Run(Stack stack, List<string> ops)
    {{
        var output = new List<string>();
        foreach (var op in ops)
        {{
            var parts = op.Split(' ');
            if (parts[0] == "push")
            {{
                int value = int.Parse(parts[1]);
                stack.Push(value);
                output.Add($"push {{value}}");
            }}
            else if (parts[0] == "pop")
            {{
                var value = stack.Pop();
                output.Add(value is null ? "pop none" : $"pop {{value}}");
            }}
            else
            {{
                var value = stack.Peek();
                output.Add(value is null ? "peek none" : $"peek {{value}}");
            }}
        }}
        return output;
    }}

    static void Main()
    {{
        var ops = new List<string>
        {{
{calls}
        }};
        foreach (var line in Run(new Stack(), ops)) Console.WriteLine(line);
    }}
}}
"""


def _bank(ledger: tuple) -> str:
    calls = "\n".join(f'            ("{kind}", {amount}),' for kind, amount in ledger)
    return f"""using System;
using System.Collections.Generic;

class BankLedger
{{
    class Account
    {{
        public int Balance {{ get; private set; }}
        public List<(string Kind, int Amount, int Balance)> Log {{ get; }} =
            new List<(string, int, int)>();

        public Account(int opening) {{ Balance = opening; }}

        public void Deposit(int amount)
        {{
            Balance += amount;
            Log.Add(("deposit", amount, Balance));
        }}

        public bool Withdraw(int amount)
        {{
            if (amount > Balance)
            {{
                Log.Add(("refused", amount, Balance));
                return false;
            }}
            Balance -= amount;
            Log.Add(("withdraw", amount, Balance));
            return true;
        }}
    }}

    static List<(string Kind, int Amount, int Balance)> Run(
        List<(string Kind, int Amount)> ops)
    {{
        var account = new Account(ops[0].Amount);
        account.Log.Add(("open", ops[0].Amount, ops[0].Amount));
        for (int i = 1; i < ops.Count; i++)
        {{
            if (ops[i].Kind == "deposit") account.Deposit(ops[i].Amount);
            else account.Withdraw(ops[i].Amount);
        }}
        return account.Log;
    }}

    static void Main()
    {{
        var ops = new List<(string, int)>
        {{
{calls}
        }};
        foreach (var row in Run(ops))
            Console.WriteLine($"{{row.Kind,-9}} {{row.Amount,4}} -> {{row.Balance,4}}");
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
