"""javascript — three-file CommonJS CLI sets whose stdout is the reference.

Same contract as the rest of `clisets`: `main.js` is a thin entry point, the
target module holds the logic a model is asked to write, and `report.js` turns
the result into the printed text. CommonJS only — the set runner writes no
package.json, so `import` would not resolve. Standard library only, no stdin, no
argv, no clock, no randomness.
"""
from __future__ import annotations

import textwrap


def _src(text: str) -> str:
    return textwrap.dedent(text).strip() + "\n"


INVOICE_INVENTORY = _src(r"""
    const ITEMS = [
      { name: 'notebook', cents: 499, qty: 3 },
      { name: 'pen', cents: 129, qty: 12 },
      { name: 'desk lamp', cents: 4599, qty: 1 },
      { name: 'usb cable', cents: 899, qty: 4 },
    ];

    function parseItems() {
      return ITEMS.map(function (item) {
        return { name: item.name, cents: item.cents, qty: item.qty };
      });
    }

    function subtotal(items) {
      return items.reduce(function (sum, item) {
        return sum + item.cents * item.qty;
      }, 0);
    }

    function applyTaxBands(items) {
      const rows = [];
      let running = 0;
      for (let i = 0; i < items.length; i += 1) {
        const item = items[i];
        const line = item.cents * item.qty;
        let rate;
        if (running > 5000) {
          rate = 0.2;
        } else if (running > 2000) {
          rate = 0.1;
        } else {
          rate = 0.05;
        }
        running += line;
        rows.push({
          name: item.name,
          line: line,
          rate: rate,
          tax: Math.round(line * rate),
        });
      }
      return rows;
    }

    module.exports = {
      parseItems: parseItems,
      subtotal: subtotal,
      applyTaxBands: applyTaxBands,
    };
""")

INVOICE_REPORT = _src(r"""
    function money(cents) {
      const sign = cents < 0 ? '-' : '';
      const abs = Math.abs(cents);
      const whole = Math.floor(abs / 100);
      const frac = abs % 100;
      return sign + '$' + whole + '.' + (frac < 10 ? '0' + frac : String(frac));
    }

    function render(title, rows, total) {
      const lines = [title];
      let tax = 0;
      for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        tax += row.tax;
        lines.push(
          '  ' + row.name + ': ' + money(row.line) +
          ' (band ' + Math.round(row.rate * 100) + '%, tax ' + money(row.tax) + ')'
        );
      }
      lines.push('subtotal ' + money(total) + ', tax ' + money(tax));
      return lines.join('\n');
    }

    module.exports = { money: money, render: render };
""")

INVOICE_MAIN = _src(r"""
    const inventory = require('./inventory');
    const report = require('./report');

    const items = inventory.parseItems();
    const rows = inventory.applyTaxBands(items);
    const total = inventory.subtotal(items);
    console.log(report.render('Invoice', rows, total));
""")

WORDS_WORDS = _src(r"""
    const SAMPLE =
      'the quick brown fox jumps over the lazy dog and the fox runs ' +
      'while the dog sleeps under an old oak tree';

    function tokenize(text) {
      return text
        .toLowerCase()
        .split(/[^a-z]+/)
        .filter(function (word) { return word.length > 0; });
    }

    function countWords(tokens) {
      const counts = {};
      for (let i = 0; i < tokens.length; i += 1) {
        const word = tokens[i];
        if (word.length < 3) {
          continue;
        }
        if (counts[word]) {
          counts[word] += 1;
        } else {
          counts[word] = 1;
        }
      }
      return counts;
    }

    function topWords(counts, limit) {
      return Object.keys(counts)
        .sort(function (a, b) {
          return counts[b] - counts[a] || (a < b ? -1 : 1);
        })
        .slice(0, limit)
        .map(function (word) { return { word: word, count: counts[word] }; });
    }

    module.exports = {
      SAMPLE: SAMPLE,
      tokenize: tokenize,
      countWords: countWords,
      topWords: topWords,
    };
""")

WORDS_REPORT = _src(r"""
    function pad(text, width) {
      let out = String(text);
      while (out.length < width) {
        out += ' ';
      }
      return out;
    }

    function renderTable(title, rows) {
      const lines = [title];
      for (let i = 0; i < rows.length; i += 1) {
        lines.push('  ' + pad(rows[i].word, 10) + pad(rows[i].count, 3));
      }
      return lines.join('\n');
    }

    module.exports = { pad: pad, renderTable: renderTable };
""")

WORDS_MAIN = _src(r"""
    const words = require('./words');
    const report = require('./report');

    const tokens = words.tokenize(words.SAMPLE);
    const counts = words.countWords(tokens);
    console.log(report.renderTable('Most common words', words.topWords(counts, 5)));
""")

INTERVALS_INTERVALS = _src(r"""
    const MEETINGS = [
      { start: 9 * 60, end: 10 * 60 + 30 },
      { start: 10 * 60, end: 11 * 60 },
      { start: 13 * 60, end: 14 * 60 },
      { start: 13 * 60 + 45, end: 15 * 60 + 15 },
      { start: 16 * 60, end: 16 * 60 + 20 },
    ];

    function mergeIntervals(meetings) {
      const sorted = meetings.slice().sort(function (a, b) {
        if (a.start !== b.start) {
          return a.start - b.start;
        }
        return a.end - b.end;
      });
      const merged = [];
      for (let i = 0; i < sorted.length; i += 1) {
        const slot = sorted[i];
        const last = merged[merged.length - 1];
        if (last && slot.start <= last.end) {
          if (slot.end > last.end) {
            last.end = slot.end;
          }
        } else {
          merged.push({ start: slot.start, end: slot.end });
        }
      }
      return merged;
    }

    function busyMinutes(merged) {
      let total = 0;
      for (let i = 0; i < merged.length; i += 1) {
        total += merged[i].end - merged[i].start;
      }
      return total;
    }

    module.exports = {
      MEETINGS: MEETINGS,
      mergeIntervals: mergeIntervals,
      busyMinutes: busyMinutes,
    };
""")

INTERVALS_REPORT = _src(r"""
    function clock(minutes) {
      const hour = String(Math.floor(minutes / 60));
      const minute = minutes % 60;
      return (hour.length < 2 ? '0' + hour : hour) + ':' +
        (minute < 10 ? '0' + minute : String(minute));
    }

    function renderSchedule(title, blocks, total) {
      const lines = [title];
      for (let i = 0; i < blocks.length; i += 1) {
        const block = blocks[i];
        lines.push('  ' + clock(block.start) + '-' + clock(block.end) +
          ' (' + (block.end - block.start) + ' min)');
      }
      lines.push('busy ' + total + ' minutes');
      return lines.join('\n');
    }

    module.exports = { clock: clock, renderSchedule: renderSchedule };
""")

INTERVALS_MAIN = _src(r"""
    const intervals = require('./intervals');
    const report = require('./report');

    const merged = intervals.mergeIntervals(intervals.MEETINGS);
    console.log(report.renderSchedule('Busy blocks', merged, intervals.busyMinutes(merged)));
""")

GRADES_GRADES = _src(r"""
    const SCORES = [88, 42, 95, 71, 66, 90, 55, 79, 83, 61, 100, 39];

    function tally(scores) {
      const bands = { A: 0, B: 0, C: 0, D: 0, F: 0 };
      let total = 0;
      for (let i = 0; i < scores.length; i += 1) {
        const score = scores[i];
        if (score >= 90) {
          bands.A += 1;
        } else if (score >= 80) {
          bands.B += 1;
        } else if (score >= 70) {
          bands.C += 1;
        } else if (score >= 60) {
          bands.D += 1;
        } else {
          bands.F += 1;
        }
        total += score;
      }
      return { bands: bands, mean: Math.round(total / scores.length) };
    }

    function leading(bands) {
      const order = ['A', 'B', 'C', 'D', 'F'];
      let best = order[0];
      for (let i = 1; i < order.length; i += 1) {
        if (bands[order[i]] > bands[best]) {
          best = order[i];
        }
      }
      return best;
    }

    module.exports = { SCORES: SCORES, tally: tally, leading: leading };
""")

GRADES_REPORT = _src(r"""
    function bar(count) {
      let out = '';
      for (let i = 0; i < count; i += 1) {
        out += '#';
      }
      return out;
    }

    function render(title, result, leading) {
      const lines = [title];
      const order = ['A', 'B', 'C', 'D', 'F'];
      for (let i = 0; i < order.length; i += 1) {
        const key = order[i];
        const count = result.bands[key];
        lines.push('  ' + key + ' ' + bar(count) + ' ' + count);
      }
      lines.push('mean ' + result.mean + ', leading band ' + leading);
      return lines.join('\n');
    }

    module.exports = { bar: bar, render: render };
""")

GRADES_MAIN = _src(r"""
    const grades = require('./grades');
    const report = require('./report');

    const result = grades.tally(grades.SCORES);
    console.log(report.render('Grade bands', result, grades.leading(result.bands)));
""")

ROMAN_ROMAN = _src(r"""
    const VALUES = [
      { value: 1000, glyph: 'M' },
      { value: 900, glyph: 'CM' },
      { value: 500, glyph: 'D' },
      { value: 400, glyph: 'CD' },
      { value: 100, glyph: 'C' },
      { value: 90, glyph: 'XC' },
      { value: 50, glyph: 'L' },
      { value: 40, glyph: 'XL' },
      { value: 10, glyph: 'X' },
      { value: 9, glyph: 'IX' },
      { value: 5, glyph: 'V' },
      { value: 4, glyph: 'IV' },
      { value: 1, glyph: 'I' }
    ];

    const NUMBERS = [1, 4, 9, 14, 40, 90, 400, 1994, 2024, 4000];

    function toRoman(number) {
      let left = number;
      let out = '';
      for (let i = 0; i < VALUES.length; i += 1) {
        const step = VALUES[i];
        while (left >= step.value) {
          out += step.glyph;
          left -= step.value;
        }
      }
      return out;
    }

    function convertAll(numbers) {
      const rows = [];
      for (let i = 0; i < numbers.length; i += 1) {
        const number = numbers[i];
        if (number < 1 || number > 3999) {
          rows.push({ input: number, roman: 'out of range' });
        } else {
          rows.push({ input: number, roman: toRoman(number) });
        }
      }
      return rows;
    }

    module.exports = { NUMBERS: NUMBERS, toRoman: toRoman, convertAll: convertAll };
""")

ROMAN_REPORT = _src(r"""
    function pad(value, width) {
      let out = String(value);
      while (out.length < width) {
        out = out + ' ';
      }
      return out;
    }

    function renderTable(title, rows) {
      const lines = [title];
      for (let i = 0; i < rows.length; i += 1) {
        lines.push('  ' + pad(rows[i].input, 5) + rows[i].roman);
      }
      return lines.join('\n');
    }

    module.exports = { pad: pad, renderTable: renderTable };
""")

ROMAN_MAIN = _src(r"""
    const roman = require('./roman');
    const report = require('./report');

    console.log(report.renderTable('Roman numerals', roman.convertAll(roman.NUMBERS)));
""")

LEDGER_LEDGER = _src(r"""
    const ENTRIES = [
      { label: 'opening', amount: 900 },
      { label: 'rent', amount: -1200 },
      { label: 'salary', amount: 2400 },
      { label: 'power bill', amount: -180 },
      { label: 'grocery', amount: -95 },
      { label: 'refund', amount: 40 },
      { label: 'insurance', amount: -260 },
      { label: 'interest', amount: 12 }
    ];

    function runningBalance(entries) {
      const rows = [];
      let balance = 0;
      for (let i = 0; i < entries.length; i += 1) {
        const entry = entries[i];
        balance += entry.amount;
        let status = 'ok';
        if (balance < 0) {
          status = 'overdraft';
        } else if (balance < 200) {
          status = 'low';
        }
        rows.push({
          label: entry.label,
          amount: entry.amount,
          balance: balance,
          status: status
        });
      }
      return rows;
    }

    function lowestPoint(rows) {
      let lowest = rows[0].balance;
      for (let i = 1; i < rows.length; i += 1) {
        if (rows[i].balance < lowest) {
          lowest = rows[i].balance;
        }
      }
      return lowest;
    }

    module.exports = {
      ENTRIES: ENTRIES,
      runningBalance: runningBalance,
      lowestPoint: lowestPoint
    };
""")

LEDGER_REPORT = _src(r"""
    function money(amount) {
      const sign = amount < 0 ? '-' : '';
      const abs = Math.abs(amount);
      const whole = Math.floor(abs);
      const cents = Math.round((abs - whole) * 100);
      return sign + whole + '.' + (cents < 10 ? '0' + cents : String(cents));
    }

    function pad(text, width) {
      let out = String(text);
      while (out.length < width) {
        out = out + ' ';
      }
      return out;
    }

    function render(title, rows, lowest) {
      const lines = [title];
      for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        lines.push(
          '  ' + pad(row.label, 12) + pad(money(row.amount), 9) +
          pad(money(row.balance), 11) + row.status
        );
      }
      lines.push('lowest balance ' + money(lowest));
      return lines.join('\n');
    }

    module.exports = { money: money, pad: pad, render: render };
""")

LEDGER_MAIN = _src(r"""
    const ledger = require('./ledger');
    const report = require('./report');

    const rows = ledger.runningBalance(ledger.ENTRIES);
    console.log(report.render('Ledger', rows, ledger.lowestPoint(rows)));
""")

TICKETS_TICKETS = _src(r"""
    const BOOKINGS = [
      { group: 'students', zone: 'stalls', qty: 6 },
      { group: 'students', zone: 'balcony', qty: 2 },
      { group: 'public', zone: 'stalls', qty: 3 },
      { group: 'members', zone: 'balcony', qty: 4 },
      { group: 'public', zone: 'box', qty: 2 },
      { group: 'members', zone: 'stalls', qty: 1 }
    ];

    const PRICES = { stalls: 2800, balcony: 1900, box: 4500 };

    function priceBookings(bookings) {
      const rows = [];
      let total = 0;
      for (let i = 0; i < bookings.length; i += 1) {
        const booking = bookings[i];
        const unit = PRICES[booking.zone];
        let discount = 0;
        if (booking.group === 'students') {
          discount = 0.25;
        } else if (booking.group === 'members') {
          discount = 0.1;
        }
        if (booking.qty >= 4) {
          discount = discount + 0.05;
        }
        const gross = unit * booking.qty;
        const net = Math.round(gross * (1 - discount));
        total += net;
        rows.push({
          group: booking.group,
          zone: booking.zone,
          qty: booking.qty,
          discount: discount,
          net: net
        });
      }
      return { rows: rows, total: total };
    }

    function busiest(rows) {
      let best = rows[0];
      for (let i = 1; i < rows.length; i += 1) {
        if (rows[i].net > best.net) {
          best = rows[i];
        }
      }
      return best.zone;
    }

    module.exports = {
      BOOKINGS: BOOKINGS,
      priceBookings: priceBookings,
      busiest: busiest
    };
""")

TICKETS_REPORT = _src(r"""
    function money(cents) {
      const whole = Math.floor(cents / 100);
      const rest = cents % 100;
      return whole + '.' + (rest < 10 ? '0' + rest : String(rest));
    }

    function pad(text, width) {
      let out = String(text);
      while (out.length < width) {
        out = out + ' ';
      }
      return out;
    }

    function render(title, priced, busiest) {
      const lines = [title];
      for (let i = 0; i < priced.rows.length; i += 1) {
        const row = priced.rows[i];
        lines.push(
          '  ' + pad(row.group, 9) + pad(row.zone, 9) + pad(row.qty, 3) +
          pad(Math.round(row.discount * 100) + '%', 5) + money(row.net)
        );
      }
      lines.push('total ' + money(priced.total) + ', busiest zone ' + busiest);
      return lines.join('\n');
    }

    module.exports = { money: money, pad: pad, render: render };
""")

TICKETS_MAIN = _src(r"""
    const tickets = require('./tickets');
    const report = require('./report');

    const priced = tickets.priceBookings(tickets.BOOKINGS);
    console.log(report.render('Ticket sales', priced, tickets.busiest(priced.rows)));
""")

WRAP_WRAP = _src(r"""
    const TEXT =
      'A small report generator wraps a paragraph to a fixed width and prints ' +
      'a ruler above it so the wrap can be checked by eye without counting ' +
      'characters by hand';

    function wrap(text, width) {
      const words = text.split(' ');
      const lines = [];
      let line = '';
      for (let i = 0; i < words.length; i += 1) {
        const word = words[i];
        if (word.length === 0) {
          continue;
        }
        if (line.length === 0) {
          line = word;
        } else if (line.length + 1 + word.length <= width) {
          line = line + ' ' + word;
        } else {
          lines.push(line);
          line = word;
        }
      }
      if (line.length > 0) {
        lines.push(line);
      }
      return lines;
    }

    function widest(lines) {
      let width = 0;
      for (let i = 0; i < lines.length; i += 1) {
        if (lines[i].length > width) {
          width = lines[i].length;
        }
      }
      return width;
    }

    module.exports = { TEXT: TEXT, wrap: wrap, widest: widest };
""")

WRAP_REPORT = _src(r"""
    function ruler(width) {
      let out = '';
      for (let i = 0; i < width; i += 1) {
        out += '-';
      }
      return out;
    }

    function render(lines, width) {
      const out = ['Wrapped ' + width, ruler(width)];
      for (let i = 0; i < lines.length; i += 1) {
        out.push(lines[i]);
      }
      out.push('lines ' + lines.length);
      return out.join('\n');
    }

    module.exports = { ruler: ruler, render: render };
""")

WRAP_MAIN = _src(r"""
    const wrap = require('./wrap');
    const report = require('./report');

    const width = 32;
    const lines = wrap.wrap(wrap.TEXT, width);
    console.log(report.render(lines, width));
""")

MATRIX_MATRIX = _src(r"""
    const GRID = [
      [3, 8, 1, 6],
      [9, 4, 7, 2],
      [5, 0, 8, 3]
    ];

    function transpose(grid) {
      const columns = grid[0].length;
      const out = [];
      for (let c = 0; c < columns; c += 1) {
        const column = [];
        for (let r = 0; r < grid.length; r += 1) {
          const row = grid[r];
          if (c < row.length) {
            column.push(row[c]);
          } else {
            column.push(0);
          }
        }
        out.push(column);
      }
      return out;
    }

    function rowSums(grid) {
      const sums = [];
      for (let r = 0; r < grid.length; r += 1) {
        let total = 0;
        for (let c = 0; c < grid[r].length; c += 1) {
          total += grid[r][c];
        }
        sums.push(total);
      }
      return sums;
    }

    module.exports = { GRID: GRID, transpose: transpose, rowSums: rowSums };
""")

MATRIX_REPORT = _src(r"""
    function pad(value, width) {
      let out = String(value);
      while (out.length < width) {
        out = ' ' + out;
      }
      return out;
    }

    function renderRows(lines) {
      const out = [];
      for (let i = 0; i < lines.length; i += 1) {
        const row = lines[i];
        let text = '';
        for (let c = 0; c < row.length; c += 1) {
          text += pad(row[c], 3);
        }
        out.push(' ' + text);
      }
      return out;
    }

    function render(title, grid, sums) {
      const lines = [title];
      const rows = renderRows(grid);
      for (let i = 0; i < rows.length; i += 1) {
        lines.push(rows[i] + '  | ' + sums[i]);
      }
      return lines.join('\n');
    }

    module.exports = { pad: pad, renderRows: renderRows, render: render };
""")

MATRIX_MAIN = _src(r"""
    const matrix = require('./matrix');
    const report = require('./report');

    const flipped = matrix.transpose(matrix.GRID);
    console.log(report.render('Transposed grid', flipped, matrix.rowSums(flipped)));
""")

POLY_POLY = _src(r"""
    const POLYNOMIALS = [
      { name: 'cubic', coeffs: [2, -3, 0, 5] },
      { name: 'quadratic', coeffs: [1, 4, -7] },
      { name: 'linear', coeffs: [3, -1] },
      { name: 'constant', coeffs: [12] }
    ];

    const POINTS = [-2, -1, 0, 1, 2, 3];

    function evaluate(coeffs, x) {
      let acc = 0;
      for (let i = 0; i < coeffs.length; i += 1) {
        acc = acc * x + coeffs[i];
      }
      return acc;
    }

    function degree(coeffs) {
      return coeffs.length - 1;
    }

    function evaluateAll(polynomials, points) {
      const rows = [];
      for (let p = 0; p < polynomials.length; p += 1) {
        const polynomial = polynomials[p];
        const values = [];
        let peak = evaluate(polynomial.coeffs, points[0]);
        for (let i = 0; i < points.length; i += 1) {
          const value = evaluate(polynomial.coeffs, points[i]);
          if (value > peak) {
            peak = value;
          }
          values.push({ x: points[i], value: value });
        }
        rows.push({
          name: polynomial.name,
          degree: degree(polynomial.coeffs),
          values: values,
          peak: peak
        });
      }
      return rows;
    }

    module.exports = {
      POLYNOMIALS: POLYNOMIALS,
      POINTS: POINTS,
      evaluate: evaluate,
      degree: degree,
      evaluateAll: evaluateAll
    };
""")

POLY_REPORT = _src(r"""
    function pad(text, width) {
      let out = String(text);
      while (out.length < width) {
        out += ' ';
      }
      return out;
    }

    function renderValues(values) {
      const parts = [];
      for (let i = 0; i < values.length; i += 1) {
        parts.push('x=' + values[i].x + ':' + values[i].value);
      }
      return parts.join(' ');
    }

    function render(title, rows) {
      const lines = [title];
      for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        lines.push(
          '  ' + pad(row.name, 10) + 'degree ' + row.degree + '  ' +
          renderValues(row.values) + '  peak ' + row.peak
        );
      }
      return lines.join('\n');
    }

    module.exports = { pad: pad, renderValues: renderValues, render: render };
""")

POLY_MAIN = _src(r"""
    const poly = require('./poly');
    const report = require('./report');

    console.log(report.render('Polynomial values', poly.evaluateAll(poly.POLYNOMIALS, poly.POINTS)));
""")

DETERMINANT_DETERMINANT = _src(r"""
    const MATRICES = [
      { name: 'identity3', grid: [[1, 0, 0], [0, 1, 0], [0, 0, 1]] },
      { name: 'rotation3', grid: [[0, -1, 0], [1, 0, 0], [0, 0, 1]] },
      { name: 'triangular3', grid: [[2, 5, 9], [0, 3, 4], [0, 0, 7]] },
      { name: 'singular2', grid: [[1, 2], [2, 4]] },
      { name: 'scale4', grid: [[2, 0, 0, 0], [0, 3, 0, 0], [0, 0, 4, 0], [0, 0, 0, 5]] },
      { name: 'single1', grid: [[-6]] }
    ];

    function minor(grid, row, col) {
      const out = [];
      for (let r = 0; r < grid.length; r += 1) {
        if (r === row) {
          continue;
        }
        const line = [];
        for (let c = 0; c < grid[r].length; c += 1) {
          if (c !== col) {
            line.push(grid[r][c]);
          }
        }
        out.push(line);
      }
      return out;
    }

    function determinant(grid) {
      const size = grid.length;
      if (size === 1) {
        return grid[0][0];
      }
      if (size === 2) {
        return grid[0][0] * grid[1][1] - grid[0][1] * grid[1][0];
      }
      let total = 0;
      for (let c = 0; c < size; c += 1) {
        const sign = c % 2 === 0 ? 1 : -1;
        total += sign * grid[0][c] * determinant(minor(grid, 0, c));
      }
      return total;
    }

    function determinantAll(matrices) {
      const rows = [];
      for (let i = 0; i < matrices.length; i += 1) {
        const matrix = matrices[i];
        const value = determinant(matrix.grid);
        rows.push({
          name: matrix.name,
          size: matrix.grid.length,
          value: value,
          singular: value === 0
        });
      }
      return rows;
    }

    module.exports = {
      MATRICES: MATRICES,
      minor: minor,
      determinant: determinant,
      determinantAll: determinantAll
    };
""")

DETERMINANT_REPORT = _src(r"""
    function pad(text, width) {
      let out = String(text);
      while (out.length < width) {
        out += ' ';
      }
      return out;
    }

    function render(title, rows) {
      const lines = [title];
      let singular = 0;
      for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        if (row.singular) {
          singular += 1;
        }
        lines.push(
          '  ' + pad(row.name, 12) + row.size + 'x' + row.size +
          ' det ' + pad(row.value, 5) + (row.singular ? ' singular' : '')
        );
      }
      lines.push('singular matrices: ' + singular);
      return lines.join('\n');
    }

    module.exports = { pad: pad, render: render };
""")

DETERMINANT_MAIN = _src(r"""
    const matrices = require('./determinant');
    const report = require('./report');

    console.log(report.render('Determinants', matrices.determinantAll(matrices.MATRICES)));
""")

DURATION_DURATION = _src(r"""
    const DURATIONS = [0, 5, 59, 60, 61, 3599, 3600, 3661, 7325, 86400, 90061];

    function pad2(value) {
      return value < 10 ? '0' + value : String(value);
    }

    function split(seconds) {
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      const rest = seconds % 60;
      return { hours: hours, minutes: minutes, seconds: rest };
    }

    function clock(seconds) {
      const parts = split(seconds);
      return pad2(parts.hours) + ':' + pad2(parts.minutes) + ':' + pad2(parts.seconds);
    }

    function human(seconds) {
      const parts = split(seconds);
      const bits = [];
      if (parts.hours > 0) {
        bits.push(parts.hours + 'h');
      }
      if (parts.minutes > 0) {
        bits.push(parts.minutes + 'm');
      }
      if (parts.seconds > 0 || bits.length === 0) {
        bits.push(parts.seconds + 's');
      }
      return bits.join(' ');
    }

    function formatAll(durations) {
      const rows = [];
      let longest = durations[0];
      for (let i = 0; i < durations.length; i += 1) {
        const seconds = durations[i];
        if (seconds > longest) {
          longest = seconds;
        }
        rows.push({
          seconds: seconds,
          clock: clock(seconds),
          human: human(seconds)
        });
      }
      return { rows: rows, longest: longest };
    }

    module.exports = {
      DURATIONS: DURATIONS,
      pad2: pad2,
      split: split,
      clock: clock,
      human: human,
      formatAll: formatAll
    };
""")

DURATION_REPORT = _src(r"""
    function pad(text, width) {
      let out = String(text);
      while (out.length < width) {
        out = ' ' + out;
      }
      return out;
    }

    function render(title, formatted) {
      const lines = [title];
      for (let i = 0; i < formatted.rows.length; i += 1) {
        const row = formatted.rows[i];
        lines.push(
          '  ' + pad(row.seconds, 6) + 's  ' + row.clock + '  ' + row.human
        );
      }
      lines.push('longest ' + formatted.longest + 's');
      return lines.join('\n');
    }

    module.exports = { pad: pad, render: render };
""")

DURATION_MAIN = _src(r"""
    const duration = require('./duration');
    const report = require('./report');

    console.log(report.render('Durations', duration.formatAll(duration.DURATIONS)));
""")

ANAGRAMS_ANAGRAMS = _src(r"""
    const WORDS = [
      'listen', 'silent', 'enlist', 'google', 'gogole', 'cat',
      'act', 'tac', 'dog', 'god', 'odg', 'hello', 'world'
    ];

    function signature(word) {
      return word.split('').sort().join('');
    }

    function group(words) {
      const order = [];
      const buckets = {};
      for (let i = 0; i < words.length; i += 1) {
        const word = words[i];
        const key = signature(word);
        if (buckets[key] === undefined) {
          buckets[key] = [word];
          order.push(key);
        } else {
          buckets[key].push(word);
        }
      }
      const groups = [];
      for (let i = 0; i < order.length; i += 1) {
        groups.push(buckets[order[i]].slice().sort());
      }
      return groups;
    }

    function largest(groups) {
      let best = groups[0];
      for (let i = 1; i < groups.length; i += 1) {
        if (groups[i].length > best.length) {
          best = groups[i];
        }
      }
      return best;
    }

    module.exports = {
      WORDS: WORDS,
      signature: signature,
      group: group,
      largest: largest
    };
""")

ANAGRAMS_REPORT = _src(r"""
    function render(title, groups, biggest) {
      const lines = [title];
      for (let i = 0; i < groups.length; i += 1) {
        lines.push('  ' + groups[i].join(' '));
      }
      lines.push('families ' + groups.length + ', largest ' + biggest.join(' '));
      return lines.join('\n');
    }

    module.exports = { render: render };
""")

ANAGRAMS_MAIN = _src(r"""
    const anagrams = require('./anagrams');
    const report = require('./report');

    const groups = anagrams.group(anagrams.WORDS);
    console.log(report.render('Anagram families', groups, anagrams.largest(groups)));
""")


BINARY_SEARCH_SEARCH = _src(r"""
    const VALUES = [2, 4, 6, 8, 10, 12, 14];
    const TARGETS = [8, 5];

    function trace(values, target) {
      const probes = [];
      let lo = 0;
      let hi = values.length - 1;
      let found = -1;
      while (lo <= hi) {
        const mid = lo + Math.floor((hi - lo) / 2);
        probes.push({ index: mid, value: values[mid] });
        if (values[mid] === target) {
          found = mid;
          break;
        }
        if (values[mid] < target) {
          lo = mid + 1;
        } else {
          hi = mid - 1;
        }
      }
      return { target: target, probes: probes, found: found };
    }

    function traceAll(values, targets) {
      const rows = [];
      for (let i = 0; i < targets.length; i += 1) {
        rows.push(trace(values, targets[i]));
      }
      return rows;
    }

    module.exports = {
      VALUES: VALUES,
      TARGETS: TARGETS,
      trace: trace,
      traceAll: traceAll,
    };
""")

BINARY_SEARCH_REPORT = _src(r"""
    function render(rows) {
      const lines = [];
      for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        lines.push('search ' + row.target);
        for (let p = 0; p < row.probes.length; p += 1) {
          lines.push('probe ' + row.probes[p].index + ' value ' + row.probes[p].value);
        }
        if (row.found >= 0) {
          lines.push('found ' + row.target + ' at index ' + row.found);
        } else {
          lines.push('not found ' + row.target);
        }
      }
      return lines.join('\n');
    }

    module.exports = { render: render };
""")

BINARY_SEARCH_MAIN = _src(r"""
    const search = require('./search');
    const report = require('./report');

    console.log(report.render(search.traceAll(search.VALUES, search.TARGETS)));
""")

LRU_CACHE_CACHE = _src(r"""
    const CAPACITY = 2;
    const OPERATIONS = [
      { op: 'get', key: 'a' },
      { op: 'put', key: 'b' },
      { op: 'get', key: 'a' },
      { op: 'put', key: 'c' },
      { op: 'get', key: 'b' },
      { op: 'get', key: 'a' },
    ];

    function replay(operations, capacity) {
      const order = [];
      const resident = {};
      const events = [];

      function touch(key) {
        const at = order.indexOf(key);
        if (at >= 0) {
          order.splice(at, 1);
        }
        order.push(key);
      }

      for (let i = 0; i < operations.length; i += 1) {
        const operation = operations[i];
        const key = operation.key;
        if (operation.op === 'get') {
          if (resident[key]) {
            touch(key);
            events.push('get ' + key + ' hit');
          } else {
            events.push('get ' + key + ' miss');
            // A miss fills an empty slot; a full cache is left alone.
            if (order.length < capacity) {
              resident[key] = true;
              order.push(key);
            }
          }
        } else if (resident[key]) {
          touch(key);
          events.push('put ' + key);
        } else {
          let evicted = '';
          if (order.length >= capacity) {
            evicted = order.shift();
            delete resident[evicted];
          }
          resident[key] = true;
          order.push(key);
          events.push('put ' + key + (evicted ? ' evict ' + evicted : ''));
        }
      }
      return events;
    }

    module.exports = { CAPACITY: CAPACITY, OPERATIONS: OPERATIONS, replay: replay };
""")

LRU_CACHE_REPORT = _src(r"""
    function render(events) {
      const lines = [];
      for (let i = 0; i < events.length; i += 1) {
        lines.push(events[i]);
      }
      return lines.join('\n');
    }

    module.exports = { render: render };
""")

LRU_CACHE_MAIN = _src(r"""
    const cache = require('./cache');
    const report = require('./report');

    console.log(report.render(cache.replay(cache.OPERATIONS, cache.CAPACITY)));
""")

ISBN_ISBN = _src(r"""
    const CODES = ['0306406152', '0306406153'];

    function digit(text) {
      const value = text.charAt(0).toUpperCase();
      return value === 'X' ? 10 : Number(value);
    }

    function expectedCheck(code) {
      let total = 0;
      for (let i = 0; i < 9; i += 1) {
        total += digit(code.charAt(i)) * (10 - i);
      }
      const rest = (11 - (total % 11)) % 11;
      return rest === 10 ? 'X' : String(rest);
    }

    function validate(code) {
      const expected = expectedCheck(code);
      return {
        code: code,
        check: expected,
        valid: code.charAt(9).toUpperCase() === expected,
      };
    }

    function validateAll(codes) {
      const rows = [];
      for (let i = 0; i < codes.length; i += 1) {
        rows.push(validate(codes[i]));
      }
      return rows;
    }

    module.exports = {
      CODES: CODES,
      expectedCheck: expectedCheck,
      validate: validate,
      validateAll: validateAll,
    };
""")

ISBN_REPORT = _src(r"""
    function render(rows) {
      const lines = [];
      for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        lines.push(
          row.code + ' ' + (row.valid ? 'valid' : 'invalid') + ' check ' + row.check
        );
      }
      return lines.join('\n');
    }

    module.exports = { render: render };
""")

ISBN_MAIN = _src(r"""
    const isbn = require('./isbn');
    const report = require('./report');

    console.log(report.render(isbn.validateAll(isbn.CODES)));
""")

VENDING_STOCK = _src(r"""
    const COINS = [50, 25, 20, 10, 5];
    const PURCHASES = [
      { price: 65, paid: 100 },
      { price: 130, paid: 200 },
    ];

    function dispense(purchases, coins) {
      const rows = [];
      for (let i = 0; i < purchases.length; i += 1) {
        const purchase = purchases[i];
        let left = purchase.paid - purchase.price;
        const parts = [];
        for (let c = 0; c < coins.length; c += 1) {
          const count = Math.floor(left / coins[c]);
          if (count > 0) {
            parts.push({ coin: coins[c], count: count });
            left -= count * coins[c];
          }
        }
        rows.push({
          price: purchase.price,
          paid: purchase.paid,
          change: purchase.paid - purchase.price,
          parts: parts,
          remainder: left,
        });
      }
      return rows;
    }

    module.exports = { COINS: COINS, PURCHASES: PURCHASES, dispense: dispense };
""")

VENDING_REPORT = _src(r"""
    function render(rows) {
      const lines = [];
      for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        lines.push('price ' + row.price + ' paid ' + row.paid + ' change ' + row.change);
        for (let p = 0; p < row.parts.length; p += 1) {
          lines.push(row.parts[p].count + ' x ' + row.parts[p].coin);
        }
      }
      return lines.join('\n');
    }

    module.exports = { render: render };
""")

VENDING_MAIN = _src(r"""
    const stock = require('./stock');
    const report = require('./report');

    console.log(report.render(stock.dispense(stock.PURCHASES, stock.COINS)));
""")

LIFE_LIFE = _src(r"""
    const GRID = [
      [0, 1, 0, 0],
      [0, 1, 0, 0],
      [0, 1, 0, 0],
      [0, 0, 0, 0],
    ];

    function neighbours(grid, row, col) {
      let live = 0;
      for (let r = row - 1; r <= row + 1; r += 1) {
        if (r < 0 || r >= grid.length) {
          continue;
        }
        for (let c = col - 1; c <= col + 1; c += 1) {
          if (c < 0 || c >= grid[r].length) {
            continue;
          }
          if (r === row && c === col) {
            continue;
          }
          if (grid[r][c]) {
            live += 1;
          }
        }
      }
      return live;
    }

    function step(grid) {
      const next = [];
      for (let r = 0; r < grid.length; r += 1) {
        const line = [];
        for (let c = 0; c < grid[r].length; c += 1) {
          const count = neighbours(grid, r, c);
          if (grid[r][c]) {
            line.push(count === 2 || count === 3 ? 1 : 0);
          } else {
            line.push(count === 3 ? 1 : 0);
          }
        }
        next.push(line);
      }
      return next;
    }

    function population(grid) {
      let live = 0;
      for (let r = 0; r < grid.length; r += 1) {
        for (let c = 0; c < grid[r].length; c += 1) {
          live += grid[r][c] ? 1 : 0;
        }
      }
      return live;
    }

    module.exports = {
      GRID: GRID,
      neighbours: neighbours,
      step: step,
      population: population,
    };
""")

LIFE_REPORT = _src(r"""
    function render(grid, live) {
      const lines = [];
      for (let r = 0; r < grid.length; r += 1) {
        lines.push('row ' + grid[r].join(''));
      }
      lines.push('live ' + live);
      return lines.join('\n');
    }

    module.exports = { render: render };
""")

LIFE_MAIN = _src(r"""
    const life = require('./life');
    const report = require('./report');

    const next = life.step(life.GRID);
    console.log(report.render(next, life.population(next)));
""")


def sets() -> list[dict]:
    return [
        {
            "title": "javascript cli set - invoice totals by tax band",
            "description": ("Parses an embedded item list and prints each line with its "
                            "tax band, the subtotal and the tax total."),
            "family": "invoice",
            "files": [
                {"path": "main.js", "content": INVOICE_MAIN},
                {"path": "inventory.js", "content": INVOICE_INVENTORY},
                {"path": "report.js", "content": INVOICE_REPORT},
            ],
            "target": "inventory.js",
        },
        {
            "title": "javascript cli set - word frequency report",
            "description": ("Tokenises an embedded paragraph and prints the five most "
                            "common words with their counts."),
            "family": "word-frequency",
            "files": [
                {"path": "main.js", "content": WORDS_MAIN},
                {"path": "words.js", "content": WORDS_WORDS},
                {"path": "report.js", "content": WORDS_REPORT},
            ],
            "target": "words.js",
        },
        {
            "title": "javascript cli set - merged busy blocks",
            "description": ("Merges overlapping meetings from an embedded list and "
                            "prints the busy blocks with the total busy minutes."),
            "family": "intervals",
            "files": [
                {"path": "main.js", "content": INTERVALS_MAIN},
                {"path": "intervals.js", "content": INTERVALS_INTERVALS},
                {"path": "report.js", "content": INTERVALS_REPORT},
            ],
            "target": "intervals.js",
        },
        {
            "title": "javascript cli set - grade bands histogram",
            "description": ("Counts an embedded score list into letter bands and prints "
                            "a bar per band with the mean and the leading band."),
            "family": "grades",
            "files": [
                {"path": "main.js", "content": GRADES_MAIN},
                {"path": "grades.js", "content": GRADES_GRADES},
                {"path": "report.js", "content": GRADES_REPORT},
            ],
            "target": "grades.js",
        },
        {
            "title": "javascript cli set - roman numerals table",
            "description": ("Converts an embedded number list to roman numerals and "
                            "flags the values outside the classical range."),
            "family": "roman",
            "files": [
                {"path": "main.js", "content": ROMAN_MAIN},
                {"path": "roman.js", "content": ROMAN_ROMAN},
                {"path": "report.js", "content": ROMAN_REPORT},
            ],
            "target": "roman.js",
        },
        {
            "title": "javascript cli set - running balance ledger",
            "description": ("Walks an embedded entry list and prints the running balance "
                            "with an overdraft or low-funds status per line."),
            "family": "ledger",
            "files": [
                {"path": "main.js", "content": LEDGER_MAIN},
                {"path": "ledger.js", "content": LEDGER_LEDGER},
                {"path": "report.js", "content": LEDGER_REPORT},
            ],
            "target": "ledger.js",
        },
        {
            "title": "javascript cli set - ticket price tiers",
            "description": ("Prices an embedded booking list by zone and group discount "
                            "and prints each line with its net price and the total."),
            "family": "tickets",
            "files": [
                {"path": "main.js", "content": TICKETS_MAIN},
                {"path": "tickets.js", "content": TICKETS_TICKETS},
                {"path": "report.js", "content": TICKETS_REPORT},
            ],
            "target": "tickets.js",
        },
        {
            "title": "javascript cli set - paragraph wrap with ruler",
            "description": ("Wraps an embedded paragraph to a fixed width and prints it "
                            "under a ruler so the wrap can be checked at a glance."),
            "family": "wrap",
            "files": [
                {"path": "main.js", "content": WRAP_MAIN},
                {"path": "wrap.js", "content": WRAP_WRAP},
                {"path": "report.js", "content": WRAP_REPORT},
            ],
            "target": "wrap.js",
        },
        {
            "title": "javascript cli set - transposed grid with row sums",
            "description": ("Transposes an embedded grid and prints each row alongside "
                            "its sum."),
            "family": "matrix",
            "files": [
                {"path": "main.js", "content": MATRIX_MAIN},
                {"path": "matrix.js", "content": MATRIX_MATRIX},
                {"path": "report.js", "content": MATRIX_REPORT},
            ],
            "target": "matrix.js",
        },
        {
            "title": "javascript cli set - polynomial values by horner",
            "description": ("Evaluates embedded coefficient lists at several points by "
                            "Horner's method and prints each value with the degree and "
                            "the peak."),
            "family": "horner-polynomial",
            "files": [
                {"path": "main.js", "content": POLY_MAIN},
                {"path": "poly.js", "content": POLY_POLY},
                {"path": "report.js", "content": POLY_REPORT},
            ],
            "target": "poly.js",
        },
        {
            "title": "javascript cli set - matrix determinants",
            "description": ("Expands embedded small square matrices into determinants by "
                            "cofactors and prints each size, value and singular flag."),
            "family": "matrix-determinant",
            "files": [
                {"path": "main.js", "content": DETERMINANT_MAIN},
                {"path": "determinant.js", "content": DETERMINANT_DETERMINANT},
                {"path": "report.js", "content": DETERMINANT_REPORT},
            ],
            "target": "determinant.js",
        },
        {
            "title": "javascript cli set - duration formatting",
            "description": ("Formats embedded second counts as hours minutes seconds and "
                            "as a short human form, with the longest duration."),
            "family": "duration-format",
            "files": [
                {"path": "main.js", "content": DURATION_MAIN},
                {"path": "duration.js", "content": DURATION_DURATION},
                {"path": "report.js", "content": DURATION_REPORT},
            ],
            "target": "duration.js",
        },
        {
            "title": "javascript cli set - anagram families",
            "description": ("Groups an embedded word list into anagram families by sorted "
                            "signature and prints each family with the largest one."),
            "family": "anagram-groups",
            "files": [
                {"path": "main.js", "content": ANAGRAMS_MAIN},
                {"path": "anagrams.js", "content": ANAGRAMS_ANAGRAMS},
                {"path": "report.js", "content": ANAGRAMS_REPORT},
            ],
            "target": "anagrams.js",
        },
        {
            "title": "binary search trace over a sorted list",
            "description": ("Searches an embedded sorted list for two targets and prints "
                            "every probe index and value before the verdict."),
            "family": "binary-search-trace",
            "files": [
                {"path": "main.js", "content": BINARY_SEARCH_MAIN},
                {"path": "search.js", "content": BINARY_SEARCH_SEARCH},
                {"path": "report.js", "content": BINARY_SEARCH_REPORT},
            ],
            "target": "search.js",
        },
        {
            "title": "lru cache simulation with capacity two",
            "description": ("Replays an embedded get and put sequence against a "
                            "capacity-two cache and prints each hit, miss and eviction."),
            "family": "lru-cache-simulation",
            "files": [
                {"path": "main.js", "content": LRU_CACHE_MAIN},
                {"path": "cache.js", "content": LRU_CACHE_CACHE},
                {"path": "report.js", "content": LRU_CACHE_REPORT},
            ],
            "target": "cache.js",
        },
        {
            "title": "isbn ten checksum validation",
            "description": ("Validates embedded ISBN-10 codes and prints each code with "
                            "the check digit it should carry."),
            "family": "isbn-checksum",
            "files": [
                {"path": "main.js", "content": ISBN_MAIN},
                {"path": "isbn.js", "content": ISBN_ISBN},
                {"path": "report.js", "content": ISBN_REPORT},
            ],
            "target": "isbn.js",
        },
        {
            "title": "vending machine change by coin count",
            "description": ("Dispenses change for embedded purchases and prints the coins "
                            "returned per denomination."),
            "family": "vending-change",
            "files": [
                {"path": "main.js", "content": VENDING_MAIN},
                {"path": "stock.js", "content": VENDING_STOCK},
                {"path": "report.js", "content": VENDING_REPORT},
            ],
            "target": "stock.js",
        },
        {
            "title": "conway life step on a four by four grid",
            "description": ("Advances an embedded four by four grid by one generation "
                            "and prints the next grid with its live-cell count."),
            "family": "game-of-life-step",
            "files": [
                {"path": "main.js", "content": LIFE_MAIN},
                {"path": "life.js", "content": LIFE_LIFE},
                {"path": "report.js", "content": LIFE_REPORT},
            ],
            "target": "life.js",
        },
    ]
