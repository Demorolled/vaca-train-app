"""go.py — thirteen multi-file Go CLI sets.

Every set is `main.go` + a logic module + a report module, all `package main` in
one directory, printing a deterministic report from embedded data. The logic
module is the target, so the function a model is asked to write is the one whose
result changes what the program prints.
"""
from __future__ import annotations

import textwrap


def _content(source: str) -> str:
    return textwrap.dedent(source).strip() + "\n"


def _payroll() -> dict:
    return {
        "title": "go cli set — payroll by bracket",
        "description": "Prints gross, tax and net for each shift, then the total paid out.",
        "family": "payroll",
        "target": "payroll.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    shifts := []Shift{
                        {Name: "ada", Hours: 38, Rate: 42},
                        {Name: "grace", Hours: 45, Rate: 50},
                        {Name: "linus", Hours: 12, Rate: 60},
                        {Name: "margaret", Hours: 51, Rate: 35},
                    }
                    fmt.Print(Report(PayLines(shifts)))
                }
            """)},
            {"path": "payroll.go", "content": _content("""
                package main

                type Shift struct {
                    Name  string
                    Hours int
                    Rate  int
                }

                type PayLine struct {
                    Name  string
                    Gross int
                    Tax   int
                    Net   int
                }

                func TaxFor(gross int) int {
                    switch {
                    case gross > 3000:
                        return gross * 30 / 100
                    case gross > 1500:
                        return gross * 20 / 100
                    default:
                        return gross * 10 / 100
                    }
                }

                func PayLines(shifts []Shift) []PayLine {
                    lines := make([]PayLine, 0, len(shifts))
                    for _, shift := range shifts {
                        if shift.Hours <= 0 || shift.Rate <= 0 {
                            continue
                        }
                        gross := shift.Hours * shift.Rate
                        if shift.Hours > 40 {
                            gross += (shift.Hours - 40) * shift.Rate / 2
                        }
                        tax := TaxFor(gross)
                        net := gross - tax
                        if net < 0 {
                            net = 0
                        }
                        lines = append(lines, PayLine{Name: shift.Name, Gross: gross, Tax: tax, Net: net})
                    }
                    return lines
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func Report(lines []PayLine) string {
                    var b strings.Builder
                    b.WriteString(fmt.Sprintf("%-10s %6s %5s %6s\\n", "name", "gross", "tax", "net"))
                    total := 0
                    for _, line := range lines {
                        b.WriteString(fmt.Sprintf("%-10s %6d %5d %6d\\n", line.Name, line.Gross, line.Tax, line.Net))
                        total += line.Net
                    }
                    b.WriteString(fmt.Sprintf("%-10s %6s %5s %6d\\n", "total", "", "", total))
                    return b.String()
                }
            """)},
        ],
    }


def _grades() -> dict:
    return {
        "title": "go cli set — grade bands",
        "description": "Prints the class mean and a bar chart of letter-band counts.",
        "family": "grades",
        "target": "grades.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    scores := []Score{
                        {Student: "ada", Points: 92},
                        {Student: "grace", Points: 78},
                        {Student: "linus", Points: 64},
                        {Student: "margaret", Points: 88},
                        {Student: "edsger", Points: 55},
                        {Student: "barbara", Points: 97},
                    }
                    fmt.Print(Chart(Bands(scores), Mean(scores)))
                }
            """)},
            {"path": "grades.go", "content": _content("""
                package main

                type Score struct {
                    Student string
                    Points  int
                }

                type Band struct {
                    Label string
                    Count int
                }

                func BandFor(points int) string {
                    switch {
                    case points >= 90:
                        return "A"
                    case points >= 80:
                        return "B"
                    case points >= 70:
                        return "C"
                    case points >= 60:
                        return "D"
                    default:
                        return "F"
                    }
                }

                func Bands(scores []Score) []Band {
                    order := []string{"A", "B", "C", "D", "F"}
                    counts := make(map[string]int, len(order))
                    for _, score := range scores {
                        if score.Points < 0 {
                            continue
                        }
                        label := BandFor(score.Points)
                        counts[label]++
                    }
                    bands := make([]Band, 0, len(order))
                    for _, label := range order {
                        bands = append(bands, Band{Label: label, Count: counts[label]})
                    }
                    return bands
                }

                func Mean(scores []Score) int {
                    if len(scores) == 0 {
                        return 0
                    }
                    total := 0
                    for _, score := range scores {
                        total += score.Points
                    }
                    return total / len(scores)
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func Chart(bands []Band, mean int) string {
                    var b strings.Builder
                    b.WriteString(fmt.Sprintf("mean %d\\n", mean))
                    for _, band := range bands {
                        bar := strings.Repeat("#", band.Count)
                        b.WriteString(fmt.Sprintf("%s %-12s %d\\n", band.Label, bar, band.Count))
                    }
                    return b.String()
                }
            """)},
        ],
    }


def _schedule() -> dict:
    return {
        "title": "go cli set — merged schedule",
        "description": "Prints the free blocks left after overlapping slots are merged.",
        "family": "schedule",
        "target": "schedule.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    slots := []Slot{
                        {Start: 0, End: 3},
                        {Start: 4, End: 7},
                        {Start: 2, End: 5},
                        {Start: 9, End: 9},
                        {Start: 8, End: 10},
                    }
                    fmt.Print(Ruler(Merge(slots)))
                }
            """)},
            {"path": "schedule.go", "content": _content("""
                package main

                type Slot struct {
                    Start int
                    End   int
                }

                func Normalize(slots []Slot) []Slot {
                    kept := make([]Slot, 0, len(slots))
                    for _, slot := range slots {
                        if slot.End <= slot.Start {
                            continue
                        }
                        kept = append(kept, slot)
                    }
                    for i := 1; i < len(kept); i++ {
                        for j := i; j > 0 && kept[j].Start < kept[j-1].Start; j-- {
                            kept[j], kept[j-1] = kept[j-1], kept[j]
                        }
                    }
                    return kept
                }

                func Merge(slots []Slot) []Slot {
                    ordered := Normalize(slots)
                    merged := make([]Slot, 0, len(ordered))
                    for _, slot := range ordered {
                        if len(merged) == 0 {
                            merged = append(merged, slot)
                            continue
                        }
                        last := &merged[len(merged)-1]
                        if slot.Start <= last.End {
                            if slot.End > last.End {
                                last.End = slot.End
                            }
                            continue
                        }
                        merged = append(merged, slot)
                    }
                    return merged
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func Ruler(slots []Slot) string {
                    var b strings.Builder
                    for _, slot := range slots {
                        bar := strings.Repeat("=", slot.End-slot.Start)
                        b.WriteString(fmt.Sprintf("[%2d,%2d] %s\\n", slot.Start, slot.End, bar))
                    }
                    b.WriteString(fmt.Sprintf("%d blocks\\n", len(slots)))
                    return b.String()
                }
            """)},
        ],
    }


def _transpose() -> dict:
    return {
        "title": "go cli set — matrix transpose",
        "description": "Prints the transposed grid and the total of each printed row.",
        "family": "transpose",
        "target": "transpose.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    grid := [][]int{
                        {1, 2, 3},
                        {4, 5, 6},
                        {7, 8, 9},
                        {10, 11, 12},
                    }
                    fmt.Print(GridReport(Transpose(grid)))
                }
            """)},
            {"path": "transpose.go", "content": _content("""
                package main

                func Transpose(grid [][]int) [][]int {
                    if len(grid) == 0 {
                        return nil
                    }
                    width := 0
                    for _, row := range grid {
                        if len(row) > width {
                            width = len(row)
                        }
                    }
                    out := make([][]int, width)
                    for col := 0; col < width; col++ {
                        line := make([]int, len(grid))
                        for row := 0; row < len(grid); row++ {
                            if col < len(grid[row]) {
                                line[row] = grid[row][col]
                            }
                        }
                        out[col] = line
                    }
                    return out
                }

                func RowTotals(grid [][]int) []int {
                    totals := make([]int, len(grid))
                    for i, row := range grid {
                        sum := 0
                        for _, value := range row {
                            sum += value
                        }
                        totals[i] = sum
                    }
                    return totals
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func GridReport(grid [][]int) string {
                    var b strings.Builder
                    totals := RowTotals(grid)
                    for i, row := range grid {
                        parts := make([]string, len(row))
                        for j, value := range row {
                            parts[j] = fmt.Sprintf("%4d", value)
                        }
                        b.WriteString(fmt.Sprintf("%s %4d\\n", strings.Join(parts, ""), totals[i]))
                    }
                    b.WriteString(fmt.Sprintf("%d rows\\n", len(grid)))
                    return b.String()
                }
            """)},
        ],
    }


def _roman() -> dict:
    return {
        "title": "go cli set — roman numerals",
        "description": "Prints each number in roman numerals with its digit sum.",
        "family": "roman",
        "target": "roman.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    values := []int{1994, 49, 2024, 9, 444, 0}
                    fmt.Print(RomanReport(values))
                }
            """)},
            {"path": "roman.go", "content": _content("""
                package main

                type Numeral struct {
                    Value  int
                    Symbol string
                }

                var numerals = []Numeral{
                    {1000, "M"}, {900, "CM"}, {500, "D"}, {400, "CD"},
                    {100, "C"}, {90, "XC"}, {50, "L"}, {40, "XL"},
                    {10, "X"}, {9, "IX"}, {5, "V"}, {4, "IV"}, {1, "I"},
                }

                func ToRoman(n int) string {
                    if n <= 0 || n > 3999 {
                        return ""
                    }
                    out := ""
                    for _, numeral := range numerals {
                        for n >= numeral.Value {
                            out += numeral.Symbol
                            n -= numeral.Value
                        }
                    }
                    return out
                }

                func DigitSum(n int) int {
                    total := 0
                    for n > 0 {
                        total += n % 10
                        n /= 10
                    }
                    return total
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func RomanReport(values []int) string {
                    var b strings.Builder
                    b.WriteString(fmt.Sprintf("%5s  %-8s %s\\n", "value", "roman", "digits"))
                    for _, value := range values {
                        roman := ToRoman(value)
                        if roman == "" {
                            roman = "-"
                        }
                        b.WriteString(fmt.Sprintf("%5d  %-8s %d\\n", value, roman, DigitSum(value)))
                    }
                    return b.String()
                }
            """)},
        ],
    }


def _buckets() -> dict:
    return {
        "title": "go cli set — histogram buckets",
        "description": "Prints a bar chart of sample counts per value bucket.",
        "family": "buckets",
        "target": "buckets.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    samples := []int{12, 45, 47, 3, 88, 91, 62, 60, 59, 75, 100, 0, 104}
                    fmt.Print(BucketReport(Buckets(samples, 20), 20))
                }
            """)},
            {"path": "buckets.go", "content": _content("""
                package main

                type Bucket struct {
                    Low   int
                    High  int
                    Count int
                }

                func BucketIndex(value int, width int) int {
                    if width <= 0 || value < 0 {
                        return 0
                    }
                    index := value / width
                    if index > 99/width {
                        index = 99 / width
                    }
                    return index
                }

                func Buckets(samples []int, width int) []Bucket {
                    if width <= 0 {
                        return nil
                    }
                    out := make([]Bucket, 0, 100/width+1)
                    for low := 0; low < 100; low += width {
                        out = append(out, Bucket{Low: low, High: low + width - 1})
                    }
                    for _, value := range samples {
                        if value < 0 || value > 100 {
                            continue
                        }
                        index := BucketIndex(value, width)
                        if index >= len(out) {
                            index = len(out) - 1
                        }
                        out[index].Count++
                    }
                    return out
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func BucketReport(buckets []Bucket, width int) string {
                    var b strings.Builder
                    for _, bucket := range buckets {
                        bar := strings.Repeat("#", bucket.Count)
                        b.WriteString(fmt.Sprintf("%3d-%3d %-12s %d\\n", bucket.Low, bucket.High, bar, bucket.Count))
                    }
                    b.WriteString(fmt.Sprintf("%d buckets of %d\\n", len(buckets), width))
                    return b.String()
                }
            """)},
        ],
    }


def _units() -> dict:
    return {
        "title": "go cli set — kilometre conversion table",
        "description": "Prints kilometres converted to miles, rounded to two places.",
        "family": "units",
        "target": "units.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    km := []float64{1, 5, 10, 21.5, 42.2, -3}
                    fmt.Print(ConversionTable(km))
                }
            """)},
            {"path": "units.go", "content": _content("""
                package main

                import "math"

                type Conversion struct {
                    Kilometres float64
                    Miles      float64
                }

                func MilesPerKilometre() float64 {
                    return 0.621371
                }

                func Convert(km []float64) []Conversion {
                    factor := MilesPerKilometre()
                    out := make([]Conversion, 0, len(km))
                    for _, value := range km {
                        if value < 0 {
                            continue
                        }
                        miles := value * factor
                        if miles < 1 {
                            miles = 1
                        }
                        miles = math.Round(miles*100) / 100
                        out = append(out, Conversion{Kilometres: value, Miles: miles})
                    }
                    return out
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func ConversionTable(km []float64) string {
                    var b strings.Builder
                    b.WriteString(fmt.Sprintf("%6s  %8s\\n", "km", "miles"))
                    for _, row := range Convert(km) {
                        b.WriteString(fmt.Sprintf("%6.1f  %8.2f\\n", row.Kilometres, row.Miles))
                    }
                    return b.String()
                }
            """)},
        ],
    }


def _sieve() -> dict:
    return {
        "title": "go cli set — prime sieve by decade",
        "description": "Prints the primes below a limit and their count per decade.",
        "family": "sieve",
        "target": "sieve.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    fmt.Print(PrimeReport(Sieve(100), 100))
                }
            """)},
            {"path": "sieve.go", "content": _content("""
                package main

                func Sieve(limit int) []int {
                    if limit < 2 {
                        return nil
                    }
                    marks := make([]bool, limit+1)
                    primes := make([]int, 0, limit/4)
                    for n := 2; n <= limit; n++ {
                        if marks[n] {
                            continue
                        }
                        primes = append(primes, n)
                        for multiple := n * n; multiple <= limit; multiple += n {
                            marks[multiple] = true
                        }
                    }
                    return primes
                }

                func DecadeCounts(primes []int) []int {
                    counts := make([]int, 10)
                    for _, p := range primes {
                        decade := p / 10
                        if decade > 9 {
                            decade = 9
                        }
                        counts[decade]++
                    }
                    return counts
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func PrimeReport(primes []int, limit int) string {
                    var b strings.Builder
                    b.WriteString(fmt.Sprintf("%d primes up to %d\\n", len(primes), limit))
                    for decade, count := range DecadeCounts(primes) {
                        bar := strings.Repeat("*", count)
                        b.WriteString(fmt.Sprintf("%3d-%-3d %-14s %d\\n", decade*10, decade*10+9, bar, count))
                    }
                    return b.String()
                }
            """)},
        ],
    }


def _wrap() -> dict:
    return {
        "title": "go cli set — greedy word wrap",
        "description": "Prints a sentence wrapped to a fixed width, one numbered line each.",
        "family": "wrap",
        "target": "wrap.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    text := "the quick brown fox jumps over the lazy dog and keeps running past the fence"
                    fmt.Print(WrapReport(text, 24))
                }
            """)},
            {"path": "wrap.go", "content": _content("""
                package main

                import "strings"

                func Words(text string) []string {
                    return strings.Fields(strings.ToLower(text))
                }

                func Wrap(text string, width int) []string {
                    if width <= 0 {
                        width = 20
                    }
                    lines := make([]string, 0, 4)
                    current := ""
                    for _, word := range Words(text) {
                        if len(word) > width {
                            word = word[:width]
                        }
                        if current == "" {
                            current = word
                            continue
                        }
                        if len(current)+1+len(word) > width {
                            lines = append(lines, current)
                            current = word
                            continue
                        }
                        current += " " + word
                    }
                    if current != "" {
                        lines = append(lines, current)
                    }
                    return lines
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func WrapReport(text string, width int) string {
                    lines := Wrap(text, width)
                    var b strings.Builder
                    for i, line := range lines {
                        b.WriteString(fmt.Sprintf("%2d|%s|\\n", i+1, line))
                    }
                    b.WriteString(fmt.Sprintf("%d lines of %d\\n", len(lines), width))
                    return b.String()
                }
            """)},
        ],
    }


def _calendar() -> dict:
    return {
        "title": "go cli set — calendar facts",
        "description": "Prints leap years, days in the year and the weekday of 1 January.",
        "family": "calendar-facts",
        "target": "calendar.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    years := []int{1900, 2000, 2023, 2024, 2100, 0}
                    fmt.Print(CalendarReport(years))
                }
            """)},
            {"path": "calendar.go", "content": _content("""
                package main

                type Year struct {
                    Value   int
                    Leap    bool
                    Days    int
                    Weekday string
                }

                func IsLeap(year int) bool {
                    if year%400 == 0 {
                        return true
                    }
                    if year%100 == 0 {
                        return false
                    }
                    return year%4 == 0
                }

                func DaysIn(year int, month int) int {
                    switch month {
                    case 2:
                        if IsLeap(year) {
                            return 29
                        }
                        return 28
                    case 4, 6, 9, 11:
                        return 30
                    default:
                        return 31
                    }
                }

                func Zeller(year int, month int, day int) int {
                    y := year
                    m := month
                    if m < 3 {
                        m += 12
                        y--
                    }
                    k := y % 100
                    j := y / 100
                    h := (day + (13*(m+1))/5 + k + k/4 + j/4 + 5*j) % 7
                    return h
                }

                func WeekdayName(h int) string {
                    names := []string{"Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
                    if h < 0 || h >= len(names) {
                        return "?"
                    }
                    return names[h]
                }

                func Summaries(years []int) []Year {
                    out := make([]Year, 0, len(years))
                    for _, year := range years {
                        if year < 1 {
                            continue
                        }
                        days := 0
                        for month := 1; month <= 12; month++ {
                            days += DaysIn(year, month)
                        }
                        weekday := WeekdayName(Zeller(year, 1, 1))
                        out = append(out, Year{Value: year, Leap: IsLeap(year), Days: days, Weekday: weekday})
                    }
                    return out
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func CalendarReport(years []int) string {
                    var b strings.Builder
                    b.WriteString(fmt.Sprintf("%5s %-5s %5s %s\\n", "year", "leap", "days", "jan1"))
                    for _, row := range Summaries(years) {
                        leap := "no"
                        if row.Leap {
                            leap = "yes"
                        }
                        b.WriteString(fmt.Sprintf("%5d %-5s %5d %s\\n", row.Value, leap, row.Days, row.Weekday))
                    }
                    return b.String()
                }
            """)},
        ],
    }


def _parking() -> dict:
    return {
        "title": "go cli set — parking fees",
        "description": "Prints a fee per parking entry with the daily cap marked.",
        "family": "parking-fees",
        "target": "parking.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    entries := []Entry{
                        {Plate: "aa-01", Hours: 1, Tier: "short"},
                        {Plate: "bb-02", Hours: 5, Tier: "short"},
                        {Plate: "cc-03", Hours: 9, Tier: "long"},
                        {Plate: "dd-04", Hours: 24, Tier: "long"},
                        {Plate: "ee-05", Hours: 0, Tier: "short"},
                    }
                    fmt.Print(FeeReport(Charge(entries)))
                }
            """)},
            {"path": "parking.go", "content": _content("""
                package main

                type Entry struct {
                    Plate string
                    Hours int
                    Tier  string
                }

                type ChargeRow struct {
                    Plate  string
                    Hours  int
                    Fee    int
                    Capped bool
                }

                func Rate(tier string) int {
                    switch tier {
                    case "long":
                        return 120
                    case "short":
                        return 250
                    default:
                        return 200
                    }
                }

                func FeeFor(hours int, tier string) (int, bool) {
                    if hours <= 0 {
                        return 0, false
                    }
                    rate := Rate(tier)
                    fee := hours * rate
                    cap := 1500
                    if rate >= 200 {
                        cap = 2200
                    }
                    if fee > cap {
                        return cap, true
                    }
                    return fee, false
                }

                func Charge(entries []Entry) []ChargeRow {
                    rows := make([]ChargeRow, 0, len(entries))
                    total := 0
                    for _, entry := range entries {
                        if entry.Hours <= 0 || entry.Plate == "" {
                            continue
                        }
                        fee, capped := FeeFor(entry.Hours, entry.Tier)
                        total += fee
                        if total > 4000 {
                            total = 4000
                        }
                        rows = append(rows, ChargeRow{Plate: entry.Plate, Hours: entry.Hours, Fee: fee, Capped: capped})
                    }
                    return rows
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func FeeReport(rows []ChargeRow) string {
                    var b strings.Builder
                    b.WriteString(fmt.Sprintf("%-8s %5s %6s %s\\n", "plate", "hours", "fee", "capped"))
                    total := 0
                    for _, row := range rows {
                        mark := ""
                        if row.Capped {
                            mark = "yes"
                        }
                        total += row.Fee
                        b.WriteString(fmt.Sprintf("%-8s %5d %6d %s\\n", row.Plate, row.Hours, row.Fee, mark))
                    }
                    b.WriteString(fmt.Sprintf("%-8s %5s %6d\\n", "total", "", total))
                    return b.String()
                }
            """)},
        ],
    }


def _csvstats() -> dict:
    return {
        "title": "go cli set — csv column stats",
        "description": "Prints count, minimum, maximum and mean for each numeric column.",
        "family": "csv-column-stats",
        "target": "csvstats.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    data := "name,qty,price\\nbolt,12,2.5\\ngasket,4,12.5\\nhousing,2,89\\nwasher,40,0.15\\nshaft,,4\\n"
                    fmt.Print(ColumnReport(Columns(data)))
                }
            """)},
            {"path": "csvstats.go", "content": _content("""
                package main

                import (
                    "strconv"
                    "strings"
                )

                type Column struct {
                    Name  string
                    Count int
                    Min   float64
                    Max   float64
                    Mean  float64
                    Blank int
                }

                func Parse(text string) ([]string, [][]string) {
                    lines := strings.Split(strings.TrimSpace(text), "\\n")
                    if len(lines) == 0 || strings.TrimSpace(lines[0]) == "" {
                        return nil, nil
                    }
                    header := strings.Split(lines[0], ",")
                    rows := make([][]string, 0, len(lines)-1)
                    for _, line := range lines[1:] {
                        if strings.TrimSpace(line) == "" {
                            continue
                        }
                        rows = append(rows, strings.Split(line, ","))
                    }
                    return header, rows
                }

                func Columns(text string) []Column {
                    header, rows := Parse(text)
                    cols := make([]Column, 0, len(header))
                    for i, name := range header {
                        col := Column{Name: name}
                        sum := 0.0
                        for _, row := range rows {
                            if i >= len(row) {
                                col.Blank++
                                continue
                            }
                            value, err := strconv.ParseFloat(strings.TrimSpace(row[i]), 64)
                            if err != nil {
                                col.Blank++
                                continue
                            }
                            col.Count++
                            sum += value
                            if col.Count == 1 || value < col.Min {
                                col.Min = value
                            }
                            if col.Count == 1 || value > col.Max {
                                col.Max = value
                            }
                        }
                        if col.Count > 0 {
                            col.Mean = sum / float64(col.Count)
                        }
                        cols = append(cols, col)
                    }
                    return cols
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func ColumnReport(cols []Column) string {
                    var b strings.Builder
                    b.WriteString(fmt.Sprintf("%-8s %5s %8s %8s %8s %5s\\n", "column", "n", "min", "max", "mean", "blank"))
                    for _, col := range cols {
                        b.WriteString(fmt.Sprintf("%-8s %5d %8.2f %8.2f %8.2f %5d\\n", col.Name, col.Count, col.Min, col.Max, col.Mean, col.Blank))
                    }
                    return b.String()
                }
            """)},
        ],
    }


def _morse() -> dict:
    return {
        "title": "go cli set — morse codec",
        "description": "Encodes embedded phrases to morse and decodes them back, checking the round trip.",
        "family": "morse-codec",
        "target": "morse.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    phrases := []string{"sos help", "abc 123", ""}
                    fmt.Print(MorseReport(phrases))
                }
            """)},
            {"path": "morse.go", "content": _content("""
                package main

                import "strings"

                var morseTable = map[rune]string{
                    'a': ".-", 'b': "-...", 'c': "-.-.", 'd': "-..", 'e': ".",
                    'f': "..-.", 'g': "--.", 'h': "....", 'i': "..", 'j': ".---",
                    'k': "-.-", 'l': ".-..", 'm': "--", 'n': "-.", 'o': "---",
                    'p': ".--.", 'q': "--.-", 'r': ".-.", 's': "...", 't': "-",
                    'u': "..-", 'v': "...-", 'w': ".--", 'x': "-..-", 'y': "-.--",
                    'z': "--..", '0': "-----", '1': ".----", '2': "..---",
                    '3': "...--", '4': "....-", '5': ".....", '6': "-....",
                    '7': "--...", '8': "---..", '9': "----.",
                }

                func Encode(text string) string {
                    parts := make([]string, 0, len(text))
                    for _, r := range strings.ToLower(text) {
                        if r == ' ' {
                            parts = append(parts, "/")
                            continue
                        }
                        if code, ok := morseTable[r]; ok {
                            parts = append(parts, code)
                        }
                    }
                    return strings.Join(parts, " ")
                }

                func Decode(code string) string {
                    var b strings.Builder
                    for _, token := range strings.Fields(code) {
                        if token == "/" {
                            b.WriteString(" ")
                            continue
                        }
                        letter := "?"
                        for r, symbol := range morseTable {
                            if symbol == token {
                                letter = string(r)
                                break
                            }
                        }
                        b.WriteString(letter)
                    }
                    return b.String()
                }

                func RoundTrip(text string) bool {
                    return Decode(Encode(text)) == strings.ToLower(text)
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func MorseReport(phrases []string) string {
                    var b strings.Builder
                    for _, phrase := range phrases {
                        code := Encode(phrase)
                        status := "mismatch"
                        if RoundTrip(phrase) {
                            status = "ok"
                        }
                        if code == "" {
                            code = "-"
                        }
                        b.WriteString(fmt.Sprintf("%-8q %-26s %s\\n", phrase, code, status))
                    }
                    b.WriteString(fmt.Sprintf("%d phrases\\n", len(phrases)))
                    return b.String()
                }
            """)},
        ],
    }


def _searchtrace() -> dict:
    return {
        "title": "binary search trace over a sorted list",
        "description": "Searches a sorted list and prints every probe, then found or not found.",
        "family": "binary-search-trace",
        "target": "search.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    values := []int{2, 4, 6, 8, 10, 12, 14}
                    targets := []int{8, 5}
                    fmt.Print(SearchReport(Trace(values, targets)))
                }
            """)},
            {"path": "search.go", "content": _content("""
                package main

                import "fmt"

                func Trace(values []int, targets []int) []string {
                    lines := make([]string, 0, len(targets)*4)
                    for _, target := range targets {
                        lines = append(lines, fmt.Sprintf("search %d", target))
                        lo, hi := 0, len(values)-1
                        found := -1
                        for lo <= hi {
                            mid := lo + (hi-lo)/2
                            lines = append(lines, fmt.Sprintf("probe %d value %d", mid, values[mid]))
                            if values[mid] == target {
                                found = mid
                                break
                            }
                            if values[mid] < target {
                                lo = mid + 1
                            } else {
                                hi = mid - 1
                            }
                        }
                        if found < 0 {
                            lines = append(lines, fmt.Sprintf("not found %d", target))
                        } else {
                            lines = append(lines, fmt.Sprintf("found %d at index %d", target, found))
                        }
                    }
                    return lines
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import "strings"

                func SearchReport(lines []string) string {
                    return strings.Join(lines, "\\n") + "\\n"
                }
            """)},
        ],
    }


def _lru() -> dict:
    return {
        "title": "lru cache simulation with capacity two",
        "description": "Replays cache operations and prints hit, miss and eviction lines.",
        "family": "lru-cache-simulation",
        "target": "cache.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    ops := []Op{
                        {Kind: "get", Key: "a"},
                        {Kind: "put", Key: "b"},
                        {Kind: "get", Key: "a"},
                        {Kind: "put", Key: "c"},
                        {Kind: "get", Key: "b"},
                        {Kind: "get", Key: "a"},
                    }
                    fmt.Print(CacheReport(Play(ops, 2)))
                }
            """)},
            {"path": "cache.go", "content": _content("""
                package main

                import "fmt"

                type Op struct {
                    Kind string
                    Key  string
                }

                type slot struct {
                    key  string
                    used int
                }

                func Play(ops []Op, capacity int) []string {
                    cache := make([]slot, 0, capacity)
                    lines := make([]string, 0, len(ops))
                    clock := 0
                    for _, op := range ops {
                        clock++
                        index := -1
                        for i := range cache {
                            if cache[i].key == op.Key {
                                index = i
                                break
                            }
                        }
                        if op.Kind == "get" {
                            if index >= 0 {
                                cache[index].used = clock
                                lines = append(lines, fmt.Sprintf("get %s hit", op.Key))
                                continue
                            }
                            lines = append(lines, fmt.Sprintf("get %s miss", op.Key))
                            if len(cache) < capacity {
                                cache = append(cache, slot{key: op.Key, used: clock})
                            }
                            continue
                        }
                        if index >= 0 {
                            cache[index].used = clock
                            lines = append(lines, fmt.Sprintf("put %s", op.Key))
                            continue
                        }
                        if len(cache) < capacity {
                            cache = append(cache, slot{key: op.Key, used: clock})
                            lines = append(lines, fmt.Sprintf("put %s", op.Key))
                            continue
                        }
                        oldest := 0
                        for i := range cache {
                            if cache[i].used < cache[oldest].used {
                                oldest = i
                            }
                        }
                        lines = append(lines, fmt.Sprintf("put %s evict %s", op.Key, cache[oldest].key))
                        cache[oldest] = slot{key: op.Key, used: clock}
                    }
                    return lines
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import "strings"

                func CacheReport(lines []string) string {
                    return strings.Join(lines, "\\n") + "\\n"
                }
            """)},
        ],
    }


def _isbn() -> dict:
    return {
        "title": "isbn ten checksum validation",
        "description": "Validates ISBN-10 codes and prints the expected check digit.",
        "family": "isbn-checksum",
        "target": "isbn.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    codes := []string{"0306406152", "0306406153"}
                    fmt.Print(IsbnReport(codes))
                }
            """)},
            {"path": "isbn.go", "content": _content("""
                package main

                func CheckDigit(code string) (int, bool) {
                    sum := 0
                    for i := 0; i < 9; i++ {
                        sum += int(code[i]-'0') * (10 - i)
                    }
                    expected := (11 - sum%11) % 11
                    last := code[9]
                    if last == 'X' {
                        return expected, expected == 10
                    }
                    return expected, expected == int(last-'0')
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func IsbnReport(codes []string) string {
                    var b strings.Builder
                    for _, code := range codes {
                        expected, valid := CheckDigit(code)
                        status := "invalid"
                        if valid {
                            status = "valid"
                        }
                        digit := fmt.Sprintf("%d", expected)
                        if expected == 10 {
                            digit = "X"
                        }
                        b.WriteString(fmt.Sprintf("%s %s check %s\\n", code, status, digit))
                    }
                    return b.String()
                }
            """)},
        ],
    }


def _vending() -> dict:
    return {
        "title": "vending machine change by coin count",
        "description": "Breaks change into the fewest coins for each purchase.",
        "family": "vending-change",
        "target": "vending.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    purchases := []Purchase{
                        {Price: 65, Paid: 100},
                        {Price: 130, Paid: 200},
                    }
                    fmt.Print(ChangeReport(purchases))
                }
            """)},
            {"path": "vending.go", "content": _content("""
                package main

                import "fmt"

                var coins = []int{50, 25, 20, 10}

                type Purchase struct {
                    Price int
                    Paid  int
                }

                func Change(price int, paid int) []string {
                    lines := []string{fmt.Sprintf("price %d paid %d change %d", price, paid, paid-price)}
                    rest := paid - price
                    for _, coin := range coins {
                        count := rest / coin
                        if count == 0 {
                            continue
                        }
                        rest -= count * coin
                        lines = append(lines, fmt.Sprintf("%d x %d", count, coin))
                    }
                    if rest != 0 {
                        lines = append(lines, fmt.Sprintf("leftover %d", rest))
                    }
                    return lines
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import "strings"

                func ChangeReport(purchases []Purchase) string {
                    var b strings.Builder
                    for _, purchase := range purchases {
                        for _, line := range Change(purchase.Price, purchase.Paid) {
                            b.WriteString(line)
                            b.WriteString("\\n")
                        }
                    }
                    return b.String()
                }
            """)},
        ],
    }


def _life() -> dict:
    return {
        "title": "conway life step on a four by four grid",
        "description": "Applies one generation of Conway's life and prints the next grid.",
        "family": "game-of-life-step",
        "target": "life.go",
        "files": [
            {"path": "main.go", "content": _content("""
                package main

                import "fmt"

                func main() {
                    var grid Grid
                    grid[0][1] = true
                    grid[1][1] = true
                    grid[2][1] = true
                    fmt.Print(LifeReport(Step(grid)))
                }
            """)},
            {"path": "life.go", "content": _content("""
                package main

                type Grid [4][4]bool

                func Step(grid Grid) Grid {
                    var next Grid
                    for row := 0; row < 4; row++ {
                        for col := 0; col < 4; col++ {
                            live := 0
                            for dr := -1; dr <= 1; dr++ {
                                for dc := -1; dc <= 1; dc++ {
                                    if dr == 0 && dc == 0 {
                                        continue
                                    }
                                    r, c := row+dr, col+dc
                                    if r < 0 || c < 0 || r >= 4 || c >= 4 {
                                        continue
                                    }
                                    if grid[r][c] {
                                        live++
                                    }
                                }
                            }
                            if grid[row][col] {
                                next[row][col] = live == 2 || live == 3
                            } else {
                                next[row][col] = live == 3
                            }
                        }
                    }
                    return next
                }
            """)},
            {"path": "report.go", "content": _content("""
                package main

                import (
                    "fmt"
                    "strings"
                )

                func LifeReport(grid Grid) string {
                    var b strings.Builder
                    live := 0
                    for row := 0; row < 4; row++ {
                        b.WriteString("row ")
                        for col := 0; col < 4; col++ {
                            if grid[row][col] {
                                b.WriteString("1")
                                live++
                            } else {
                                b.WriteString("0")
                            }
                        }
                        b.WriteString("\\n")
                    }
                    b.WriteString(fmt.Sprintf("live %d\\n", live))
                    return b.String()
                }
            """)},
        ],
    }


def sets() -> list[dict]:
    return [_payroll(), _grades(), _schedule(),
            _transpose(), _roman(), _buckets(), _units(), _sieve(), _wrap(),
            _calendar(), _parking(), _csvstats(), _morse(),
            _searchtrace(), _lru(), _isbn(), _vending(), _life()]
