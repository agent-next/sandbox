#!/usr/bin/env python3
"""The judge's own final-answer extractor.

Written from the task definition (the final numeric answer of a GSM8K
solution), never from the artifact's `extracted_answer` field. This is the
independent oracle half of gate 2: the artifact is free to use its own
extractor, and the judge scores the raw generation text with this one.

Rules, in order:

1. a line matching ``final answer: <number>`` (case-insensitive) wins;
2. otherwise the last number in the text;
3. ``#### <number>`` (the GSM8K gold marker) is honoured as a synonym.

A number is an optionally signed integer or decimal, with commas allowed
between digits. Commas are stripped and a trailing ``.0`` is dropped, so
``1,000`` and ``1000.0`` are the same value.
"""

import re

NUMBER = r"[-+]?(?:\d[\d,]*)(?:\.\d+)?"
FINAL_RE = re.compile(r"final\s*answer\s*[:\-]?\s*(\**\s*" + NUMBER + r")",
                      re.IGNORECASE)
HASH_RE = re.compile(r"####\s*(\**\s*" + NUMBER + r")")
ANY_RE = re.compile(NUMBER)


def _normalise(raw):
    """'1,000.0' -> '1000'; '-3.50' -> '-3.5'; returns None if unusable."""
    if raw is None:
        return None
    s = raw.strip().lstrip("*").strip().replace(",", "")
    if not s or s in ("+", "-", "."):
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    if value == int(value):
        return str(int(value))
    return repr(round(value, 6))


def extract(text):
    """Return the normalised final answer of `text`, or None."""
    if not isinstance(text, str) or not text.strip():
        return None
    for regex in (FINAL_RE, HASH_RE):
        hits = regex.findall(text)
        if hits:
            value = _normalise(hits[-1])
            if value is not None:
                return value
    hits = ANY_RE.findall(text)
    if not hits:
        return None
    return _normalise(hits[-1])


def first_number(text):
    """The mutant extractor: takes the FIRST number in the text."""
    if not isinstance(text, str):
        return None
    hits = ANY_RE.findall(text)
    if not hits:
        return None
    return _normalise(hits[0])


if __name__ == "__main__":
    import sys

    for line in sys.stdin:
        print(extract(line))
