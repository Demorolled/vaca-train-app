"""python cli sets — three-file programs whose report is the behaviour.

Each set is an entry point, a formatter, and a target module that turns embedded
data into a deterministic report. Standard library only, no input, no clock: the
same contract as the base builds, across files.
"""
from __future__ import annotations

import textwrap


INVOICE_INVENTORY = textwrap.dedent("""\
    # Invoice lines and the totals they add up to.

    LINES = [
        ("bolt", 12, 240),
        ("gasket", 4, 1250),
        ("housing", 2, 8900),
        ("washer", 40, 15),
        ("shaft", 3, 4200),
    ]


    def line_total(quantity, unit_cents):
        return quantity * unit_cents


    def tax_rate(cents):
        if cents >= 20000:
            return 8
        if cents >= 8000:
            return 5
        return 0


    def summarise(lines):
        subtotal = 0
        tax = 0
        taxed = 0
        bands = {}
        for name, quantity, unit_cents in lines:
            total = line_total(quantity, unit_cents)
            subtotal = subtotal + total
            rate = tax_rate(total)
            if rate > 0:
                taxed = taxed + 1
                tax = tax + total * rate // 100
            label = str(rate) + "%"
            if label in bands:
                bands[label] = bands[label] + 1
            else:
                bands[label] = 1
        return {
            "lines": len(lines),
            "subtotal": subtotal,
            "tax": tax,
            "total": subtotal + tax,
            "taxed": taxed,
            "bands": bands,
        }
""")

INVOICE_REPORT = textwrap.dedent("""\
    # Rendering for the invoice report.


    def money(cents):
        return "$" + str(cents // 100) + "." + str(cents % 100).rjust(2, "0")


    def render(summary):
        rows = []
        rows.append("invoice report")
        rows.append("lines: " + str(summary["lines"]))
        for label in sorted(summary["bands"]):
            rows.append("band " + label + ": " + str(summary["bands"][label]))
        rows.append("subtotal: " + money(summary["subtotal"]))
        rows.append("tax: " + money(summary["tax"]))
        rows.append("total: " + money(summary["total"]))
        return "\\n".join(rows)
""")

INVOICE_MAIN = textwrap.dedent("""\
    from inventory import LINES, summarise
    from report import render


    def main():
        print(render(summarise(LINES)))


    if __name__ == "__main__":
        main()
""")

GRADES_GRADES = textwrap.dedent("""\
    # Scores, the curve applied to them, and the bands they fall in.

    SCORES = [88, 71, 64, 95, 52, 79, 83, 67, 90, 58]


    def curved(score, lift):
        value = score + lift
        if value > 100:
            return 100
        return value


    def letter(score):
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 70:
            return "C"
        if score >= 60:
            return "D"
        return "F"


    def summarise(scores, lift):
        bands = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        total = 0
        best = 0
        for score in scores:
            value = curved(score, lift)
            total = total + value
            if value > best:
                best = value
            band = letter(value)
            bands[band] = bands[band] + 1
        mean = total // len(scores) if scores else 0
        return {"count": len(scores), "mean": mean, "best": best, "bands": bands}
""")

GRADES_REPORT = textwrap.dedent("""\
    # Rendering for the grade report.


    def bar(count):
        return "#" * count


    def render(summary):
        rows = []
        rows.append("grade report")
        rows.append("count: " + str(summary["count"]))
        rows.append("mean: " + str(summary["mean"]))
        rows.append("best: " + str(summary["best"]))
        for band in ("A", "B", "C", "D", "F"):
            rows.append(band + " " + bar(summary["bands"][band]))
        return "\\n".join(rows)
""")

GRADES_MAIN = textwrap.dedent("""\
    from grades import SCORES, summarise
    from report import render


    def main():
        print(render(summarise(SCORES, 4)))


    if __name__ == "__main__":
        main()
""")

SCHEDULE_SCHEDULE = textwrap.dedent("""\
    # Blocks booked in a day, merged into the spans that are actually busy.

    BLOCKS = [(540, 615), (600, 660), (720, 780), (760, 830), (900, 930)]


    def merge(blocks):
        if not blocks:
            return []
        ordered = sorted(blocks)
        merged = [ordered[0]]
        for start, end in ordered[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                if end > last_end:
                    merged[-1] = (last_start, end)
            else:
                merged.append((start, end))
        return merged


    def minutes(spans):
        total = 0
        for start, end in spans:
            total = total + (end - start)
        return total


    def summarise(blocks):
        spans = merge(blocks)
        busy = minutes(spans)
        longest = 0
        for start, end in spans:
            length = end - start
            if length > longest:
                longest = length
        return {
            "blocks": len(blocks),
            "spans": len(spans),
            "busy": busy,
            "longest": longest,
        }
""")

SCHEDULE_REPORT = textwrap.dedent("""\
    # Rendering for the schedule report.


    def clock(minutes):
        return str(minutes // 60).rjust(2, "0") + ":" + str(minutes % 60).rjust(2, "0")


    def render(summary):
        rows = []
        rows.append("schedule report")
        rows.append("blocks: " + str(summary["blocks"]))
        rows.append("spans: " + str(summary["spans"]))
        rows.append("busy: " + clock(summary["busy"]))
        rows.append("longest: " + clock(summary["longest"]))
        return "\\n".join(rows)
""")

SCHEDULE_MAIN = textwrap.dedent("""\
    from schedule import BLOCKS, summarise
    from report import render


    def main():
        print(render(summarise(BLOCKS)))


    if __name__ == "__main__":
        main()
""")


STOCK_STOCK = textwrap.dedent("""\
    # Stock rows and the flags a warehouse would act on.

    STOCK = [
        ("bolt", 12, 240),
        ("gasket", 4, 1250),
        ("housing", 2, 8900),
        ("washer", 40, 15),
        ("shaft", 3, 4200),
        ("bracket", 17, 310),
    ]


    def restock_flag(quantity, floor=5):
        if quantity == 0:
            return "OUT"
        if quantity < floor:
            return "LOW"
        return "OK"


    def summarise(items):
        rows = []
        value = 0
        low = 0
        widest = 0
        for name, quantity, cents in items:
            worth = quantity * cents
            value = value + worth
            flag = restock_flag(quantity)
            if flag != "OK":
                low = low + 1
            if len(name) > widest:
                widest = len(name)
            rows.append((name, quantity, cents, worth, flag))
        return {"rows": rows, "value": value, "low": low, "widest": widest,
                "skus": len(items)}
""")

STOCK_REPORT = textwrap.dedent("""\
    # Rendering for the stock table.

    SEP = chr(10)


    def money(cents):
        return "$" + str(cents // 100) + "." + str(cents % 100).rjust(2, "0")


    def pad(text, width):
        return str(text).ljust(width)


    def render(summary):
        rows = []
        rows.append("stock report")
        rows.append("skus: " + str(summary["skus"]))
        rows.append("low: " + str(summary["low"]))
        rows.append("value: " + money(summary["value"]))
        rows.append("")
        rows.append(pad("name", 10) + pad("qty", 5) + pad("value", 10) + "flag")
        for name, quantity, cents, worth, flag in summary["rows"]:
            rows.append(pad(name, 10) + pad(quantity, 5) + pad(money(worth), 10) + flag)
        return SEP.join(rows)
""")

STOCK_MAIN = textwrap.dedent("""\
    from stock import STOCK, summarise
    from report import render


    def main():
        print(render(summarise(STOCK)))


    if __name__ == "__main__":
        main()
""")

LEDGER_LEDGER = textwrap.dedent("""\
    # Entries posted in order, with the balance after each one.

    ENTRIES = [
        ("open", 50000),
        ("rent", -32000),
        ("sales", 18400),
        ("tools", -9250),
        ("refund", -4100),
        ("sales", 7600),
    ]


    def post(balance, amount, floor):
        after = balance + amount
        if after < floor:
            return after, "overdrawn"
        return after, "ok"


    def summarise(entries, floor=0):
        rows = []
        balance = 0
        lowest = 0
        overdraw = 0
        peak = 0
        for label, amount in entries:
            balance, status = post(balance, amount, floor)
            if status != "ok":
                overdraw = overdraw + 1
            if balance < lowest:
                lowest = balance
            if balance > peak:
                peak = balance
            rows.append((label, amount, balance, status))
        return {"rows": rows, "balance": balance, "lowest": lowest,
                "peak": peak, "overdraw": overdraw}
""")

LEDGER_REPORT = textwrap.dedent("""\
    # Rendering for the ledger.

    SEP = chr(10)


    def money(cents):
        sign = "-" if cents < 0 else ""
        value = abs(cents)
        return sign + "$" + str(value // 100) + "." + str(value % 100).rjust(2, "0")


    def render(summary):
        rows = []
        rows.append("ledger report")
        rows.append("entries: " + str(len(summary["rows"])))
        for label, amount, balance, status in summary["rows"]:
            rows.append(label.ljust(8) + money(amount).rjust(11) + money(balance).rjust(12)
                        + "  " + status)
        rows.append("balance: " + money(summary["balance"]))
        rows.append("lowest: " + money(summary["lowest"]))
        rows.append("peak: " + money(summary["peak"]))
        rows.append("overdraw: " + str(summary["overdraw"]))
        return SEP.join(rows)
""")

LEDGER_MAIN = textwrap.dedent("""\
    from ledger import ENTRIES, summarise
    from report import render


    def main():
        print(render(summarise(ENTRIES)))


    if __name__ == "__main__":
        main()
""")

HISTOGRAM_HISTOGRAM = textwrap.dedent("""\
    # Readings grouped into fixed-width buckets.

    SAMPLES = [3, 11, 12, 19, 22, 27, 31, 34, 38, 41, 44, 47, 52, 58, 61,
               66, 70, 74, 79, 83, 88, 92, 97]
    WIDTH = 10


    def bucket_of(value, width):
        if value < 0:
            return -1
        return value // width


    def summarise(samples, width):
        counts = {}
        total = 0
        peak = 0
        peak_bucket = 0
        for value in samples:
            total = total + value
            key = bucket_of(value, width)
            if key in counts:
                counts[key] = counts[key] + 1
            else:
                counts[key] = 1
            if counts[key] > peak:
                peak = counts[key]
                peak_bucket = key
        mean = total // len(samples) if samples else 0
        return {"counts": counts, "total": total, "peak": peak,
                "peak_bucket": peak_bucket, "mean": mean, "width": width}
""")

HISTOGRAM_REPORT = textwrap.dedent("""\
    # Rendering for the histogram.

    SEP = chr(10)


    def bar(count):
        return "*" * count


    def render(summary):
        rows = []
        rows.append("histogram report")
        rows.append("mean: " + str(summary["mean"]))
        rows.append("peak: " + str(summary["peak"]) + " in bucket "
                    + str(summary["peak_bucket"]))
        width = summary["width"]
        for key in sorted(summary["counts"]):
            low = key * width
            rows.append(str(low).rjust(3) + "-" + str(low + width - 1).rjust(3)
                        + " " + bar(summary["counts"][key]))
        return SEP.join(rows)
""")

HISTOGRAM_MAIN = textwrap.dedent("""\
    from histogram import SAMPLES, WIDTH, summarise
    from report import render


    def main():
        print(render(summarise(SAMPLES, WIDTH)))


    if __name__ == "__main__":
        main()
""")

ROMANS_ROMANS = textwrap.dedent("""\
    # Numbers and the numerals the subtractive rules produce.

    NUMBERS = [1987, 2024, 49, 9, 444, 1666]
    UNITS = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]


    def to_roman(value):
        left = value
        letters = []
        for size, text in UNITS:
            while left >= size:
                letters.append(text)
                left = left - size
        return "".join(letters)


    def summarise(numbers):
        rows = []
        longest = 0
        letters = 0
        for value in numbers:
            text = to_roman(value)
            if len(text) > longest:
                longest = len(text)
            letters = letters + len(text)
            rows.append((value, text))
        return {"rows": rows, "longest": longest, "letters": letters,
                "count": len(numbers)}
""")

ROMANS_REPORT = textwrap.dedent("""\
    # Rendering for the numeral table.

    SEP = chr(10)


    def render(summary):
        rows = []
        rows.append("roman report")
        rows.append("count: " + str(summary["count"]))
        rows.append("longest: " + str(summary["longest"]))
        rows.append("letters: " + str(summary["letters"]))
        for value, text in summary["rows"]:
            rows.append(str(value).rjust(5) + " " + text)
        return SEP.join(rows)
""")

ROMANS_MAIN = textwrap.dedent("""\
    from romans import NUMBERS, summarise
    from report import render


    def main():
        print(render(summarise(NUMBERS)))


    if __name__ == "__main__":
        main()
""")

MATRIX_MATRIX = textwrap.dedent("""\
    # A small grid turned on its side, with a column total for each row.

    GRID = [
        [1, 2, 3, 4],
        [5, 6, 7, 8],
        [9, 10, 11, 12],
    ]


    def transpose(rows):
        if not rows:
            return []
        width = len(rows[0])
        out = []
        for column in range(width):
            line = []
            for row in rows:
                if column < len(row):
                    line.append(row[column])
            out.append(line)
        return out


    def summarise(rows):
        grid = transpose(rows)
        totals = []
        widest = 0
        for line in grid:
            total = 0
            for value in line:
                total = total + value
            if total > widest:
                widest = total
            totals.append(total)
        return {"grid": grid, "totals": totals, "widest": widest,
                "rows": len(rows), "columns": len(grid)}
""")

MATRIX_REPORT = textwrap.dedent("""\
    # Rendering for the transposed grid.

    SEP = chr(10)


    def row_text(line):
        return " ".join(str(value).rjust(3) for value in line)


    def render(summary):
        rows = []
        rows.append("matrix report")
        rows.append("rows: " + str(summary["rows"]))
        rows.append("columns: " + str(summary["columns"]))
        for line, total in zip(summary["grid"], summary["totals"]):
            rows.append(row_text(line) + "  total " + str(total))
        rows.append("widest: " + str(summary["widest"]))
        return SEP.join(rows)
""")

MATRIX_MAIN = textwrap.dedent("""\
    from matrix import GRID, summarise
    from report import render


    def main():
        print(render(summarise(GRID)))


    if __name__ == "__main__":
        main()
""")

RLE_RLE = textwrap.dedent("""\
    # A run-length view of a short string, and the check that it round-trips.

    TEXT = "aaabbccccdddeeffffgghhhhhh"


    def encode(text):
        out = []
        if not text:
            return out
        current = text[0]
        count = 1
        for ch in text[1:]:
            if ch == current:
                count = count + 1
            else:
                out.append((current, count))
                current = ch
                count = 1
        out.append((current, count))
        return out


    def decode(pairs):
        parts = []
        for ch, count in pairs:
            parts.append(ch * count)
        return "".join(parts)


    def summarise(text):
        pairs = encode(text)
        longest = 0
        compact = ""
        for ch, count in pairs:
            if count > longest:
                longest = count
            compact = compact + ch + str(count)
        return {"pairs": pairs, "runs": len(pairs), "longest": longest,
                "compact": compact, "round_trip": decode(pairs) == text}
""")

RLE_REPORT = textwrap.dedent("""\
    # Rendering for the run-length report.

    SEP = chr(10)


    def render(summary):
        rows = []
        rows.append("run length report")
        rows.append("runs: " + str(summary["runs"]))
        rows.append("longest: " + str(summary["longest"]))
        rows.append("compact: " + summary["compact"])
        rows.append("round trip: " + ("ok" if summary["round_trip"] else "broken"))
        for ch, count in summary["pairs"]:
            rows.append("  " + ch + " x" + str(count))
        return SEP.join(rows)
""")

RLE_MAIN = textwrap.dedent("""\
    from rle import TEXT, summarise
    from report import render


    def main():
        print(render(summarise(TEXT)))


    if __name__ == "__main__":
        main()
""")


SEARCH_SEARCH = textwrap.dedent("""\
    # A sorted list and the probes a binary search makes before it answers.

    VALUES = [2, 5, 8, 12, 16, 23, 38, 56, 72, 91]
    TARGETS = [23, 91, 4, 16]


    def find(values, target):
        low = 0
        high = len(values) - 1
        probes = []
        while low <= high:
            mid = (low + high) // 2
            probes.append(mid)
            if values[mid] == target:
                return mid, probes
            if values[mid] < target:
                low = mid + 1
            else:
                high = mid - 1
        return -1, probes


    def summarise(values, targets):
        rows = []
        found = 0
        probes = 0
        longest = 0
        for target in targets:
            index, trail = find(values, target)
            probes = probes + len(trail)
            if len(trail) > longest:
                longest = len(trail)
            if index >= 0:
                found = found + 1
            rows.append((target, index, trail))
        return {"rows": rows, "found": found, "probes": probes,
                "longest": longest, "count": len(targets)}
""")

SEARCH_REPORT = textwrap.dedent("""\
    # Rendering for the search report.

    SEP = chr(10)


    def trail_text(trail):
        return " ".join(str(index) for index in trail)


    def render(summary):
        rows = []
        rows.append("search report")
        rows.append("targets: " + str(summary["count"]))
        rows.append("found: " + str(summary["found"]))
        rows.append("probes: " + str(summary["probes"]))
        for target, index, trail in summary["rows"]:
            rows.append(str(target).rjust(3) + " -> " + str(index).rjust(2)
                        + " after " + trail_text(trail))
        rows.append("longest: " + str(summary["longest"]))
        return SEP.join(rows)
""")

SEARCH_MAIN = textwrap.dedent("""\
    from search import TARGETS, VALUES, summarise
    from report import render


    def main():
        print(render(summarise(VALUES, TARGETS)))


    if __name__ == "__main__":
        main()
""")

CACHE_CACHE = textwrap.dedent("""\
    # A small least-recently-used cache replayed from fixed operations.

    CAPACITY = 3
    OPERATIONS = [
        ("get", "a"), ("put", "a"), ("put", "b"), ("put", "c"),
        ("get", "a"), ("put", "d"), ("get", "b"), ("put", "e"),
        ("get", "c"), ("put", "e"), ("get", "a"),
    ]


    def replay(capacity, operations):
        order = []
        values = {}
        hits = 0
        misses = 0
        evicted = []
        log = []
        for action, key in operations:
            if action == "get":
                if key in values:
                    hits = hits + 1
                    order.remove(key)
                    order.append(key)
                    log.append((action, key, "hit"))
                else:
                    misses = misses + 1
                    log.append((action, key, "miss"))
            else:
                values[key] = key.upper()
                if key in order:
                    order.remove(key)
                order.append(key)
                if len(order) > capacity:
                    gone = order.pop(0)
                    values.pop(gone, None)
                    evicted.append(gone)
                log.append((action, key, "put"))
        return {"log": log, "hits": hits, "misses": misses,
                "evicted": evicted, "order": order}


    def summarise(capacity, operations):
        result = replay(capacity, operations)
        total = result["hits"] + result["misses"]
        rate = 0
        if total > 0:
            rate = result["hits"] * 100 // total
        result["hit_rate"] = rate
        result["keys"] = len(result["order"])
        return result
""")

CACHE_REPORT = textwrap.dedent("""\
    # Rendering for the cache replay.

    SEP = chr(10)


    def render(summary):
        rows = []
        rows.append("cache report")
        rows.append("hits: " + str(summary["hits"]))
        rows.append("misses: " + str(summary["misses"]))
        rows.append("hit rate: " + str(summary["hit_rate"]) + "%")
        for action, key, outcome in summary["log"]:
            rows.append(action.ljust(4) + key + " " + outcome)
        rows.append("evicted: " + (" ".join(summary["evicted"]) or "none"))
        rows.append("resident: " + " ".join(summary["order"]))
        return SEP.join(rows)
""")

CACHE_MAIN = textwrap.dedent("""\
    from cache import CAPACITY, OPERATIONS, summarise
    from report import render


    def main():
        print(render(summarise(CAPACITY, OPERATIONS)))


    if __name__ == "__main__":
        main()
""")

LUHN_LUHN = textwrap.dedent("""\
    # Card numbers and the digit the Luhn rule says they should end with.

    NUMBERS = [
        "4539578763621486",
        "6011111111111117",
        "79927398713",
        "79927398710",
        "4222222222222",
    ]


    def digits_of(text):
        out = []
        for ch in text:
            if ch.isdigit():
                out.append(int(ch))
        return out


    def describe(number):
        digits = digits_of(number)
        if not digits:
            return "empty", 0
        total = 0
        doubled = 0
        for position, digit in enumerate(reversed(digits)):
            if position % 2 == 1:
                value = digit * 2
                if value > 9:
                    value = value - 9
                doubled = doubled + 1
                total = total + value
            else:
                total = total + digit
        if len(digits) < 2:
            return "short", total
        if total % 10 == 0:
            return "ok", total
        return "invalid", total


    def summarise(numbers):
        rows = []
        ok = 0
        longest = 0
        for number in numbers:
            status, total = describe(number)
            if status == "ok":
                ok = ok + 1
            if len(number) > longest:
                longest = len(number)
            rows.append((number, total, total % 10, status))
        return {"rows": rows, "ok": ok, "longest": longest,
                "count": len(numbers)}
""")

LUHN_REPORT = textwrap.dedent("""\
    # Rendering for the card check table.

    SEP = chr(10)


    def render(summary):
        rows = []
        rows.append("luhn report")
        rows.append("numbers: " + str(summary["count"]))
        rows.append("valid: " + str(summary["ok"]))
        for number, total, digit, status in summary["rows"]:
            rows.append(number.ljust(summary["longest"] + 2) + str(total).rjust(4)
                        + " " + str(digit).ljust(2) + status)
        return SEP.join(rows)
""")

LUHN_MAIN = textwrap.dedent("""\
    from luhn import NUMBERS, summarise
    from report import render


    def main():
        print(render(summarise(NUMBERS)))


    if __name__ == "__main__":
        main()
""")

DIJKSTRA_GRAPH = textwrap.dedent("""\
    # A small weighted graph and the distances out of one fixed start.

    EDGES = [
        ("a", "b", 7), ("a", "c", 9), ("a", "f", 14),
        ("b", "c", 10), ("b", "d", 15),
        ("c", "d", 11), ("c", "f", 2),
        ("d", "e", 6),
        ("e", "f", 9),
    ]
    START = "a"


    def neighbours(edges, node):
        out = []
        for left, right, weight in edges:
            if left == node:
                out.append((right, weight))
            elif right == node:
                out.append((left, weight))
        return out


    def distances(edges, start):
        nodes = []
        for left, right, weight in edges:
            if left not in nodes:
                nodes.append(left)
            if right not in nodes:
                nodes.append(right)
        dist = {}
        for node in nodes:
            dist[node] = None
        dist[start] = 0
        done = []
        while len(done) < len(nodes):
            best = None
            for node in nodes:
                if node in done or dist[node] is None:
                    continue
                if best is None or dist[node] < dist[best]:
                    best = node
            if best is None:
                break
            done.append(best)
            for other, weight in neighbours(edges, best):
                candidate = dist[best] + weight
                if dist[other] is None or candidate < dist[other]:
                    dist[other] = candidate
        return dist


    def summarise(edges, start):
        dist = distances(edges, start)
        order = []
        total = 0
        for node in sorted(dist):
            value = dist[node]
            order.append((node, value))
            if value is not None:
                total = total + value
        return {"order": order, "total": total, "nodes": len(order),
                "start": start}
""")

DIJKSTRA_REPORT = textwrap.dedent("""\
    # Rendering for the distance table.

    SEP = chr(10)


    def render(summary):
        rows = []
        rows.append("graph report")
        rows.append("start: " + summary["start"])
        rows.append("nodes: " + str(summary["nodes"]))
        for node, value in summary["order"]:
            if value is None:
                rows.append("  " + node.ljust(4) + "unreachable")
            else:
                rows.append("  " + node.ljust(4) + str(value).rjust(4))
        rows.append("total: " + str(summary["total"]))
        return SEP.join(rows)
""")

DIJKSTRA_MAIN = textwrap.dedent("""\
    from graph import EDGES, START, summarise
    from report import render


    def main():
        print(render(summarise(EDGES, START)))


    if __name__ == "__main__":
        main()
""")


SEARCH_TRACE_SEARCH = textwrap.dedent("""\
    # A sorted list and the probes a search makes before it answers.

    VALUES = [2, 4, 6, 8, 10, 12, 14]
    TARGETS = [8, 5]


    def find(values, target):
        low = 0
        high = len(values) - 1
        trail = []
        while low <= high:
            mid = low + (high - low) // 2
            trail.append((mid, values[mid]))
            if values[mid] == target:
                return mid, trail
            if values[mid] < target:
                low = mid + 1
            else:
                high = mid - 1
        return -1, trail


    def summarise(values, targets):
        rows = []
        for target in targets:
            index, trail = find(values, target)
            rows.append((target, index, trail))
        return {"rows": rows, "count": len(targets), "size": len(values)}
""")

SEARCH_TRACE_REPORT = textwrap.dedent("""\
    # Rendering for the search trace.

    SEP = chr(10)


    def render(summary):
        rows = []
        for target, index, trail in summary["rows"]:
            rows.append("search " + str(target))
            for mid, value in trail:
                rows.append("probe " + str(mid) + " value " + str(value))
            if index >= 0:
                rows.append("found " + str(target) + " at index " + str(index))
            else:
                rows.append("not found " + str(target))
        return SEP.join(rows)
""")

SEARCH_TRACE_MAIN = textwrap.dedent("""\
    from search_trace import TARGETS, VALUES, summarise
    from report import render


    def main():
        print(render(summarise(VALUES, TARGETS)))


    if __name__ == "__main__":
        main()
""")

LRU_LRU = textwrap.dedent("""\
    # A two-entry cache replayed from fixed operations.

    CAPACITY = 2
    OPERATIONS = [
        ("get", "a"), ("put", "b"), ("get", "a"),
        ("put", "c"), ("get", "b"), ("get", "a"),
    ]


    def replay(capacity, operations):
        order = []
        log = []
        for action, key in operations:
            if action == "get":
                if key in order:
                    order.remove(key)
                    order.append(key)
                    log.append((action, key, "hit", ""))
                else:
                    if len(order) < capacity:
                        order.append(key)
                    log.append((action, key, "miss", ""))
            else:
                if key in order:
                    order.remove(key)
                order.append(key)
                gone = ""
                if len(order) > capacity:
                    gone = order.pop(0)
                log.append((action, key, "put", gone))
        return {"log": log, "capacity": capacity, "resident": order}


    def summarise(capacity, operations):
        result = replay(capacity, operations)
        hits = 0
        misses = 0
        for action, key, outcome, gone in result["log"]:
            if outcome == "hit":
                hits = hits + 1
            elif outcome == "miss":
                misses = misses + 1
        result["hits"] = hits
        result["misses"] = misses
        return result
""")

LRU_REPORT = textwrap.dedent("""\
    # Rendering for the cache replay.

    SEP = chr(10)


    def render(summary):
        rows = []
        for action, key, outcome, gone in summary["log"]:
            line = action + " " + key
            if outcome == "put":
                if gone:
                    line = line + " evict " + gone
            else:
                line = line + " " + outcome
            rows.append(line)
        return SEP.join(rows)
""")

LRU_MAIN = textwrap.dedent("""\
    from lru import CAPACITY, OPERATIONS, summarise
    from report import render


    def main():
        print(render(summarise(CAPACITY, OPERATIONS)))


    if __name__ == "__main__":
        main()
""")

ISBN_ISBN = textwrap.dedent("""\
    # ISBN-10 codes and the check digit the weights produce.

    CODES = ["0306406152", "0306406153"]
    WEIGHTS = [10, 9, 8, 7, 6, 5, 4, 3, 2]


    def check_digit(code):
        total = 0
        for index in range(9):
            total = total + int(code[index]) * WEIGHTS[index]
        value = (11 - total % 11) % 11
        if value == 10:
            return "X"
        return str(value)


    def describe(code):
        expected = check_digit(code)
        given = code[9].upper()
        return expected, given, expected == given


    def summarise(codes):
        rows = []
        valid = 0
        for code in codes:
            expected, given, ok = describe(code)
            if ok:
                valid = valid + 1
            rows.append((code, expected, given, ok))
        return {"rows": rows, "valid": valid, "count": len(codes)}
""")

ISBN_REPORT = textwrap.dedent("""\
    # Rendering for the ISBN check.

    SEP = chr(10)


    def render(summary):
        rows = []
        for code, expected, given, ok in summary["rows"]:
            status = "valid" if ok else "invalid"
            rows.append(code + " " + status + " check " + expected)
        return SEP.join(rows)
""")

ISBN_MAIN = textwrap.dedent("""\
    from isbn import CODES, summarise
    from report import render


    def main():
        print(render(summarise(CODES)))


    if __name__ == "__main__":
        main()
""")

VENDING_VENDING = textwrap.dedent("""\
    # Purchases and the coins a greedy dispenser hands back.

    COINS = [50, 25, 20, 10]
    PURCHASES = [(65, 100), (130, 200)]


    def dispense(change, coins):
        counts = []
        left = change
        for coin in coins:
            count = left // coin
            left = left - count * coin
            counts.append((coin, count))
        return counts, left


    def summarise(purchases, coins):
        rows = []
        for price, paid in purchases:
            change = paid - price
            counts, rest = dispense(change, coins)
            rows.append((price, paid, change, counts, rest))
        return {"rows": rows, "count": len(purchases)}
""")

VENDING_REPORT = textwrap.dedent("""\
    # Rendering for the change report.

    SEP = chr(10)


    def render(summary):
        rows = []
        for price, paid, change, counts, rest in summary["rows"]:
            rows.append("price " + str(price) + " paid " + str(paid)
                        + " change " + str(change))
            for coin, count in counts:
                if count > 0:
                    rows.append(str(count) + " x " + str(coin))
            if rest:
                rows.append("short " + str(rest))
        return SEP.join(rows)
""")

VENDING_MAIN = textwrap.dedent("""\
    from vending import COINS, PURCHASES, summarise
    from report import render


    def main():
        print(render(summarise(PURCHASES, COINS)))


    if __name__ == "__main__":
        main()
""")

LIFE_LIFE = textwrap.dedent("""\
    # One step of life on a four by four grid.

    SIZE = 4
    LIVE = [(0, 1), (1, 1), (2, 1)]


    def neighbours(row, column, live, size):
        count = 0
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                r = row + dr
                c = column + dc
                if r < 0 or c < 0 or r >= size or c >= size:
                    continue
                if (r, c) in live:
                    count = count + 1
        return count


    def step(live, size):
        out = []
        for row in range(size):
            for column in range(size):
                count = neighbours(row, column, live, size)
                alive = (row, column) in live
                if alive and count in (2, 3):
                    out.append((row, column))
                elif not alive and count == 3:
                    out.append((row, column))
        return out


    def summarise(live, size):
        after = step(live, size)
        return {"size": size, "before": len(live), "after": len(after),
                "live": after}
""")

LIFE_REPORT = textwrap.dedent("""\
    # Rendering for the grid step.

    SEP = chr(10)


    def render(summary):
        rows = []
        size = summary["size"]
        alive = summary["live"]
        for row in range(size):
            line = ""
            for column in range(size):
                if (row, column) in alive:
                    line = line + "1"
                else:
                    line = line + "0"
            rows.append("row " + line)
        rows.append("live " + str(summary["after"]))
        return SEP.join(rows)
""")

LIFE_MAIN = textwrap.dedent("""\
    from life import LIVE, SIZE, summarise
    from report import render


    def main():
        print(render(summarise(LIVE, SIZE)))


    if __name__ == "__main__":
        main()
""")


def _set(title: str, description: str, family: str, main: str, target: str,
         formatter: str, target_path: str, formatter_path: str) -> dict:
    return {
        "title": title,
        "description": description,
        "family": family,
        "files": [
            {"path": "main.py", "content": main},
            {"path": target_path, "content": target},
            {"path": formatter_path, "content": formatter},
        ],
        "target": target_path,
    }


def sets() -> list[dict]:
    """Eighteen python sets: invoices, grades, schedule, stock, ledger,
    histogram, numerals, a transposed grid, run-length encoding, a binary
    search trace, an LRU cache replay, Luhn validation, and Dijkstra, plus a
    search trace, a two-entry cache, an ISBN-10 check, a coin count and one
    life step that have siblings in the other four languages."""
    return [
        _set("python cli set - invoice totals by tax band",
             "Reads embedded invoice lines, applies a banded tax rate, and prints "
             "the subtotal, tax and total.",
             "invoice", INVOICE_MAIN, INVOICE_INVENTORY, INVOICE_REPORT,
             "inventory.py", "report.py"),
        _set("python cli set - grade curve and letter bands",
             "Applies a fixed curve to embedded scores and prints the mean, the "
             "best score, and a bar per letter band.",
             "grades", GRADES_MAIN, GRADES_GRADES, GRADES_REPORT,
             "grades.py", "report.py"),
        _set("python cli set - merged day schedule",
             "Merges overlapping booking blocks into busy spans and prints the "
             "block count, span count, total busy time and the longest span.",
             "schedule", SCHEDULE_MAIN, SCHEDULE_SCHEDULE, SCHEDULE_REPORT,
             "schedule.py", "report.py"),
        _set("python cli set - stock table with restock flags",
             "Prints a padded stock table with a value per line and an OUT/LOW/OK "
             "flag from each quantity.",
             "stock", STOCK_MAIN, STOCK_STOCK, STOCK_REPORT,
             "stock.py", "report.py"),
        _set("python cli set - running balance ledger",
             "Posts embedded entries in order and prints the balance after each "
             "one, the lowest and peak balances, and how often it went over.",
             "ledger", LEDGER_MAIN, LEDGER_LEDGER, LEDGER_REPORT,
             "ledger.py", "report.py"),
        _set("python cli set - sample histogram by bucket",
             "Groups embedded readings into width-10 buckets and prints a bar per "
             "bucket plus the mean and the peak bucket.",
             "histogram", HISTOGRAM_MAIN, HISTOGRAM_HISTOGRAM, HISTOGRAM_REPORT,
             "histogram.py", "report.py"),
        _set("python cli set - roman numeral table",
             "Converts embedded numbers with the subtractive rules and prints each "
             "numeral with the longest and total letter counts.",
             "roman", ROMANS_MAIN, ROMANS_ROMANS, ROMANS_REPORT,
             "romans.py", "report.py"),
        _set("python cli set - matrix transpose totals",
             "Transposes an embedded grid, totals each row of the result, and "
             "prints the shape and the widest total.",
             "matrix", MATRIX_MAIN, MATRIX_MATRIX, MATRIX_REPORT,
             "matrix.py", "report.py"),
        _set("python cli set - run length encoding",
             "Encodes an embedded string into runs, decodes it back, and prints the "
             "run count, the longest run and the compact form.",
             "encode", RLE_MAIN, RLE_RLE, RLE_REPORT,
             "rle.py", "report.py"),
        _set("python cli set - binary search probe trace",
             "Searches a sorted embedded list for fixed targets and prints the "
             "index each one landed on, the probes it took, and the deepest trace.",
             "binary-search-trace", SEARCH_MAIN, SEARCH_SEARCH, SEARCH_REPORT,
             "search.py", "report.py"),
        _set("python cli set - least recently used cache replay",
             "Replays a fixed list of get and put operations against a "
             "capacity-three cache and prints the hits, misses, evictions and "
             "resident keys.",
             "lru-cache-simulation", CACHE_MAIN, CACHE_CACHE, CACHE_REPORT,
             "cache.py", "report.py"),
        _set("python cli set - luhn card number check",
             "Runs the Luhn rule over embedded card numbers and prints each "
             "checksum, its last digit, and whether the number is valid.",
             "luhn-validation", LUHN_MAIN, LUHN_LUHN, LUHN_REPORT,
             "luhn.py", "report.py"),
        _set("python cli set - dijkstra distances from one start",
             "Runs Dijkstra over a small embedded weighted graph and prints the "
             "shortest distance to every node plus their total.",
             "dijkstra-shortest-path", DIJKSTRA_MAIN, DIJKSTRA_GRAPH,
             DIJKSTRA_REPORT, "graph.py", "report.py"),
        _set("binary search trace over a sorted list",
             "Searches a sorted embedded list for two targets and prints every "
             "probe it made and the index it landed on.",
             "binary-search-trace",
             SEARCH_TRACE_MAIN, SEARCH_TRACE_SEARCH, SEARCH_TRACE_REPORT,
             "search_trace.py", "report.py"),
        _set("lru cache simulation with capacity two",
             "Replays fixed get and put operations against a two-entry cache "
             "and prints each outcome and the key an eviction removed.",
             "lru-cache-simulation",
             LRU_MAIN, LRU_LRU, LRU_REPORT,
             "lru.py", "report.py"),
        _set("isbn ten checksum validation",
             "Computes the ISBN-10 check digit from the first nine digits and "
             "prints whether each embedded code ends with it.",
             "isbn-checksum",
             ISBN_MAIN, ISBN_ISBN, ISBN_REPORT,
             "isbn.py", "report.py"),
        _set("vending machine change by coin count",
             "Gives change for embedded purchases with a greedy dispenser and "
             "prints the coin count it hands back.",
             "vending-change",
             VENDING_MAIN, VENDING_VENDING, VENDING_REPORT,
             "vending.py", "report.py"),
        _set("conway life step on a four by four grid",
             "Applies one generation of Conway's rules to an embedded four by "
             "four grid and prints the next grid and its live count.",
             "game-of-life-step",
             LIFE_MAIN, LIFE_LIFE, LIFE_REPORT,
             "life.py", "report.py"),
    ]
