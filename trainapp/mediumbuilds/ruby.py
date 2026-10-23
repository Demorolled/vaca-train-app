"""Ruby medium builds — ten templates, ten data variants each.

Each program is one file with at least three methods, a real data structure
between them, and a deterministic multi-line report. No argv, stdin, files,
clock, network or randomness.
"""
from __future__ import annotations

LANGUAGE = "ruby"

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
    "name,qty,price\nbolt,12,0.50\nnut,40,0.10\nwasher,0,0.05",
    "item,units,cost\nhammer,3,36.00\nsaw,0,18.50\ndrill,2,90.00",
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
)

LISTS = ((3, 1, 4), (7, 2, 9, 5), (1, 2, 3, 4, 5), (9,), (4, 4, 6),
         (8, 3, 1, 7), (2, 6, 5, 3, 8), (11, 4), (5, 9, 2, 6, 1),
         (10, 20, 30, 40))


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace(f"@{key}@", value)
    return template


def _rb_rows(records: tuple) -> str:
    return "[" + ", ".join(f'["{name}", {qty}, {price}]'
                           for name, qty, price in records) + "]"


def _rb_matrix(matrix: tuple) -> str:
    return "[" + ", ".join("[" + ", ".join(str(v) for v in row) + "]"
                           for row in matrix) + "]"


def _rb_list(values) -> str:
    return "[" + ", ".join(str(v) for v in values) + "]"


WORD_FREQ = """TEXT = '@TEXT@'

def tokens(text)
  text.split
end

def counts(words)
  table = Hash.new(0)
  words.each { |word| table[word] += 1 }
  table
end

def ranked(table)
  table.sort_by { |word, count| [-count, word] }.map { |word, _| word }
end

table = counts(tokens(TEXT))
ranked(table).first(4).each { |word| puts format('%s: %d', word, table[word]) }
"""

INVENTORY = """STOCK = @ROWS@

def available(stock)
  stock.select { |row| row[1] > 0 }
end

def total(rows)
  rows.sum { |row| row[1] * row[2] }
end

def report(rows)
  rows.map { |name, qty, price| format('%-8s %3d x %6.2f = %8.2f', name, qty, price, qty * price) }
end

rows = available(STOCK)
puts report(rows).join("\\n")
puts format('total %.2f', total(rows))
"""

MATRIX = """MATRIX = @MATRIX@

def transpose(matrix)
  matrix.transpose
end

def row_sums(matrix)
  matrix.map { |row| row.sum }
end

def render(matrix)
  matrix.map { |row| row.map { |value| format('%3d', value) }.join(' ') }
end

puts render(transpose(MATRIX)).join("\\n")
puts "sums #{row_sums(MATRIX).join(' ')}"
"""

STACK = """class Stack
  def initialize
    @items = []
  end

  def push(value)
    @items.push(value)
  end

  def pop
    @items.pop
  end

  def peek
    @items.last
  end

  def size
    @items.length
  end
end

def run(stack, ops)
  out = []
  ops.each do |op|
    name, _, argument = op.partition(' ')
    case name
    when 'push'
      stack.push(argument.to_i)
      out << "push #{argument}"
    when 'pop'
      out << "pop #{stack.pop || 'none'}"
    else
      out << "peek #{stack.peek || 'none'}"
    end
  end
  out
end

OPS = @OPS@
puts run(Stack.new, OPS).join("\\n")
"""

LINKED = """Node = Struct.new(:value, :next_node)

VALUES = @LIST@

def build(values)
  head = nil
  values.reverse_each { |value| head = Node.new(value, head) }
  head
end

def reverse(head)
  previous = nil
  while head
    following = head.next_node
    head.next_node = previous
    previous = head
    head = following
  end
  previous
end

def render(head)
  parts = []
  while head
    parts << head.value.to_s
    head = head.next_node
  end
  parts.join(' -> ')
end

head = build(VALUES)
puts render(head)
puts render(reverse(head))
"""

CSV = """TABLE = <<~CSV
@DATA@
CSV

def parse(data)
  lines = data.split("\\n").reject(&:empty?)
  header = lines.shift.split(',')
  rows = lines.map { |line| line.split(',') }
  [header, rows]
end

def numeric?(text)
  Float(text)
  true
rescue ArgumentError
  false
end

def totals(header, rows)
  out = {}
  index = 1
  while index < header.length
    name = header[index]
    out[name] = rows.sum { |row| numeric?(row[index]) ? row[index].to_f : 1.0 }
    index += 1
  end
  out
end

header, rows = parse(TABLE)
puts "columns #{header[1..].join(',')}"
totals(header, rows).each { |name, value| puts format('%s: %.2f', name, value) }
"""

SORT_RECORDS = """ROWS = @ROWS@

def by_value(rows)
  rows.sort_by { |name, qty, price| [-(qty * price), name] }
end

def by_name(rows)
  rows.sort_by { |name, _, _| name }
end

def render(rows)
  rows.map { |name, qty, _| format('%s(%d)', name, qty) }.join(', ')
end

puts "value #{render(by_value(ROWS))}"
puts "name  #{render(by_name(ROWS))}"
"""

FACTORS = """NUMBERS = @NUMBERS@

def factorise(value)
  out = []
  divisor = 2
  while divisor * divisor <= value
    while (value % divisor).zero?
      out << divisor
      value /= divisor
    end
    divisor += 1
  end
  out << value if value > 1
  out
end

def table(numbers)
  numbers.map { |number| [number, factorise(number)] }
end

table(NUMBERS).each { |number, parts| puts format('%d: %s', number, parts.join(' x ')) }
"""

BANK = """class Account
  attr_reader :log

  def initialize(opening)
    @balance = opening
    @log = [['open', opening, opening]]
  end

  def deposit(amount)
    @balance += amount
    @log << ['deposit', amount, @balance]
  end

  def withdraw(amount)
    if amount > @balance
      @log << ['refused', amount, @balance]
      return false
    end
    @balance -= amount
    @log << ['withdraw', amount, @balance]
    true
  end
end

OPS = @OPS@
account = Account.new(OPS[0][1])
OPS[1..].each do |kind, amount|
  kind == 'deposit' ? account.deposit(amount) : account.withdraw(amount)
end

account.log.each { |kind, amount, balance| puts format('%-9s %4d -> %4d', kind, amount, balance) }
"""

PIPELINE = """TEXT = '@TEXT@'

def words(text)
  text.split
end

def transform(words)
  words.map(&:capitalize)
end

def longest(words)
  words.max_by(&:length) || ''
end

def report(words)
  transform(words).join(' | ')
end

items = words(TEXT)
puts report(items)
puts "#{items.length} #{longest(items)} #{items.sum(&:length)}"
"""


def programs() -> list[dict]:
    rows: list[dict] = []
    for text in TEXTS:
        rows.append({"title": f"word frequency: {text[:24]}", "template": "word-freq",
                     "code": _fill(WORD_FREQ, TEXT=text)})
    for records in RECORDS:
        rows.append({"title": f"inventory report: {records[0][0]}", "template": "inventory",
                     "code": _fill(INVENTORY, ROWS=_rb_rows(records))})
        rows.append({"title": f"sort records: {records[0][0]}", "template": "sort-records",
                     "code": _fill(SORT_RECORDS, ROWS=_rb_rows(records))})
    for matrix in MATRICES:
        rows.append({"title": f"matrix {matrix[0]}", "template": "matrix",
                     "code": _fill(MATRIX, MATRIX=_rb_matrix(matrix))})
    for ops in STACK_OPS:
        literal = "[" + ", ".join(f"'{op}'" for op in ops) + "]"
        rows.append({"title": f"stack: {' '.join(ops[:2])}", "template": "stack",
                     "code": _fill(STACK, OPS=literal)})
    for values in LISTS:
        rows.append({"title": f"reverse list {list(values)}", "template": "linked-list",
                     "code": _fill(LINKED, LIST=_rb_list(values))})
    for data in CSVS:
        rows.append({"title": f"csv totals: {data.split(',')[0]}", "template": "csv",
                     "code": _fill(CSV, DATA=data)})
    for n in NUMBERS:
        numbers = [n // 2, n - 1, n, 7, 11, 13, 17, 19]
        rows.append({"title": f"factors up to {n}", "template": "factors",
                     "code": _fill(FACTORS, NUMBERS=_rb_list(numbers))})
    for ledger in LEDGERS:
        pairs = "[" + ", ".join(f"['{kind}', {amount}]" for kind, amount in ledger) + "]"
        rows.append({"title": f"ledger from {ledger[0][1]}", "template": "bank",
                     "code": _fill(BANK, OPS=pairs)})
    for text in TEXTS:
        rows.append({"title": f"text pipeline: {text[:20]}", "template": "pipeline",
                     "code": _fill(PIPELINE, TEXT=text)})
    return rows
