"""php cli sets — three-file programs whose report is the behaviour.

An entry script, a formatter, and a target module that turns embedded data into
a deterministic report. Standard library only, no input, no clock.
"""
from __future__ import annotations

import textwrap


INVOICE_INVENTORY = textwrap.dedent("""\
    <?php

    const LINES = [
        ["bolt", 12, 240],
        ["gasket", 4, 1250],
        ["housing", 2, 8900],
        ["washer", 40, 15],
        ["shaft", 3, 4200],
    ];

    function lineTotal(int $quantity, int $unitCents): int
    {
        return $quantity * $unitCents;
    }

    function taxRate(int $cents): int
    {
        if ($cents >= 20000) {
            return 8;
        }
        if ($cents >= 8000) {
            return 5;
        }
        return 0;
    }

    function summarise(array $lines): array
    {
        $subtotal = 0;
        $tax = 0;
        $taxed = 0;
        $bands = [];
        foreach ($lines as $line) {
            $total = lineTotal($line[1], $line[2]);
            $subtotal += $total;
            $rate = taxRate($total);
            if ($rate > 0) {
                $taxed += 1;
                $tax += intdiv($total * $rate, 100);
            }
            $label = $rate . "%";
            if (isset($bands[$label])) {
                $bands[$label] += 1;
            } else {
                $bands[$label] = 1;
            }
        }
        return [
            "lines" => count($lines),
            "subtotal" => $subtotal,
            "tax" => $tax,
            "total" => $subtotal + $tax,
            "taxed" => $taxed,
            "bands" => $bands,
        ];
    }
""")

INVOICE_REPORT = textwrap.dedent("""\
    <?php

    function money(int $cents): string
    {
        return sprintf('$%d.%02d', intdiv($cents, 100), $cents % 100);
    }

    function render(array $summary): string
    {
        $rows = [];
        $rows[] = "invoice report";
        $rows[] = "lines: " . $summary["lines"];
        $bands = $summary["bands"];
        ksort($bands);
        foreach ($bands as $label => $count) {
            $rows[] = "band " . $label . ": " . $count;
        }
        $rows[] = "subtotal: " . money($summary["subtotal"]);
        $rows[] = "tax: " . money($summary["tax"]);
        $rows[] = "total: " . money($summary["total"]);
        return implode(PHP_EOL, $rows);
    }
""")

INVOICE_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/inventory.php';
    require_once __DIR__ . '/report.php';

    echo render(summarise(LINES)) . PHP_EOL;
""")

WORDS_WORDS = textwrap.dedent("""\
    <?php

    const PASSAGE = "the quick brown fox jumps over the lazy dog the fox barks "
        . "and the dog sleeps while the fox runs";

    function tokenise(string $text): array
    {
        return explode(" ", trim($text));
    }

    function tally(array $words): array
    {
        $counts = [];
        foreach ($words as $word) {
            $clean = strtolower(trim($word, ".,;:!?"));
            if ($clean === "") {
                continue;
            }
            if (isset($counts[$clean])) {
                $counts[$clean] += 1;
            } else {
                $counts[$clean] = 1;
            }
        }
        return $counts;
    }

    function leaderboard(array $counts, int $limit): array
    {
        $pairs = [];
        foreach ($counts as $word => $count) {
            $pairs[] = [$word, $count];
        }
        usort($pairs, function ($a, $b) {
            if ($a[1] === $b[1]) {
                return strcmp($a[0], $b[0]);
            }
            return $b[1] <=> $a[1];
        });
        $kept = [];
        foreach ($pairs as $pair) {
            if (count($kept) >= $limit) {
                break;
            }
            $kept[] = $pair;
        }
        return $kept;
    }
""")

WORDS_REPORT = textwrap.dedent("""\
    <?php

    function renderWords(array $rows, int $distinct): string
    {
        $lines = [];
        $lines[] = "word report";
        $lines[] = "distinct: " . $distinct;
        foreach ($rows as $row) {
            $lines[] = $row[0] . " " . $row[1];
        }
        return implode(PHP_EOL, $lines);
    }
""")

WORDS_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/words.php';
    require_once __DIR__ . '/report.php';

    $counts = tally(tokenise(PASSAGE));
    echo renderWords(leaderboard($counts, 4), count($counts)) . PHP_EOL;
""")

COINS_COINS = textwrap.dedent("""\
    <?php

    const AMOUNTS = [413, 1287, 99, 640, 2505];
    const COINS = [200, 100, 50, 20, 10, 5, 2, 1];

    function changeFor(int $cents): array
    {
        $left = $cents;
        $used = [];
        foreach (COINS as $coin) {
            $count = intdiv($left, $coin);
            if ($count > 0) {
                $used[] = [$coin, $count];
                $left -= $count * $coin;
            }
        }
        return $used;
    }

    function summariseCoins(array $amounts): array
    {
        $total = 0;
        $pieces = 0;
        $largest = 0;
        foreach ($amounts as $amount) {
            $total += $amount;
            $used = changeFor($amount);
            foreach ($used as $entry) {
                $pieces += $entry[1];
            }
            if ($amount > $largest) {
                $largest = $amount;
            }
        }
        return [
            "amounts" => count($amounts),
            "total" => $total,
            "pieces" => $pieces,
            "largest" => $largest,
        ];
    }
""")

COINS_REPORT = textwrap.dedent("""\
    <?php

    function coins(int $cents): string
    {
        return sprintf('%d.%02d', intdiv($cents, 100), $cents % 100);
    }

    function renderTill(array $summary, array $change): string
    {
        $lines = [];
        $lines[] = "till report";
        $lines[] = "amounts: " . $summary["amounts"];
        $lines[] = "total: " . coins($summary["total"]);
        $lines[] = "pieces: " . $summary["pieces"];
        foreach ($change as $entry) {
            $lines[] = coins($entry[0]) . " x" . $entry[1];
        }
        return implode(PHP_EOL, $lines);
    }
""")

COINS_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/coins.php';
    require_once __DIR__ . '/report.php';

    echo renderTill(summariseCoins(AMOUNTS), changeFor(AMOUNTS[1])) . PHP_EOL;
""")


TICKETS_PRICES = textwrap.dedent("""\
    <?php

    const SEATS = [
        ["row a", 6, "stalls"],
        ["row b", 4, "circle"],
        ["row c", 9, "stalls"],
        ["row d", 2, "balcony"],
        ["row e", 7, "circle"],
    ];

    function priceFor(string $zone, int $seats): int
    {
        if ($zone === "stalls") {
            $base = 4500;
        } elseif ($zone === "circle") {
            $base = 3200;
        } else {
            $base = 1800;
        }
        if ($seats >= 8) {
            return intdiv($base * 85, 100);
        }
        return $base;
    }

    function summariseTickets(array $groups): array
    {
        $rows = [];
        $total = 0;
        $sold = 0;
        $zones = [];
        foreach ($groups as $group) {
            $zone = $group[2];
            $seats = $group[1];
            $price = priceFor($zone, $seats);
            $worth = $price * $seats;
            $total += $worth;
            $sold += $seats;
            if (isset($zones[$zone])) {
                $zones[$zone] += $seats;
            } else {
                $zones[$zone] = $seats;
            }
            $rows[] = [$group[0], $seats, $zone, $price, $worth];
        }
        return ["rows" => $rows, "total" => $total, "sold" => $sold, "zones" => $zones];
    }
""")

TICKETS_REPORT = textwrap.dedent("""\
    <?php

    function ticketMoney(int $cents): string
    {
        return sprintf('$%d.%02d', intdiv($cents, 100), $cents % 100);
    }

    function renderTickets(array $summary): string
    {
        $lines = [];
        $lines[] = "ticket report";
        $lines[] = "seats: " . $summary["sold"];
        foreach ($summary["rows"] as $row) {
            $lines[] = $row[0] . " " . $row[1] . " " . $row[2] . " "
                . ticketMoney($row[3]) . " " . ticketMoney($row[4]);
        }
        $zones = $summary["zones"];
        ksort($zones);
        foreach ($zones as $zone => $count) {
            $lines[] = "zone " . $zone . ": " . $count;
        }
        $lines[] = "total: " . ticketMoney($summary["total"]);
        return implode(PHP_EOL, $lines);
    }
""")

TICKETS_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/prices.php';
    require_once __DIR__ . '/report.php';

    echo renderTickets(summariseTickets(SEATS)) . PHP_EOL;
""")

ROMANS_DATA = textwrap.dedent("""\
    <?php

    const NUMBERS = [1987, 2024, 49, 9, 444, 1666];
    const ROMAN_UNITS = [
        [1000, "M"], [900, "CM"], [500, "D"], [400, "CD"],
        [100, "C"], [90, "XC"], [50, "L"], [40, "XL"],
        [10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"],
    ];

    function toRoman(int $value): string
    {
        $left = $value;
        $out = "";
        foreach (ROMAN_UNITS as $unit) {
            while ($left >= $unit[0]) {
                $out .= $unit[1];
                $left -= $unit[0];
            }
        }
        return $out;
    }

    function summariseRomans(array $values): array
    {
        $rows = [];
        $longest = 0;
        $letters = 0;
        foreach ($values as $value) {
            $text = toRoman($value);
            $length = strlen($text);
            if ($length > $longest) {
                $longest = $length;
            }
            $letters += $length;
            $rows[] = [$value, $text];
        }
        return ["rows" => $rows, "longest" => $longest, "letters" => $letters,
            "count" => count($values)];
    }
""")

ROMANS_REPORT = textwrap.dedent("""\
    <?php

    function renderRomans(array $summary): string
    {
        $lines = [];
        $lines[] = "roman report";
        $lines[] = "count: " . $summary["count"];
        $lines[] = "longest: " . $summary["longest"];
        $lines[] = "letters: " . $summary["letters"];
        foreach ($summary["rows"] as $row) {
            $lines[] = str_pad((string) $row[0], 5, " ", STR_PAD_LEFT) . " " . $row[1];
        }
        return implode(PHP_EOL, $lines);
    }
""")

ROMANS_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/romans.php';
    require_once __DIR__ . '/report.php';

    echo renderRomans(summariseRomans(NUMBERS)) . PHP_EOL;
""")

MATRIX_GRID = textwrap.dedent("""\
    <?php

    const GRID = [
        [1, 2, 3, 4],
        [5, 6, 7, 8],
        [9, 10, 11, 12],
    ];

    function transposeGrid(array $rows): array
    {
        if (count($rows) === 0) {
            return [];
        }
        $columns = count($rows[0]);
        $out = [];
        for ($column = 0; $column < $columns; $column++) {
            $line = [];
            foreach ($rows as $row) {
                if ($column < count($row)) {
                    $line[] = $row[$column];
                }
            }
            $out[] = $line;
        }
        return $out;
    }

    function summariseGrid(array $rows): array
    {
        $grid = transposeGrid($rows);
        $totals = [];
        $widest = 0;
        foreach ($grid as $line) {
            $total = 0;
            foreach ($line as $value) {
                $total += $value;
            }
            if ($total > $widest) {
                $widest = $total;
            }
            $totals[] = $total;
        }
        return ["grid" => $grid, "totals" => $totals, "widest" => $widest,
            "rows" => count($rows), "columns" => count($grid)];
    }
""")

MATRIX_REPORT = textwrap.dedent("""\
    <?php

    function renderGrid(array $summary): string
    {
        $lines = [];
        $lines[] = "matrix report";
        $lines[] = "rows: " . $summary["rows"];
        $lines[] = "columns: " . $summary["columns"];
        foreach ($summary["grid"] as $index => $line) {
            $text = "";
            foreach ($line as $value) {
                $text .= str_pad((string) $value, 4, " ", STR_PAD_LEFT);
            }
            $lines[] = trim($text) . "  total " . $summary["totals"][$index];
        }
        $lines[] = "widest: " . $summary["widest"];
        return implode(PHP_EOL, $lines);
    }
""")

MATRIX_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/matrix.php';
    require_once __DIR__ . '/report.php';

    echo renderGrid(summariseGrid(GRID)) . PHP_EOL;
""")

RUNS_RLE = textwrap.dedent("""\
    <?php

    const SAMPLE_TEXT = "aaabbccccdddeeffffgghhhhhh";

    function encodeRuns(string $text): array
    {
        $out = [];
        $length = strlen($text);
        if ($length === 0) {
            return $out;
        }
        $current = $text[0];
        $count = 1;
        for ($i = 1; $i < $length; $i++) {
            $ch = $text[$i];
            if ($ch === $current) {
                $count += 1;
            } else {
                $out[] = [$current, $count];
                $current = $ch;
                $count = 1;
            }
        }
        $out[] = [$current, $count];
        return $out;
    }

    function decodeRuns(array $pairs): string
    {
        $out = "";
        foreach ($pairs as $pair) {
            $out .= str_repeat($pair[0], $pair[1]);
        }
        return $out;
    }

    function summariseRuns(string $text): array
    {
        $pairs = encodeRuns($text);
        $longest = 0;
        $compact = "";
        foreach ($pairs as $pair) {
            if ($pair[1] > $longest) {
                $longest = $pair[1];
            }
            $compact .= $pair[0] . $pair[1];
        }
        return ["pairs" => $pairs, "runs" => count($pairs), "longest" => $longest,
            "compact" => $compact, "round_trip" => decodeRuns($pairs) === $text];
    }
""")

RUNS_REPORT = textwrap.dedent("""\
    <?php

    function renderRuns(array $summary): string
    {
        $lines = [];
        $lines[] = "run length report";
        $lines[] = "runs: " . $summary["runs"];
        $lines[] = "longest: " . $summary["longest"];
        $lines[] = "compact: " . $summary["compact"];
        $lines[] = "round trip: " . ($summary["round_trip"] ? "ok" : "broken");
        foreach ($summary["pairs"] as $pair) {
            $lines[] = "  " . $pair[0] . " x" . $pair[1];
        }
        return implode(PHP_EOL, $lines);
    }
""")

RUNS_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/rle.php';
    require_once __DIR__ . '/report.php';

    echo renderRuns(summariseRuns(SAMPLE_TEXT)) . PHP_EOL;
""")

LEDGER_DATA = textwrap.dedent("""\
    <?php

    const ENTRIES = [
        ["open", 50000],
        ["rent", -32000],
        ["sales", 18400],
        ["tools", -9250],
        ["refund", -4100],
        ["sales", 7600],
    ];

    function summariseLedger(array $entries, int $floor = 0): array
    {
        $rows = [];
        $balance = 0;
        $lowest = 0;
        $peak = 0;
        $overdraw = 0;
        foreach ($entries as $entry) {
            $balance += $entry[1];
            $status = "ok";
            if ($balance < $floor) {
                $status = "overdrawn";
                $overdraw += 1;
            }
            if ($balance < $lowest) {
                $lowest = $balance;
            }
            if ($balance > $peak) {
                $peak = $balance;
            }
            $rows[] = [$entry[0], $entry[1], $balance, $status];
        }
        return ["rows" => $rows, "balance" => $balance, "lowest" => $lowest,
            "peak" => $peak, "overdraw" => $overdraw];
    }
""")

LEDGER_REPORT = textwrap.dedent("""\
    <?php

    function ledgerMoney(int $cents): string
    {
        $sign = $cents < 0 ? "-" : "";
        $value = abs($cents);
        return $sign . sprintf('$%d.%02d', intdiv($value, 100), $value % 100);
    }

    function renderLedger(array $summary): string
    {
        $lines = [];
        $lines[] = "ledger report";
        $lines[] = "entries: " . count($summary["rows"]);
        foreach ($summary["rows"] as $row) {
            $lines[] = str_pad($row[0], 8) . str_pad(ledgerMoney($row[1]), 11, " ", STR_PAD_LEFT)
                . str_pad(ledgerMoney($row[2]), 12, " ", STR_PAD_LEFT) . "  " . $row[3];
        }
        $lines[] = "balance: " . ledgerMoney($summary["balance"]);
        $lines[] = "lowest: " . ledgerMoney($summary["lowest"]);
        $lines[] = "peak: " . ledgerMoney($summary["peak"]);
        $lines[] = "overdraw: " . $summary["overdraw"];
        return implode(PHP_EOL, $lines);
    }
""")

LEDGER_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/ledger.php';
    require_once __DIR__ . '/report.php';

    echo renderLedger(summariseLedger(ENTRIES)) . PHP_EOL;
""")

UNITS_DATA = textwrap.dedent("""\
    <?php

    const MILES = [1, 5, 12, 26, 40, 55, 73, 90];

    function convertRow(int $miles): array
    {
        $km = intdiv($miles * 1609, 1000);
        $feet = $miles * 5280;
        if ($miles >= 50) {
            $label = "long";
        } elseif ($miles >= 20) {
            $label = "medium";
        } else {
            $label = "short";
        }
        return [$miles, $km, $feet, $label];
    }

    function summariseUnits(array $miles): array
    {
        $rows = [];
        $totalKm = 0;
        $longest = 0;
        $labels = [];
        foreach ($miles as $value) {
            $row = convertRow($value);
            $totalKm += $row[1];
            if ($row[1] > $longest) {
                $longest = $row[1];
            }
            $label = $row[3];
            if (isset($labels[$label])) {
                $labels[$label] += 1;
            } else {
                $labels[$label] = 1;
            }
            $rows[] = $row;
        }
        return ["rows" => $rows, "total_km" => $totalKm, "longest" => $longest,
            "labels" => $labels];
    }
""")

UNITS_REPORT = textwrap.dedent("""\
    <?php

    function renderUnits(array $summary): string
    {
        $lines = [];
        $lines[] = "unit report";
        $lines[] = "total km: " . $summary["total_km"];
        $lines[] = "longest km: " . $summary["longest"];
        foreach ($summary["rows"] as $row) {
            $lines[] = str_pad((string) $row[0], 4, " ", STR_PAD_LEFT) . " mi "
                . str_pad((string) $row[1], 6, " ", STR_PAD_LEFT) . " km "
                . str_pad((string) $row[2], 8, " ", STR_PAD_LEFT) . " ft " . $row[3];
        }
        $labels = $summary["labels"];
        ksort($labels);
        foreach ($labels as $label => $count) {
            $lines[] = "label " . $label . ": " . $count;
        }
        return implode(PHP_EOL, $lines);
    }
""")

UNITS_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/units.php';
    require_once __DIR__ . '/report.php';

    echo renderUnits(summariseUnits(MILES)) . PHP_EOL;
""")

ISBN_DATA = textwrap.dedent("""\
    <?php

    const CODES = [
        "0306406152",
        "0306406153",
        "080442957X",
        "0131103629",
        "0262033844",
        "020161622X",
    ];

    function cleanCode(string $code): string
    {
        $text = strtoupper(trim($code));
        return str_replace([" ", "-"], "", $text);
    }

    function checkDigit(string $body): string
    {
        $total = 0;
        $position = 1;
        foreach (str_split($body) as $ch) {
            if (preg_match('/[0-9]/', $ch) !== 1) {
                return "";
            }
            $total += intval($ch) * $position;
            $position += 1;
        }
        $value = $total % 11;
        if ($value === 10) {
            return "X";
        }
        return (string) $value;
    }

    function validate(array $codes): array
    {
        $rows = [];
        $valid = 0;
        $invalid = 0;
        foreach ($codes as $code) {
            $text = cleanCode($code);
            if (strlen($text) !== 10) {
                $rows[] = [$text, "?", false, "length"];
                $invalid += 1;
                continue;
            }
            $expected = checkDigit(substr($text, 0, 9));
            $actual = substr($text, 9, 1);
            $ok = $expected !== "" && $expected === $actual;
            if ($ok) {
                $valid += 1;
            } else {
                $invalid += 1;
            }
            $rows[] = [$text, $expected, $ok, $ok ? "ok" : "check " . $actual];
        }
        return ["rows" => $rows, "valid" => $valid, "invalid" => $invalid];
    }
""")

ISBN_REPORT = textwrap.dedent("""\
    <?php

    function renderIsbn(array $summary): string
    {
        $lines = [];
        $lines[] = "isbn report";
        $lines[] = "codes: " . count($summary["rows"]);
        foreach ($summary["rows"] as $row) {
            $verdict = $row[2] ? "valid" : "invalid";
            $lines[] = $row[0] . " expect " . $row[1] . " " . $verdict
                . " (" . $row[3] . ")";
        }
        $lines[] = "valid: " . $summary["valid"];
        $lines[] = "invalid: " . $summary["invalid"];
        return implode(PHP_EOL, $lines);
    }
""")

ISBN_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/isbn.php';
    require_once __DIR__ . '/report.php';

    echo renderIsbn(validate(CODES)) . PHP_EOL;
""")

VENDING_STOCK = textwrap.dedent("""\
    <?php

    const PURCHASES = [
        ["cola", 175, 200],
        ["crisps", 120, 200],
        ["bar", 95, 100],
        ["water", 60, 100],
        ["juice", 210, 500],
    ];
    const COINS = [200, 100, 50, 20, 10, 5];

    function changeFor(int $cents): array
    {
        $left = $cents;
        $used = [];
        foreach (COINS as $coin) {
            $count = intdiv($left, $coin);
            if ($count > 0) {
                $used[$coin] = $count;
                $left -= $count * $coin;
            }
        }
        return $used;
    }

    function dispense(array $purchases): array
    {
        $rows = [];
        $taken = 0;
        $returned = 0;
        $pieces = 0;
        $short = 0;
        foreach ($purchases as $purchase) {
            $name = $purchase[0];
            $price = $purchase[1];
            $paid = $purchase[2];
            if ($paid < $price) {
                $short += 1;
                $rows[] = [$name, $price, $paid, -1, [], "short " . ($price - $paid)];
                continue;
            }
            $change = changeFor($paid - $price);
            $taken += $price;
            $returned += $paid - $price;
            foreach ($change as $count) {
                $pieces += $count;
            }
            $rows[] = [$name, $price, $paid, $paid - $price, $change, "ok"];
        }
        return ["rows" => $rows, "taken" => $taken, "returned" => $returned,
            "pieces" => $pieces, "short" => $short];
    }
""")

VENDING_REPORT = textwrap.dedent("""\
    <?php

    function vendorMoney(int $cents): string
    {
        return sprintf('%d.%02d', intdiv($cents, 100), $cents % 100);
    }

    function renderVending(array $summary): string
    {
        $lines = [];
        $lines[] = "vending report";
        foreach ($summary["rows"] as $row) {
            $line = $row[0] . " price " . vendorMoney($row[1])
                . " paid " . vendorMoney($row[2]);
            if ($row[3] >= 0) {
                $line .= " change " . vendorMoney($row[3]);
                $parts = [];
                foreach ($row[4] as $coin => $count) {
                    $parts[] = $coin . "x" . $count;
                }
                $line .= " in " . implode(",", $parts);
            }
            $lines[] = $line . " " . $row[5];
        }
        $lines[] = "taken: " . vendorMoney($summary["taken"]);
        $lines[] = "returned: " . vendorMoney($summary["returned"]);
        $lines[] = "pieces: " . $summary["pieces"];
        $lines[] = "short: " . $summary["short"];
        return implode(PHP_EOL, $lines);
    }
""")

VENDING_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/stock.php';
    require_once __DIR__ . '/report.php';

    echo renderVending(dispense(PURCHASES)) . PHP_EOL;
""")

INTEREST_DATA = textwrap.dedent("""\
    <?php

    const ACCOUNTS = [
        ["starter", 100000, 250, 3],
        ["growth", 250000, 475, 5],
        ["saver", 50000, 125, 7],
        ["bonus", 1000000, 310, 4],
    ];

    function project(int $principal, int $rate, int $years): array
    {
        $rows = [];
        $balance = $principal;
        $interest = 0;
        for ($year = 1; $year <= $years; $year++) {
            $gain = intdiv($balance * $rate, 1000);
            $balance += $gain;
            $interest += $gain;
            $band = "steady";
            if ($balance >= 1000000) {
                $band = "premium";
            } elseif ($balance >= 300000) {
                $band = "solid";
            }
            $rows[] = [$year, $balance, $gain, $band];
        }
        return ["rows" => $rows, "balance" => $balance, "interest" => $interest];
    }

    function summariseAccounts(array $accounts): array
    {
        $rows = [];
        $best = "";
        $bestInterest = 0;
        $totalInterest = 0;
        $premiumYears = 0;
        foreach ($accounts as $account) {
            $name = $account[0];
            $result = project($account[1], $account[2], $account[3]);
            $totalInterest += $result["interest"];
            if ($result["interest"] > $bestInterest) {
                $bestInterest = $result["interest"];
                $best = $name;
            }
            foreach ($result["rows"] as $year) {
                if ($year[3] === "premium") {
                    $premiumYears += 1;
                }
            }
            $rows[] = [$name, $account[1], $account[2], $account[3],
                $result["balance"], $result["interest"]];
        }
        return ["rows" => $rows, "best" => $best, "best_interest" => $bestInterest,
            "total_interest" => $totalInterest, "premium_years" => $premiumYears];
    }
""")

INTEREST_REPORT = textwrap.dedent("""\
    <?php

    function accountMoney(int $cents): string
    {
        return sprintf('%d.%02d', intdiv($cents, 100), $cents % 100);
    }

    function renderInterest(array $summary): string
    {
        $lines = [];
        $lines[] = "interest report";
        foreach ($summary["rows"] as $row) {
            $lines[] = str_pad($row[0], 8) . " principal " . accountMoney($row[1])
                . " rate " . $row[2] . "/1000"
                . " years " . $row[3]
                . " final " . accountMoney($row[4])
                . " interest " . accountMoney($row[5]);
        }
        $lines[] = "best: " . $summary["best"] . " "
            . accountMoney($summary["best_interest"]);
        $lines[] = "total interest: " . accountMoney($summary["total_interest"]);
        $lines[] = "premium years: " . $summary["premium_years"];
        return implode(PHP_EOL, $lines);
    }
""")

INTEREST_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/accounts.php';
    require_once __DIR__ . '/report.php';

    echo renderInterest(summariseAccounts(ACCOUNTS)) . PHP_EOL;
""")

TALLY_DATA = textwrap.dedent("""\
    <?php

    const BALLOTS = [
        "ada", "bo", "ada", "cy", "ada", "bo", "dee", "ada",
        "cy", "bo", "ada", "dee", "bo", "bo",
    ];

    function tally(array $ballots): array
    {
        $counts = [];
        foreach ($ballots as $name) {
            $key = strtolower(trim($name));
            if ($key === "") {
                continue;
            }
            if (isset($counts[$key])) {
                $counts[$key] += 1;
            } else {
                $counts[$key] = 1;
            }
        }
        arsort($counts);
        return $counts;
    }

    function result(array $counts, int $total): array
    {
        $rows = [];
        $winner = "";
        $top = 0;
        $tie = false;
        foreach ($counts as $name => $votes) {
            $share = $total > 0 ? intdiv($votes * 1000, $total) : 0;
            if ($votes > $top) {
                $top = $votes;
                $winner = $name;
                $tie = false;
            } elseif ($votes === $top) {
                $tie = true;
            }
            $rows[] = [$name, $votes, $share];
        }
        return ["rows" => $rows, "winner" => $winner, "top" => $top,
            "tie" => $tie, "majority" => $total > 0 && $top * 2 > $total,
            "total" => $total];
    }
""")

TALLY_REPORT = textwrap.dedent("""\
    <?php

    function percent(int $permille): string
    {
        return intdiv($permille, 10) . "." . ($permille % 10) . "%";
    }

    function renderTally(array $summary): string
    {
        $lines = [];
        $lines[] = "tally report";
        $lines[] = "ballots: " . $summary["total"];
        foreach ($summary["rows"] as $row) {
            $lines[] = str_pad($row[0], 6) . str_pad((string) $row[1], 4, " ", STR_PAD_LEFT)
                . " " . percent($row[2]);
        }
        $lines[] = "winner: " . ($summary["tie"] ? "tie" : $summary["winner"]);
        $lines[] = "majority: " . ($summary["majority"] ? "yes" : "no");
        return implode(PHP_EOL, $lines);
    }
""")

TALLY_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/ballots.php';
    require_once __DIR__ . '/report.php';

    $counts = tally(BALLOTS);
    echo renderTally(result($counts, count(BALLOTS))) . PHP_EOL;
""")

SEARCH_DATA = textwrap.dedent("""\
    <?php

    const VALUES = [2, 4, 6, 8, 10, 12, 14];
    const TARGETS = [8, 5];

    function probe(array $values, int $target): array
    {
        $lines = [];
        $low = 0;
        $high = count($values) - 1;
        while ($low <= $high) {
            $mid = $low + intdiv($high - $low, 2);
            $lines[] = "probe " . $mid . " value " . $values[$mid];
            if ($values[$mid] === $target) {
                $lines[] = "found " . $target . " at index " . $mid;
                return $lines;
            }
            if ($values[$mid] < $target) {
                $low = $mid + 1;
            } else {
                $high = $mid - 1;
            }
        }
        $lines[] = "not found " . $target;
        return $lines;
    }

    function traceSearch(array $values, array $targets): array
    {
        $rows = [];
        foreach ($targets as $target) {
            $rows[] = "search " . $target;
            foreach (probe($values, $target) as $line) {
                $rows[] = $line;
            }
        }
        return $rows;
    }
""")

SEARCH_REPORT = textwrap.dedent("""\
    <?php

    function renderSearch(array $rows): string
    {
        return implode(PHP_EOL, $rows);
    }
""")

SEARCH_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/search.php';
    require_once __DIR__ . '/report.php';

    echo renderSearch(traceSearch(VALUES, TARGETS)) . PHP_EOL;
""")

CACHE_DATA = textwrap.dedent("""\
    <?php

    const CAPACITY = 2;
    const OPS = [
        ["get", "a"],
        ["put", "b"],
        ["get", "a"],
        ["put", "c"],
        ["get", "b"],
        ["get", "a"],
    ];

    function mark_used(array $order, string $key): array
    {
        $kept = [];
        foreach ($order as $entry) {
            if ($entry !== $key) {
                $kept[] = $entry;
            }
        }
        $kept[] = $key;
        return $kept;
    }

    function replay(array $ops, int $capacity): array
    {
        $lines = [];
        $order = [];
        $present = [];
        foreach ($ops as $op) {
            $kind = $op[0];
            $key = $op[1];
            if ($kind === "get" && isset($present[$key])) {
                $order = mark_used($order, $key);
                $lines[] = "get " . $key . " hit";
                continue;
            }
            if ($kind === "get") {
                $lines[] = "get " . $key . " miss";
                // A miss with room is remembered, so asking twice for the same
                // key is answered from the cache the second time. A full cache
                // cannot hold the answer, so it is not stored.
                if (count($order) < $capacity) {
                    $present[$key] = true;
                    $order = mark_used($order, $key);
                }
                continue;
            }
            $lines[] = "put " . $key;
            $present[$key] = true;
            $order = mark_used($order, $key);
            while (count($order) > $capacity) {
                $old = array_shift($order);
                unset($present[$old]);
                $lines[count($lines) - 1] .= " evict " . $old;
            }
        }
        return $lines;
    }
""")

CACHE_REPORT = textwrap.dedent("""\
    <?php

    function renderCache(array $rows): string
    {
        return implode(PHP_EOL, $rows);
    }
""")

CACHE_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/cache.php';
    require_once __DIR__ . '/report.php';

    echo renderCache(replay(OPS, CAPACITY)) . PHP_EOL;
""")

CHECKSUM_DATA = textwrap.dedent("""\
    <?php

    const CODES = ["0306406152", "0306406153"];

    function checkDigit(string $body): string
    {
        $total = 0;
        $weight = 10;
        foreach (str_split($body) as $ch) {
            $total += intval($ch) * $weight;
            $weight -= 1;
        }
        $value = (11 - $total % 11) % 11;
        return $value === 10 ? "X" : (string) $value;
    }

    function validateCodes(array $codes): array
    {
        $rows = [];
        foreach ($codes as $code) {
            $expected = checkDigit(substr($code, 0, 9));
            $actual = substr($code, 9, 1);
            $rows[] = [$code, $expected, $expected === $actual];
        }
        return $rows;
    }
""")

CHECKSUM_REPORT = textwrap.dedent("""\
    <?php

    function renderCodes(array $rows): string
    {
        $lines = [];
        foreach ($rows as $row) {
            $verdict = $row[2] ? "valid" : "invalid";
            $lines[] = $row[0] . " " . $verdict . " check " . $row[1];
        }
        return implode(PHP_EOL, $lines);
    }
""")

CHECKSUM_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/checksum.php';
    require_once __DIR__ . '/report.php';

    echo renderCodes(validateCodes(CODES)) . PHP_EOL;
""")

CHANGE_DATA = textwrap.dedent("""\
    <?php

    const PURCHASES = [[65, 100], [130, 200]];
    const COIN_UNITS = [50, 25, 20, 10];

    function changeFor(int $cents): array
    {
        $left = $cents;
        $used = [];
        foreach (COIN_UNITS as $coin) {
            $count = intdiv($left, $coin);
            if ($count > 0) {
                $used[] = [$coin, $count];
                $left -= $count * $coin;
            }
        }
        return $used;
    }

    function dispense(array $purchases): array
    {
        $rows = [];
        foreach ($purchases as $purchase) {
            $price = $purchase[0];
            $paid = $purchase[1];
            $change = $paid - $price;
            $rows[] = ["price " . $price . " paid " . $paid . " change " . $change,
                changeFor($change)];
        }
        return $rows;
    }
""")

CHANGE_REPORT = textwrap.dedent("""\
    <?php

    function renderChange(array $rows): string
    {
        $lines = [];
        foreach ($rows as $row) {
            $lines[] = $row[0];
            foreach ($row[1] as $coin) {
                $lines[] = $coin[1] . " x " . $coin[0];
            }
        }
        return implode(PHP_EOL, $lines);
    }
""")

CHANGE_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/change.php';
    require_once __DIR__ . '/report.php';

    echo renderChange(dispense(PURCHASES)) . PHP_EOL;
""")

LIFE_DATA = textwrap.dedent("""\
    <?php

    const SIZE = 4;
    const LIVE_CELLS = [[0, 1], [1, 1], [2, 1]];

    function board(array $live): array
    {
        $grid = [];
        for ($row = 0; $row < SIZE; $row++) {
            $line = [];
            for ($column = 0; $column < SIZE; $column++) {
                $line[] = 0;
            }
            $grid[] = $line;
        }
        foreach ($live as $cell) {
            $grid[$cell[0]][$cell[1]] = 1;
        }
        return $grid;
    }

    function neighbours(array $grid, int $row, int $column): int
    {
        $count = 0;
        for ($dr = -1; $dr <= 1; $dr++) {
            for ($dc = -1; $dc <= 1; $dc++) {
                if ($dr === 0 && $dc === 0) {
                    continue;
                }
                $r = $row + $dr;
                $c = $column + $dc;
                if ($r < 0 || $c < 0 || $r >= SIZE || $c >= SIZE) {
                    continue;
                }
                $count += $grid[$r][$c];
            }
        }
        return $count;
    }

    function step(array $grid): array
    {
        $next = [];
        for ($row = 0; $row < SIZE; $row++) {
            $line = [];
            for ($column = 0; $column < SIZE; $column++) {
                $alive = neighbours($grid, $row, $column);
                $cell = $grid[$row][$column];
                $line[] = ($cell === 1 && ($alive === 2 || $alive === 3))
                    || ($cell === 0 && $alive === 3) ? 1 : 0;
            }
            $next[] = $line;
        }
        return $next;
    }

    function liveCount(array $grid): int
    {
        $count = 0;
        foreach ($grid as $line) {
            foreach ($line as $cell) {
                $count += $cell;
            }
        }
        return $count;
    }
""")

LIFE_REPORT = textwrap.dedent("""\
    <?php

    function renderLife(array $grid): string
    {
        $lines = [];
        foreach ($grid as $line) {
            $lines[] = "row " . implode("", $line);
        }
        $lines[] = "live " . liveCount($grid);
        return implode(PHP_EOL, $lines);
    }
""")

LIFE_MAIN = textwrap.dedent("""\
    <?php

    require_once __DIR__ . '/life.php';
    require_once __DIR__ . '/report.php';

    echo renderLife(step(board(LIVE_CELLS))) . PHP_EOL;
""")


def _set(title: str, description: str, family: str, main: str, target: str,
         formatter: str, target_path: str, formatter_path: str) -> dict:
    return {
        "title": title,
        "description": description,
        "family": family,
        "files": [
            {"path": "main.php", "content": main},
            {"path": target_path, "content": target},
            {"path": formatter_path, "content": formatter},
        ],
        "target": target_path,
    }


def sets() -> list[dict]:
    """Eighteen php sets: invoices, a word leaderboard, a till count, tickets,
    numerals, a transposed grid, run-length encoding, a ledger, units, ISBN
    checksums, a vending machine, compound interest, an election tally, a binary
    search trace, an LRU cache, a check digit, coin change and a life step."""
    return [
        _set("php cli set - invoice totals by tax band",
             "Reads embedded invoice lines, applies a banded tax rate, and prints "
             "the subtotal, tax and total.",
             "invoice", INVOICE_MAIN, INVOICE_INVENTORY, INVOICE_REPORT,
             "inventory.php", "report.php"),
        _set("php cli set - word frequency leaderboard",
             "Tallies the words of an embedded passage and prints the distinct "
             "count plus the four most frequent words.",
             "words", WORDS_MAIN, WORDS_WORDS, WORDS_REPORT,
             "words.php", "report.php"),
        _set("php cli set - till total and coin change",
             "Counts the coins needed for each embedded amount and prints the "
             "total, the piece count and the change for one amount.",
             "till", COINS_MAIN, COINS_COINS, COINS_REPORT,
             "coins.php", "report.php"),
        _set("php cli set - ticket prices by zone",
             "Prices embedded seat groups by zone with a group discount and prints "
             "each row, the seats per zone and the total.",
             "tickets", TICKETS_MAIN, TICKETS_PRICES, TICKETS_REPORT,
             "prices.php", "report.php"),
        _set("php cli set - roman numeral table",
             "Converts embedded numbers with the subtractive rules and prints each "
             "numeral with the longest and total letter counts.",
             "roman", ROMANS_MAIN, ROMANS_DATA, ROMANS_REPORT,
             "romans.php", "report.php"),
        _set("php cli set - matrix transpose totals",
             "Transposes an embedded grid, totals each row of the result, and "
             "prints the shape and the widest total.",
             "matrix", MATRIX_MAIN, MATRIX_GRID, MATRIX_REPORT,
             "matrix.php", "report.php"),
        _set("php cli set - run length encoding",
             "Encodes an embedded string into runs, decodes it back, and prints the "
             "run count, the longest run and the compact form.",
             "encode", RUNS_MAIN, RUNS_RLE, RUNS_REPORT,
             "rle.php", "report.php"),
        _set("php cli set - running balance ledger",
             "Posts embedded entries in order and prints the balance after each "
             "one, the lowest and peak balances, and how often it went over.",
             "ledger", LEDGER_MAIN, LEDGER_DATA, LEDGER_REPORT,
             "ledger.php", "report.php"),
        _set("php cli set - mile conversion table",
             "Converts embedded distances to kilometres and feet and prints each "
             "row, the totals and a short/medium/long label count.",
             "units", UNITS_MAIN, UNITS_DATA, UNITS_REPORT,
             "units.php", "report.php"),
        _set("php cli set - isbn checksums",
             "Validates embedded ISBN-10 codes, printing the check digit each "
             "code should carry and whether it is valid.",
             "isbn-checksum", ISBN_MAIN, ISBN_DATA, ISBN_REPORT,
             "isbn.php", "report.php"),
        _set("php cli set - vending machine change",
             "Dispenses change for embedded purchases with a coin count per "
             "denomination and prints the takings and the coins returned.",
             "vending-change", VENDING_MAIN, VENDING_STOCK, VENDING_REPORT,
             "stock.php", "report.php"),
        _set("php cli set - compound interest schedule",
             "Projects embedded accounts year by year at a permille rate and "
             "prints each final balance with the interest it earned.",
             "compound-interest", INTEREST_MAIN, INTEREST_DATA, INTEREST_REPORT,
             "accounts.php", "report.php"),
        _set("php cli set - election tally",
             "Counts embedded ballots, prints each candidate's votes and share, "
             "and names the winner with whether it was a majority.",
             "election-tally", TALLY_MAIN, TALLY_DATA, TALLY_REPORT,
             "ballots.php", "report.php"),
        _set("binary search trace over a sorted list",
             "Searches an embedded sorted list for two targets and prints every "
             "probe it makes with the index it found.",
             "binary-search-trace",
             SEARCH_MAIN, SEARCH_DATA, SEARCH_REPORT,
             "search.php", "report.php"),
        _set("lru cache simulation with capacity two",
             "Replays embedded cache operations against a two-entry LRU cache and "
             "prints each hit, miss and eviction.",
             "lru-cache-simulation",
             CACHE_MAIN, CACHE_DATA, CACHE_REPORT,
             "cache.php", "report.php"),
        _set("isbn ten checksum validation",
             "Computes the ISBN-10 check digit for embedded codes and prints "
             "whether each code carries the digit it should.",
             "isbn-checksum",
             CHECKSUM_MAIN, CHECKSUM_DATA, CHECKSUM_REPORT,
             "checksum.php", "report.php"),
        _set("vending machine change by coin count",
             "Works out the change for embedded purchases with the coins needed "
             "per denomination from a greedy coin set.",
             "vending-change",
             CHANGE_MAIN, CHANGE_DATA, CHANGE_REPORT,
             "change.php", "report.php"),
        _set("conway life step on a four by four grid",
             "Takes one step of Conway's game of life on an embedded four by four "
             "grid and prints the next grid with its live count.",
             "game-of-life-step",
             LIFE_MAIN, LIFE_DATA, LIFE_REPORT,
             "life.php", "report.php"),
    ]
