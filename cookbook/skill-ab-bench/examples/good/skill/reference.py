"""regex-cookbook skill: reference implementations.

This file is the skill package's *technique table*.  Every entry is written
the way the SKILL.md essay argues it should be:

  * a value reader that scopes sections, honours case and ignores comments
  * regexes anchored so they cannot run past the character they stop at
  * escapes handled, not hoped away
  * word boundaries where a substring count would lie

The demo's judge never imports this file; the skill arm policy does, and the
judge independently recomputes every verdict from the task's pinned input.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# config values
# ---------------------------------------------------------------------------

def _sections(text: str) -> list[tuple[str, list[str]]]:
    """Split an INI-style snippet into (section, lines) pairs."""
    out: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] = ("", [])
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = (stripped[1:-1], [])
            out.append(current)
        else:
            current[1].append(line)
    return out


def _strip_comment(value: str) -> str:
    """Drop a trailing ' #' comment and trim what is left.

    Quotes are part of the value and survive, per the task contract.
    """
    for marker in (" #", "\t#"):
        at = value.find(marker)
        if at >= 0:
            value = value[:at]
    return value.strip()


def ini_lookup(text: str, key: str, section: str | None = None,
               last: bool = False, case_sensitive: bool = False,
               active_only: bool = False, strip_comment: bool = False,
               **_unused) -> str:
    """Read `key` out of a config snippet the way the essay describes.

    section        only look inside `[section]` blocks (first, or last when
                   `last=True`); None scans the whole file
    case_sensitive compare the key byte for byte instead of case-folded
    active_only    skip '#' and ';' comment lines entirely
    strip_comment  drop a trailing comment from the value before trimming
    """
    if section is None:
        lines = text.splitlines()
    else:
        blocks = [ls for name, ls in _sections(text) if name == section]
        blocks = blocks[-1:] if last else blocks[:1]
        lines = [ln for blk in blocks for ln in blk]

    hits: list[str] = []
    for line in lines:
        stripped = line.strip()
        if active_only and (stripped.startswith("#") or stripped.startswith(";")):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if case_sensitive:
            if k != key:
                continue
        elif k.lower() != key.lower():
            continue
        value = v.strip()
        if strip_comment:
            value = _strip_comment(value)
        hits.append(value)
    if not hits:
        return ""
    return hits[-1] if last else hits[0]


def csv_lookup(text: str, row_key: str, col: str) -> str:
    """One CSV cell by row key and column name."""
    rows = [ln for ln in text.splitlines() if ln.strip()]
    header = [c.strip() for c in rows[0].split(",")]
    want = header.index(col)
    for row in rows[1:]:
        cells = row.split(",")
        if cells and cells[0].strip() == row_key:
            return cells[want].strip()
    return ""


# ---------------------------------------------------------------------------
# the regex techniques
# ---------------------------------------------------------------------------

def digits_join(text: str) -> str:
    """Every number in the text, '|'-separated."""
    return "|".join(re.findall(r"\d+", text))


def first_port(text: str) -> str:
    """The first port number: `\\d+` stops at the comma, where a greedy
    `port=.*` would swallow both ports and the semicolon."""
    match = re.search(r"\bport=(\d+)", text)
    return match.group(1) if match else ""


def quoted(text: str) -> str:
    """The whole quoted string, escapes included.

    `"(?:[^"\\]|\\.)*"` reads a quote, then either a non-quote-non-backslash
    character or a backslash followed by anything, until the closing quote.
    """
    match = re.search(r'"(?:[^"\\]|\\.)*"', text)
    return match.group(0) if match else ""


def dotted_quad(text: str) -> str:
    """The first IPv4 address.

    `\\b` before the digit run keeps `::1` out: a bare `1` is not a
    word-start, so the v6 host cannot match.
    """
    match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
    return match.group(0) if match else ""


def version(text: str) -> str:
    """A full multi-part version: keep consuming `.digits` groups.

    Anchoring each group on a *digit* after the dot is what stops a
    sentence-ending period from being read as part of the version:
    `2.10.` yields `2.10`, not `2.10.`.
    """
    match = re.search(r"\d+(?:\.\d+)+", text)
    return match.group(0) if match else ""


def word_count(text: str, word: str) -> str:
    """Count whole words, any case -- not substring occurrences."""
    return str(len(re.findall(rf"(?i)\b{re.escape(word)}\b", text)))


def email_local(text: str) -> str:
    """The local part of an address, '+' included.

    `[\\w.+-]+` is the local-part character class; `\\w+@` would stop at the
    '+' and report a shorter answer.
    """
    match = re.search(r"[\w.+-]+@", text)
    return match.group(0)[:-1] if match else ""


def trailing_int(text: str) -> str:
    """The last integer: `$` anchors the match at the end of the line."""
    match = re.search(r"(\d+)$", text)
    return match.group(1) if match else ""


TECHNIQUES = {
    "ini_lookup": ini_lookup,
    "csv_lookup": csv_lookup,
    "digits_join": digits_join,
    "first_port": first_port,
    "quoted": quoted,
    "dotted_quad": dotted_quad,
    "version": version,
    "word_count": word_count,
    "email_local": email_local,
    "trailing_int": trailing_int,
}
