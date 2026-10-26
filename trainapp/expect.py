"""expect — what a correct run prints, read off the requirement itself.

The gate compares stdout when it knows what to expect, and an exit code alone
says only that the program did not crash. The caller's `--expect` is the best
source and the architect's own `expected_stdout` is the second, but neither is
always there: a request typed straight into the app states the answer inside the
sentence — "a program that prints the sum of 2 and 3" — and that is a fact the
requirement carries, not one the model gets to author.

So this module reads the narrow, unambiguous shapes and nothing else:

    prints "Hello, ada"                  -> Hello, ada
    prints 42                            -> 42
    prints the sum of 2 and 3            -> 5
    prints the product of 4 and 6        -> 24
    prints 10 - 3                        -> 7

Anything else returns nothing, and the orchestra falls back to the weaker check
in `wants_output`: a requirement that says it prints must print something. A
derivation is recorded as `derived` in the run copy, because evidence that came
from the sentence is not the same as evidence the caller supplied.

Deliberately not a general English parser, and deliberately not `eval`: an
expression that does not match one of these shapes is left alone rather than
guessed at.
"""
from __future__ import annotations

import re

# "prints", "print", "outputs", "echoes", ... — the verb, then what follows it.
_VERB = r"(?:prints?|outputs?|displays?|echoes?|shows?|writes?|returns?)"
_LITERAL = re.compile(
    _VERB + r"""\s+(?:the\s+(?:text|string|word|message|literal)\s+)?"""
    r"""["']([^"'\n]{1,200})["']""", re.I)
_NUMBER = re.compile(
    _VERB + r"\s+(?:the\s+(?:number|integer|result|value)\s+)?(-?\d+)(?![\d.])", re.I)
_WORD_ARITH = re.compile(
    _VERB + r"\s+the\s+(sum|product|difference|quotient)\s+of\s+"
    r"(-?\d+)\s+and\s+(-?\d+)", re.I)
_SIGN_ARITH = re.compile(
    _VERB + r"\s+(-?\d+)\s*([-+*/x×])\s*(-?\d+)(?![\d.])", re.I)
_OUTPUT_WORD = re.compile(
    r"\b(print|prints|printing|output|outputs|display|displays|echo|echoes|"
    r"show|shows|writes?|stdout)\b", re.I)


def _compute(op: str, left: int, right: int) -> str:
    if op in ("sum", "+"):
        return str(left + right)
    if op in ("product", "*", "x", "×"):
        return str(left * right)
    if op in ("difference", "-"):
        return str(left - right)
    # Quotient: only when it divides exactly. "7 / 2" is 3.5 or 3 depending on
    # the language, so it is not a fact the sentence carries.
    if right == 0 or left % right:
        return ""
    return str(left // right)


def derive(requirement: str) -> dict:
    """`{"expected": "5", "rule": "sum of 2 and 3"}`, or empties when unknown."""
    text = (requirement or "").strip()
    if not text:
        return {"expected": "", "rule": ""}
    match = _LITERAL.search(text)
    if match:
        return {"expected": match.group(1), "rule": "quoted literal"}
    match = _WORD_ARITH.search(text)
    if match:
        op, left, right = match.group(1).lower(), int(match.group(2)), int(match.group(3))
        value = _compute(op, left, right)
        if value:
            return {"expected": value,
                    "rule": f"{op} of {left} and {right}"}
        return {"expected": "", "rule": ""}
    match = _SIGN_ARITH.search(text)
    if match:
        left, op, right = int(match.group(1)), match.group(2), int(match.group(3))
        value = _compute(op, left, right)
        if value:
            return {"expected": value, "rule": f"{left} {op} {right}"}
        return {"expected": "", "rule": ""}
    match = _NUMBER.search(text)
    if match:
        return {"expected": match.group(1), "rule": "plain number"}
    return {"expected": "", "rule": ""}


def wants_output(requirement: str) -> bool:
    """Does the requirement say the program prints anything at all?

    The fallback when nothing can be derived: a program the sentence expects to
    print something, that prints nothing, has not done the job — even if it
    exited 0.
    """
    return bool(_OUTPUT_WORD.search(requirement or ""))
