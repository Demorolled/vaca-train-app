"""Rewrite the Ruby game-of-life set with a distinct implementation.

The worker's version was byte-identical to an older Ruby set (same grid code),
so `library.load_tasks` deduped it away and the family had no Ruby sibling that
printed the spec. A padded-board implementation is the same program, different
code, and prints the same five lines.
"""
from pathlib import Path

Q3 = '"' * 3
TEMPLATE = """def _life_step() -> dict:
    return {
        "title": "conway life step on a four by four grid",
        "description": "conway life step on a four by four grid",
        "family": "game-of-life-step",
        "target": "life.rb",
        "files": [
            {"path": "main.rb", "content": _content(Q3
                require_relative 'life'
                require_relative 'report'

                GRID = [
                  [0, 1, 0, 0],
                  [0, 1, 0, 0],
                  [0, 1, 0, 0],
                  [0, 0, 0, 0]
                ].freeze

                puts render_board(step(GRID))
            Q3)},
            {"path": "life.rb", "content": _content(Q3
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
            Q3)},
            {"path": "report.rb", "content": _content(Q3
                def render_board(grid)
                  rows = grid.map do |row|
                    "row " + row.map { |cell| cell.zero? ? "0" : "1" }.join
                  end
                  rows << "live #{live_count(grid)}"
                  rows.join(10.chr)
                end
            Q3)},
        ],
    }
"""

path = Path("trainapp/clisets/ruby.py")
text = path.read_text(encoding="utf-8")
start = text.index("def _life_step() -> dict:")
end = text.index("\ndef ", start + 1)
path.write_text(text[:start] + TEMPLATE.replace("Q3", Q3) + text[end + 1:],
                encoding="utf-8")
print("rewrote _life_step:", start, "->", end)
