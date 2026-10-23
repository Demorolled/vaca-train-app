"""ruby.py — eighteen multi-file Ruby CLI sets.

Each set is `main.rb` (entry), a logic module that holds the interesting
functions, and a `report.rb` that renders rows to text. Everything is embedded
data and plain methods: no stdin, no argv, no clock, so the printed report is the
same on every run and the logic module is the target a model is asked for.
"""
from __future__ import annotations

import textwrap


def _content(source: str) -> str:
    return textwrap.dedent(source).strip() + "\n"


def _invoices() -> dict:
    return {
        "title": "ruby cli set — invoice totals",
        "description": "Prints subtotal, discount and total per invoice, largest net first.",
        "family": "invoices",
        "target": "invoices.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'invoices'
                require_relative 'report'

                invoices = [
                  Invoice.new("ada", 120, 90),
                  Invoice.new("grace", 40, 250),
                  Invoice.new("linus", 300, 12),
                  Invoice.new("margaret", 15, 600)
                ]

                puts render_invoices(invoice_lines(invoices))
            """)},
            {"path": "invoices.rb", "content": _content("""
                Invoice = Struct.new(:customer, :units, :price)

                Line = Struct.new(:customer, :subtotal, :discount, :total)

                def discount_for(subtotal)
                  if subtotal >= 20_000
                    0.15
                  elsif subtotal >= 10_000
                    0.10
                  elsif subtotal >= 5_000
                    0.05
                  else
                    0.0
                  end
                end

                def invoice_lines(invoices)
                  lines = []
                  invoices.each do |invoice|
                    next if invoice.units.negative? || invoice.price.negative?

                    subtotal = invoice.units * invoice.price
                    discount = (subtotal * discount_for(subtotal)).round
                    total = subtotal - discount
                    total = 0 if total.negative?
                    lines << Line.new(invoice.customer, subtotal, discount, total)
                  end
                  lines.sort_by { |line| -line.total }
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def render_invoices(lines)
                  rows = lines.map do |line|
                    format("%-10s %7d %8d %7d", line.customer, line.subtotal, line.discount, line.total)
                  end
                  rows.unshift(format("%-10s %7s %8s %7s", "customer", "subtotal", "discount", "total"))
                  rows.join("\\n")
                end
            """)},
        ],
    }


def _words() -> dict:
    return {
        "title": "ruby cli set — word frequency chart",
        "description": "Prints the most frequent words over a minimum length as a bar chart.",
        "family": "words",
        "target": "words.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'words'
                require_relative 'report'

                text = "the quick brown fox jumps over the lazy dog the fox sees the dog run"

                puts chart(ranked(text, 3, 6))
            """)},
            {"path": "words.rb", "content": _content("""
                def tokenize(text)
                  text.downcase.split(/[^a-z0-9]+/).reject(&:empty?)
                end

                def frequencies(text, minimum)
                  counts = Hash.new(0)
                  return counts if minimum <= 0

                  tokenize(text).each do |word|
                    next if word.length < minimum

                    counts[word] += 1
                  end
                  counts
                end

                def ranked(text, minimum, limit)
                  pairs = frequencies(text, minimum).sort_by { |word, count| [-count, word] }
                  pairs.first(limit)
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def chart(pairs)
                  return "no words" if pairs.empty?

                  width = pairs.map { |word, _count| word.length }.max
                  pairs.map do |word, count|
                    format("%-#{width}s %s %d", word, "*" * count, count)
                  end.join("\\n")
                end
            """)},
        ],
    }


def _loans() -> dict:
    return {
        "title": "ruby cli set — overdue library fees",
        "description": "Prints each overdue loan's fine, capped at the maximum, largest first.",
        "family": "loans",
        "target": "loans.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'loans'
                require_relative 'report'

                loans = [
                  Loan.new("dune", 9),
                  Loan.new("ulysses", 30),
                  Loan.new("emma", 6),
                  Loan.new("middlemarch", 14)
                ]

                puts render_fines(fines(loans))
            """)},
            {"path": "loans.rb", "content": _content("""
                Loan = Struct.new(:title, :days)

                Fine = Struct.new(:title, :days, :amount)

                def fine_for(days)
                  return 0 if days <= 7

                  weeks = (days - 7 + 6) / 7
                  weeks * 25
                end

                def fines(loans)
                  out = []
                  loans.each do |loan|
                    next if loan.days <= 0

                    amount = fine_for(loan.days)
                    amount = 150 if amount > 150
                    out << Fine.new(loan.title, loan.days, amount)
                  end
                  out.sort_by { |fine| -fine.amount }
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def render_fines(fines)
                  rows = fines.map do |fine|
                    format("%-18s %4d days %6d", fine.title, fine.days, fine.amount)
                  end
                  total = fines.inject(0) { |sum, fine| sum + fine.amount }
                  rows << format("%-18s %4s %11d", "total", "", total)
                  rows.join("\\n")
                end
            """)},
        ],
    }


def _caesar() -> dict:
    return {
        "title": "ruby cli set — caesar cipher round trip",
        "description": "Prints each phrase encoded by a shift and decoded back again.",
        "family": "caesar",
        "target": "caesar.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'caesar'
                require_relative 'report'

                phrases = ["attack at dawn", "Meet me at the bridge", "hold the line 42!"]

                puts shift_report(phrases, 3)
            """)},
            {"path": "caesar.rb", "content": _content("""
                def shift_text(text, shift)
                  out = []
                  text.each_char do |char|
                    if char.match?(/[a-z]/)
                      out << (((char.ord - 97 + shift) % 26) + 97).chr
                    elsif char.match?(/[A-Z]/)
                      out << (((char.ord - 65 + shift) % 26) + 65).chr
                    else
                      out << char
                    end
                  end
                  out.join
                end

                def round_trip(text, shift)
                  shift_text(shift_text(text, shift), -shift)
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def shift_report(phrases, shift)
                  rows = phrases.map do |phrase|
                    encoded = shift_text(phrase, shift)
                    decoded = round_trip(phrase, shift)
                    format("%-22s %-22s %s", phrase, encoded, decoded)
                  end
                  rows.unshift(format("%-22s %-22s %s", "plain", "encoded", "round trip"))
                  rows.join("\\n")
                end
            """)},
        ],
    }


def _coins() -> dict:
    return {
        "title": "ruby cli set — coin change",
        "description": "Prints the fewest coins for each amount and checks the total back.",
        "family": "coins",
        "target": "coins.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'coins'
                require_relative 'report'

                amounts = [287, 412, 1999, 63, 1]

                puts coin_report(amounts)
            """)},
            {"path": "coins.rb", "content": _content("""
                COINS = [200, 100, 50, 20, 10, 5, 2, 1].freeze

                def change_for(amount)
                  remaining = amount
                  purse = {}
                  COINS.each do |coin|
                    next if remaining < coin

                    count = remaining / coin
                    purse[coin] = count
                    remaining -= count * coin
                  end
                  purse
                end

                def coin_total(purse)
                  purse.inject(0) { |sum, (coin, count)| sum + coin * count }
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def coin_report(amounts)
                  rows = amounts.map do |amount|
                    purse = change_for(amount)
                    parts = purse.map { |coin, count| "#{count}x#{coin}" }
                    format("%5d  %-32s %d", amount, parts.join(" "), coin_total(purse))
                  end
                  rows.unshift(format("%5s  %-32s %s", "amount", "coins", "check"))
                  rows.join("\\n")
                end
            """)},
        ],
    }


def _temps() -> dict:
    return {
        "title": "ruby cli set — celsius to fahrenheit table",
        "description": "Prints each temperature converted and labelled by its range.",
        "family": "temps",
        "target": "temps.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'temps'
                require_relative 'report'

                celsius = [-10, 0, 18, 37, 100]

                puts temperature_table(celsius)
            """)},
            {"path": "temps.rb", "content": _content("""
                def to_fahrenheit(celsius)
                  (celsius * 9.0 / 5.0 + 32).round(1)
                end

                def temperature_rows(celsius)
                  rows = []
                  celsius.each do |value|
                    fahrenheit = to_fahrenheit(value)
                    if fahrenheit > 100
                      note = "above body heat"
                    elsif fahrenheit < 32
                      note = "below freezing"
                    else
                      note = "normal range"
                    end
                    rows << [value, fahrenheit, note]
                  end
                  rows
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def temperature_table(celsius)
                  rows = temperature_rows(celsius).map do |value, fahrenheit, note|
                    format("%6.1f C %7.1f F  %s", value, fahrenheit, note)
                  end
                  rows.unshift(format("%6s %9s  %s", "celsius", "fahrenheit", "note"))
                  rows.join("\\n")
                end
            """)},
        ],
    }


def _palindromes() -> dict:
    return {
        "title": "ruby cli set — palindrome check",
        "description": "Prints each phrase cleaned, measured, and marked as a palindrome.",
        "family": "palindromes",
        "target": "palindromes.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'palindromes'
                require_relative 'report'

                phrases = [
                  "A man, a plan, a canal: Panama",
                  "Was it a car or a cat I saw",
                  "not a palindrome",
                  "   "
                ]

                puts palindrome_report(phrases)
            """)},
            {"path": "palindromes.rb", "content": _content("""
                def normalize(text)
                  text.downcase.gsub(/[^a-z0-9]/, "")
                end

                def palindrome_rows(phrases)
                  rows = []
                  phrases.each do |phrase|
                    cleaned = normalize(phrase)
                    if cleaned.empty?
                      status = "blank"
                    elsif cleaned == cleaned.reverse
                      status = "yes"
                    else
                      status = "no"
                    end
                    rows << [phrase.strip, cleaned.length, status]
                  end
                  rows
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def palindrome_report(phrases)
                  rows = palindrome_rows(phrases).map do |phrase, length, status|
                    format("%-34s %3d %s", phrase, length, status)
                  end
                  rows.unshift(format("%-34s %3s %s", "phrase", "len", "palindrome"))
                  rows.join("\\n")
                end
            """)},
        ],
    }


def _roots() -> dict:
    return {
        "title": "ruby cli set — quadratic roots",
        "description": "Prints the real roots of each quadratic, or why there are none.",
        "family": "roots",
        "target": "roots.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'roots'
                require_relative 'report'

                coefficients = [[1, -3, 2], [1, 0, -4], [1, 2, 5], [2, 4, 2], [0, 1, 1]]

                puts root_report(coefficients)
            """)},
            {"path": "roots.rb", "content": _content("""
                def discriminant(a, b, c)
                  b * b - 4 * a * c
                end

                def roots_for(a, b, c)
                  return nil if a.zero?

                  d = discriminant(a, b, c)
                  if d.negative?
                    []
                  elsif d.zero?
                    [-b / (2.0 * a)]
                  else
                    root = Math.sqrt(d)
                    [(-b + root) / (2.0 * a), (-b - root) / (2.0 * a)].sort
                  end
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def root_report(coefficients)
                  rows = coefficients.map do |a, b, c|
                    found = roots_for(a, b, c)
                    text =
                      if found.nil?
                        "not quadratic"
                      elsif found.empty?
                        "complex roots"
                      else
                        found.map { |value| format("%.2f", value) }.join(" , ")
                      end
                    format("%2d %3d %3d  %s", a, b, c, text)
                  end
                  rows.unshift(format("%2s %3s %3s  %s", "a", "b", "c", "roots"))
                  rows.join("\\n")
                end
            """)},
        ],
    }


def _rle() -> dict:
    return {
        "title": "ruby cli set — run length encoding",
        "description": "Prints each sample encoded as runs and decoded back for a check.",
        "family": "rle",
        "target": "rle.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'rle'
                require_relative 'report'

                samples = ["aaabbbcccd", "wwwwwwwwwwww", "abcd", "zzzzzzzzzzzzz"]

                puts rle_report(samples)
            """)},
            {"path": "rle.rb", "content": _content("""
                def encode_runs(text)
                  runs = []
                  text.each_char do |char|
                    if runs.empty? || runs.last[0] != char
                      runs << [char, 1]
                    else
                      runs.last[1] += 1
                    end
                  end
                  runs.map { |char, count| "#{char}#{count}" }.join
                end

                def decode_runs(encoded)
                  out = ""
                  encoded.scan(/([a-zA-Z])(\d+)/) do |char, count|
                    out += char * count.to_i
                  end
                  out
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def rle_report(samples)
                  rows = samples.map do |text|
                    encoded = encode_runs(text)
                    status = decode_runs(encoded) == text ? "ok" : "mismatch"
                    format("%-16s %-14s %s", text, encoded, status)
                  end
                  rows.unshift(format("%-16s %-14s %s", "text", "encoded", "round trip"))
                  rows.join("\\n")
                end
            """)},
        ],
    }


def _life() -> dict:
    return {
        "title": "ruby cli set — one game of life step",
        "description": "Prints the next generation of an embedded grid and how many cells live.",
        "family": "game-of-life-step",
        "target": "life.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'life'
                require_relative 'report'

                GRID = [
                  [0, 1, 0, 0, 0],
                  [0, 1, 0, 0, 0],
                  [0, 1, 0, 1, 1],
                  [0, 0, 0, 0, 0],
                  [0, 0, 1, 1, 0]
                ]

                puts board_report(step(GRID))
            """)},
            {"path": "life.rb", "content": _content("""
                def neighbours(grid, row, col)
                  rows = grid.length
                  cols = grid.first.length
                  count = 0
                  [-1, 0, 1].each do |dr|
                    [-1, 0, 1].each do |dc|
                      next if dr.zero? && dc.zero?

                      r = row + dr
                      c = col + dc
                      next if r.negative? || c.negative? || r >= rows || c >= cols
                      next if grid[r][c].zero?

                      count += 1
                    end
                  end
                  count
                end

                def step(grid)
                  rows = grid.length
                  cols = grid.first.length
                  out = []
                  (0...rows).each do |row|
                    line = []
                    (0...cols).each do |col|
                      alive = neighbours(grid, row, col)
                      if grid[row][col] == 1
                        line << ([2, 3].include?(alive) ? 1 : 0)
                      else
                        line << (alive == 3 ? 1 : 0)
                      end
                    end
                    out << line
                  end
                  out
                end

                def live_count(grid)
                  grid.inject(0) do |sum, row|
                    sum + row.inject(0) { |inner, cell| inner + cell }
                  end
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def board_report(grid)
                  rows = grid.map do |row|
                    row.map { |cell| cell.zero? ? "." : "#" }.join(" ")
                  end
                  rows << "live #{live_count(grid)}"
                  rows.join(10.chr)
                end
            """)},
        ],
    }


def _tic_tac_toe() -> dict:
    return {
        "title": "ruby cli set — tic tac toe results",
        "description": "Prints each embedded tic tac toe board with its winner or draw.",
        "family": "tic-tac-toe-winner",
        "target": "board.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'board'
                require_relative 'report'

                games = [
                  ["X", "X", "X", "O", "O", "", "", "", ""],
                  ["X", "O", "X", "X", "O", "O", "O", "X", "X"],
                  ["X", "O", "", "X", "O", "", "", "X", ""]
                ]

                puts result_report(games)
            """)},
            {"path": "board.rb", "content": _content("""
                LINES = [[0, 1, 2], [3, 4, 5], [6, 7, 8],
                         [0, 3, 6], [1, 4, 7], [2, 5, 8],
                         [0, 4, 8], [2, 4, 6]].freeze

                def filled(cells)
                  cells.count { |cell| !cell.nil? && !cell.empty? }
                end

                def verdict(cells)
                  winners = []
                  LINES.each do |a, b, c|
                    mark = cells[a]
                    next if mark.nil? || mark.empty?
                    next unless mark == cells[b] && mark == cells[c]

                    winners << mark
                  end
                  if winners.empty?
                    if filled(cells) == 9
                      "draw"
                    else
                      "unfinished"
                    end
                  else
                    "#{winners.first} wins"
                  end
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def result_report(games)
                  rows = games.each_with_index.map do |cells, index|
                    marks = cells.map { |cell| cell.nil? || cell.empty? ? "." : cell }
                    format("game %d  %-9s %-11s filled %d",
                           index + 1, marks.join, verdict(cells), filled(cells))
                  end
                  rows.unshift(format("%-7s %-9s %-11s %s",
                                      "game", "board", "result", "filled"))
                  rows.join(10.chr)
                end
            """)},
        ],
    }


def _acronyms() -> dict:
    return {
        "title": "ruby cli set — acronym and title case",
        "description": "Prints each embedded phrase in title case beside the acronym it spells.",
        "family": "acronym-titlecase",
        "target": "phrases.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'phrases'
                require_relative 'report'

                PHRASES = [
                  "portable network graphics",
                  "as soon as possible",
                  "hyper text markup language",
                  "application programming interface"
                ]

                puts case_report(PHRASES)
            """)},
            {"path": "phrases.rb", "content": _content("""
                SMALL = %w[a an and as at but by for in of on or the to].freeze

                def title_case(text)
                  words = text.downcase.split
                  out = []
                  words.each_with_index do |word, index|
                    if index.zero? || index == words.length - 1
                      out << word.capitalize
                    elsif SMALL.include?(word)
                      out << word
                    else
                      out << word.capitalize
                    end
                  end
                  out.join(" ")
                end

                def acronym(text)
                  words = title_case(text).split
                  words.select { |word| word[0] == word[0].upcase }
                       .map { |word| word[0] }
                       .join
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def case_report(phrases)
                  rows = phrases.map do |phrase|
                    format("%-29s %-31s %s", phrase, title_case(phrase), acronym(phrase))
                  end
                  rows.unshift(format("%-29s %-31s %s", "phrase", "title case", "acronym"))
                  rows.join(10.chr)
                end
            """)},
        ],
    }


def _moving_average() -> dict:
    return {
        "title": "ruby cli set — moving average",
        "description": "Prints each window's average over an embedded series and its peak.",
        "family": "moving-average",
        "target": "series.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'series'
                require_relative 'report'

                SERIES = [4, 8, 15, 16, 23, 42, 7, 11, 19, 3]

                puts average_report(SERIES, 3)
            """)},
            {"path": "series.rb", "content": _content("""
                def window_average(values, start, size)
                  window = values[start, size]
                  return nil if window.nil? || window.empty?

                  total = 0
                  window.each do |value|
                    total += value
                  end
                  (total.to_f / window.length).round(2)
                end

                def moving_averages(values, size)
                  return [] if size <= 0 || size > values.length

                  out = []
                  last_start = values.length - size
                  (0..last_start).each do |start|
                    average = window_average(values, start, size)
                    next if average.nil?

                    out << average
                  end
                  out
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def average_report(values, size)
                  averages = moving_averages(values, size)
                  return "window #{size}: no averages" if averages.empty?

                  rows = averages.each_with_index.map do |value, index|
                    format("window %d  %6.2f", index + 1, value)
                  end
                  rows << format("series %d values, window %d, peak %.2f",
                                 values.length, size, averages.max)
                  rows.join(10.chr)
                end
            """)},
        ],
    }


def _binary_search() -> dict:
    return {
        "title": "binary search trace over a sorted list",
        "description": "binary search trace over a sorted list",
        "family": "binary-search-trace",
        "target": "trace.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'trace'
                require_relative 'report'

                VALUES = [2, 4, 6, 8, 10, 12, 14].freeze
                TARGETS = [8, 5].freeze

                puts render_searches(search_results(VALUES, TARGETS))
            """)},
            {"path": "trace.rb", "content": _content("""
                Probe = Struct.new(:index, :value)

                Search = Struct.new(:target, :index, :probes)

                def binary_search(values, target)
                  low = 0
                  high = values.length - 1
                  probes = []
                  found = nil
                  while low <= high
                    mid = low + (high - low) / 2
                    value = values[mid]
                    probes << Probe.new(mid, value)
                    if value == target
                      found = mid
                      break
                    elsif value < target
                      low = mid + 1
                    else
                      high = mid - 1
                    end
                  end
                  Search.new(target, found, probes)
                end

                def search_results(values, targets)
                  targets.map { |target| binary_search(values, target) }
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def render_searches(searches)
                  rows = []
                  searches.each do |search|
                    rows << "search #{search.target}"
                    search.probes.each do |probe|
                      rows << "probe #{probe.index} value #{probe.value}"
                    end
                    if search.index.nil?
                      rows << "not found #{search.target}"
                    else
                      rows << "found #{search.target} at index #{search.index}"
                    end
                  end
                  rows.join(10.chr)
                end
            """)},
        ],
    }


def _lru_cache() -> dict:
    return {
        "title": "lru cache simulation with capacity two",
        "description": "lru cache simulation with capacity two",
        "family": "lru-cache-simulation",
        "target": "cache.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'cache'
                require_relative 'report'

                OPERATIONS = [
                  [:get, "a"],
                  [:put, "b"],
                  [:get, "a"],
                  [:put, "c"],
                  [:get, "b"],
                  [:get, "a"]
                ].freeze

                puts render_log(replay(OPERATIONS, 2))
            """)},
            {"path": "cache.rb", "content": _content("""
                # A miss reads the key through: it enters the cache when there is
                # room, and a full cache answers the miss without evicting, so a
                # read cannot push out an entry a write just kept.
                def get_key(cache, key, capacity, log)
                  if cache.include?(key)
                    cache.delete(key)
                    cache << key
                    log << "get #{key} hit"
                  else
                    log << "get #{key} miss"
                    cache << key if cache.length < capacity
                  end
                end

                def put_key(cache, key, capacity, log)
                  line = "put #{key}"
                  cache.delete(key)
                  if cache.length >= capacity
                    line += " evict #{cache.shift}"
                  end
                  cache << key
                  log << line
                end

                def replay(operations, capacity)
                  cache = []
                  log = []
                  operations.each do |kind, key|
                    if kind == :get
                      get_key(cache, key, capacity, log)
                    else
                      put_key(cache, key, capacity, log)
                    end
                  end
                  log
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def render_log(log)
                  log.join(10.chr)
                end
            """)},
        ],
    }


def _isbn() -> dict:
    return {
        "title": "isbn ten checksum validation",
        "description": "isbn ten checksum validation",
        "family": "isbn-checksum",
        "target": "isbn.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'isbn'
                require_relative 'report'

                CODES = ["0306406152", "0306406153"].freeze

                puts render_codes(checked_codes(CODES))
            """)},
            {"path": "isbn.rb", "content": _content("""
                Checked = Struct.new(:code, :check, :valid)

                def digit_value(char)
                  return 10 if char.casecmp("x").zero?

                  char.to_i
                end

                def weighted_sum(text)
                  total = 0
                  text.each_char.with_index do |char, index|
                    total += digit_value(char) * (10 - index)
                  end
                  total
                end

                def check_digit(head)
                  total = weighted_sum(head)
                  (11 - total % 11) % 11
                end

                def checked_code(code)
                  return nil unless code.length == 10

                  head = code[0, 9]
                  Checked.new(code, check_digit(head), weighted_sum(code) % 11 == 0)
                end

                def checked_codes(codes)
                  codes.map { |code| checked_code(code) }.compact
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def render_codes(checked)
                  rows = checked.map do |entry|
                    status = entry.valid ? "valid" : "invalid"
                    "#{entry.code} #{status} check #{entry.check}"
                  end
                  rows.join(10.chr)
                end
            """)},
        ],
    }


def _vending() -> dict:
    return {
        "title": "vending machine change by coin count",
        "description": "vending machine change by coin count",
        "family": "vending-change",
        "target": "vending.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'vending'
                require_relative 'report'

                PURCHASES = [[65, 100], [130, 200]].freeze

                puts render_purchases(purchase_rows(PURCHASES))
            """)},
            {"path": "vending.rb", "content": _content("""
                COINS = [50, 25, 20, 10].freeze

                Purchase = Struct.new(:price, :paid, :change, :coins)

                def coin_counts(amount)
                  remaining = amount
                  counts = []
                  COINS.each do |coin|
                    next if remaining < coin

                    count = remaining / coin
                    counts << [coin, count]
                    remaining -= coin * count
                  end
                  counts
                end

                def purchase_rows(purchases)
                  purchases.map do |price, paid|
                    change = paid - price
                    change = 0 if change.negative?
                    Purchase.new(price, paid, change, coin_counts(change))
                  end
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def render_purchases(purchases)
                  rows = []
                  purchases.each do |purchase|
                    rows << format("price %d paid %d change %d",
                                   purchase.price, purchase.paid, purchase.change)
                    purchase.coins.each do |coin, count|
                      rows << "#{count} x #{coin}"
                    end
                  end
                  rows.join(10.chr)
                end
            """)},
        ],
    }


def _life_step() -> dict:
    return {
        "title": "conway life step on a four by four grid",
        "description": "conway life step on a four by four grid",
        "family": "game-of-life-step",
        "target": "life.rb",
        "files": [
            {"path": "main.rb", "content": _content("""
                require_relative 'life'
                require_relative 'report'

                GRID = [
                  [0, 1, 0, 0],
                  [0, 1, 0, 0],
                  [0, 1, 0, 0],
                  [0, 0, 0, 0]
                ].freeze

                puts render_board(step(GRID))
            """)},
            {"path": "life.rb", "content": _content("""
                def padded(grid)
                  blind = Array.new(grid.length + 2) { Array.new(grid.first.length + 2, 0) }
                  grid.each_with_index do |row, r|
                    row.each_with_index { |cell, c| blind[r + 1][c + 1] = cell }
                  end
                  blind
                end

                def step(grid)
                  area = padded(grid)
                  Array.new(grid.length) do |r|
                    Array.new(grid.first.length) do |c|
                      around = 0
                      (0..2).each do |dr|
                        (0..2).each { |dc| around += area[r + dr][c + dc] }
                      end
                      here = area[r + 1][c + 1]
                      alive = around - here
                      alive == 3 || (here == 1 && alive == 2) ? 1 : 0
                    end
                  end
                end

                def live_count(grid)
                  grid.flatten.count(1)
                end
            """)},
            {"path": "report.rb", "content": _content("""
                def render_board(grid)
                  rows = grid.map do |row|
                    "row " + row.map { |cell| cell.zero? ? "0" : "1" }.join
                  end
                  rows << "live #{live_count(grid)}"
                  rows.join(10.chr)
                end
            """)},
        ],
    }
def sets() -> list[dict]:
    return [_invoices(), _words(), _loans(),
            _caesar(), _coins(), _temps(), _palindromes(), _roots(), _rle(),
            _life(), _tic_tac_toe(), _acronyms(), _moving_average(),
            _binary_search(), _lru_cache(), _isbn(), _vending(), _life_step()]
