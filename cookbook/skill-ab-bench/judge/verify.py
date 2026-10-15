#!/usr/bin/env python3
"""Independent oracle for the skill-ab-bench judge.

This module is the *specification* of a correct answer for every task in
`judge/tasks.json`, written deliberately in a different style from
`judge/gen_inputs.py` (explicit character scanning here, regular
expressions there).  The judge recomputes the expected answer from the
pinned task input alone and compares it, byte for byte, with the answer the
harness recorded -- so a pass verdict the harness invented cannot survive.

Two implementations of the same spec must agree: `judge/grade.py` gate G4
checks `expected_answer(task) == task["answer"]` for every task and fails
closed when they drift apart.
"""

from __future__ import annotations

# Allowed characters in an e-mail local part, for the re07 task.
_LOCAL_CHARS = set("abcdefghijklmnopqrstuvwxyz"
                   "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                   "0123456789._+-")


def _active_lines(text: str, active_only: bool) -> list[str]:
    """Config lines, optionally dropping '#' and ';' comment lines."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if active_only and (stripped.startswith("#") or stripped.startswith(";")):
            continue
        out.append(line)
    return out


def _split_kv(line: str) -> tuple[str, str] | None:
    """Split 'key = value' -> (key, value); None when there is no '='."""
    if "=" not in line:
        return None
    key, _, value = line.partition("=")
    return key.strip(), value


def _ini_value(text: str, key: str, section: str | None = None,
               last: bool = False, case_sensitive: bool = False,
               active_only: bool = False) -> str:
    """Read a value out of an INI-style snippet, scanning line by line.

    `section` selects the (first or last) block whose header is exactly
    `[section]`; None scans the whole file.  `case_sensitive` compares the
    key byte for byte.  `active_only` ignores comment lines.
    """
    lines = _active_lines(text, active_only)
    if section is not None:
        blocks: list[list[str]] = []
        current: list[str] | None = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                if stripped == "[" + section + "]":
                    current = []
                    blocks.append(current)
                else:
                    current = None
                continue
            if current is not None:
                current.append(line)
        lines = [ln for blk in (blocks[-1:] if last else blocks[:1]) for ln in blk]

    hits: list[str] = []
    for line in lines:
        pair = _split_kv(line)
        if pair is None:
            continue
        k, v = pair
        if case_sensitive:
            if k != key:
                continue
        elif k.lower() != key.lower():
            continue
        hits.append(v.strip())
    if not hits:
        return ""
    return hits[-1] if last else hits[0]


def _csv_lookup(text: str, row_key: str, col: str) -> str:
    """Return one CSV cell by row key and column name."""
    rows = [ln for ln in text.splitlines() if ln.strip()]
    header = [c.strip() for c in rows[0].split(",")]
    want = header.index(col)
    for row in rows[1:]:
        cells = row.split(",")
        if cells and cells[0].strip() == row_key:
            return cells[want].strip()
    return ""


def _strip_comment(value: str) -> str:
    """Drop trailing ' #' comments from a config value."""
    for marker in (" #", "\t#"):
        at = value.find(marker)
        if at >= 0:
            return value[:at]
    return value


# ---------------------------------------------------------------------------
# the oracle functions, one per task kind (no regular expression is used)
# ---------------------------------------------------------------------------

def _digits_join(text: str) -> str:
    runs: list[str] = []
    current: list[str] = []
    for ch in text:
        if ch.isdigit():
            current.append(ch)
        elif current:
            runs.append("".join(current))
            current = []
    if current:
        runs.append("".join(current))
    return "|".join(runs)


def _first_port(text: str) -> str:
    marker = "port="
    at = text.find(marker)
    if at < 0:
        return ""
    i = at + len(marker)
    out = []
    while i < len(text) and text[i].isdigit():
        out.append(text[i])
        i += 1
    return "".join(out)


def _quoted(text: str) -> str:
    """The whole quoted string, honouring backslash escapes."""
    start = text.find('"')
    if start < 0:
        return ""
    i = start + 1
    out = ['"']
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            out.append(ch)
            out.append(text[i + 1])
            i += 2
            continue
        out.append(ch)
        if ch == '"':
            break
        i += 1
    return "".join(out)


def _dotted_quad(text: str) -> str:
    """The first four-group dotted number in the text."""
    i = 0
    while i < len(text):
        if text[i].isdigit():
            j = i
            while j < len(text) and (text[j].isdigit() or text[j] == "."):
                j += 1
            candidate = text[i:j]
            parts = candidate.split(".")
            if len(parts) == 4 and all(p.isdigit() and 1 <= len(p) <= 3
                                       for p in parts):
                return candidate
            i = j
            continue
        i += 1
    return ""


def _version(text: str) -> str:
    """The first version: a digit run, then any number of '.digit' groups.

    A trailing dot is a sentence period, not part of the version: `2.10.`
    yields `2.10`, where a bare `[0-9.]+` scan would swallow the period.
    """
    i = 0
    while i < len(text):
        if text[i].isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            while j + 1 < len(text) and text[j] == "." and text[j + 1].isdigit():
                j += 1
                while j < len(text) and text[j].isdigit():
                    j += 1
            return text[i:j]
        i += 1
    return ""


def _word_count(text: str, word: str) -> str:
    tokens: list[str] = []
    current: list[str] = []
    for ch in text:
        if ch.isalnum():
            current.append(ch)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return str(sum(1 for t in tokens if t.lower() == word.lower()))


def _email_local(text: str) -> str:
    at = text.find("@")
    if at <= 0:
        return ""
    i = at
    while i > 0 and text[i - 1] in _LOCAL_CHARS:
        i -= 1
    return text[i:at]


def _trailing_int(text: str) -> str:
    """The last integer, ignoring any trailing whitespace/newline."""
    i = len(text)
    while i > 0 and text[i - 1].isspace():
        i -= 1
    end = i
    while i > 0 and text[i - 1].isdigit():
        i -= 1
    return text[i:end]


def expected_answer(task: dict) -> str:
    """The correct answer for one task, computed from its pinned input."""
    tid = task["task_id"]
    kind = task["kind"]
    params = task["params"]
    text = task["input"]

    if kind == "kv":
        if "csv_row" in params:
            return _csv_lookup(text, params["csv_row"], params["csv_col"])
        value = _ini_value(
            text,
            params["key"],
            section=params.get("section"),
            last=bool(params.get("last", False)),
            case_sensitive=bool(params.get("case_sensitive", False)),
            active_only=bool(params.get("active_only", False)),
        )
        if params.get("strip_comment"):
            value = _strip_comment(value).strip()
        return value

    if kind == "re":
        how = params["how"]
        if how == "digits_join":
            return _digits_join(text)
        if how == "first_port":
            return _first_port(text)
        if how == "quoted":
            return _quoted(text)
        if how == "dotted_quad":
            return _dotted_quad(text)
        if how == "version":
            return _version(text)
        if how == "word_count":
            return _word_count(text, params["word"])
        if how == "email_local":
            return _email_local(text)
        if how == "trailing_int":
            return _trailing_int(text)
    raise KeyError(f"no oracle for task {tid}")


def verify(task: dict, answer: str) -> bool:
    """True iff `answer` is the correct answer for `task` (byte exact)."""
    if not isinstance(answer, str):
        return False
    return answer == expected_answer(task)


def load_tasks(path) -> list[dict]:
    import json
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["tasks"]
