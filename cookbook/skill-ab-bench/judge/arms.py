#!/usr/bin/env python3
"""The three arm policies of the skill-ab-bench experiment.

An arm is a *policy*: code that answers a parsing task.  The experiment
measures whether the answers change when a skill package is on the desk
next to the working copy.

  skill    loads <skill_dir>/reference.py and answers with its techniques.
  noskill  answers with a plain, plausible first attempt (no reference).
  placebo  reads the README-only skill package and applies its one rule.

Nothing here talks to a model; the numbers are deterministic and the judge
recomputes every verdict (judge/grade.py gate G3), so an arm cannot claim a
pass the oracle would not give it.

The three policies are deliberately different in *method*, not in effort:
each is ~30 lines, and only one of them is right about section scoping,
case sensitivity, comments and greedy matches.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

SKILL_FILE = "reference.py"


# ---------------------------------------------------------------------------
# the no-skill policy: a plausible first attempt
# ---------------------------------------------------------------------------

def noskill_kv(text: str, key: str, **_kw) -> str:
    """First attempt: flatten the file into one dict and look the key up.

    Loses section scoping, case sensitivity and comment state -- which is
    exactly what a config-value task is testing.
    """
    flat: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        flat[k.strip().lower()] = v.strip()          # first occurrence wins
    return flat.get(key.lower(), "")


# A first attempt at each regex family: short, obvious, and wrong whenever
# the input has an escape, a second candidate, or a non-word character.
_NOSKILL_RE = {
    "digits_join": lambda t: "|".join(re.findall(r"\d+", t)),
    "first_port": lambda t: re.search(r"port=(\d+)", t).group(1),
    "quoted": lambda t: re.search(r'"([^"]*)"', t).group(1),
    "dotted_quad": lambda t: re.search(r"(\d+\.){3}\d+", t).group(0),
    "version": lambda t: re.search(r"(\d+\.)+\d+", t).group(0),
    "whole_word_count": lambda t, word: str(t.lower().count(word)),
    "email_local": lambda t: re.search(r"(\w+)@", t).group(1),
    "trailing_int": lambda t: re.search(r"(\d+)$", t).group(1),
}


def noskill_answer(task: dict) -> str:
    params = task["params"]
    if task["kind"] == "kv":
        if "csv_row" in params:
            return _csv_lookup(task["input"], params["csv_row"], params["csv_col"])
        return noskill_kv(task["input"], params["key"])
    fn = _NOSKILL_RE[params["how"]]
    if params["how"] == "whole_word_count":
        return fn(task["input"], params["word"])
    return fn(task["input"])


# ---------------------------------------------------------------------------
# the placebo policy: the README's one rule, applied to the naive lookup
# ---------------------------------------------------------------------------

def placebo_kv(text: str, key: str, **_kw) -> str:
    """What the README tells you: 'trust the last matching line, ignore
    case, and keep comments -- they document intent'."""
    flat: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        flat[k.strip().lower()] = v.strip()          # last occurrence wins
    return flat.get(key.lower(), "")


def placebo_answer(task: dict) -> str:
    """Placebo: the naive regex table, plus the README's lookup rule."""
    params = task["params"]
    if task["kind"] == "kv":
        if "csv_row" in params:
            return _csv_lookup(task["input"], params["csv_row"], params["csv_col"])
        return placebo_kv(task["input"], params["key"])
    fn = _NOSKILL_RE[params["how"]]
    if params["how"] == "whole_word_count":
        return fn(task["input"], params["word"])
    return fn(task["input"])


# ---------------------------------------------------------------------------
# the skill policy: load the skill package and use what it teaches
# ---------------------------------------------------------------------------

def load_skill(skill_dir: str | Path):
    """Import <skill_dir>/reference.py; returns its TECHNIQUES table."""
    path = Path(skill_dir) / SKILL_FILE
    if not path.is_file():
        raise FileNotFoundError(f"skill package has no {SKILL_FILE}: {path}")
    spec = importlib.util.spec_from_file_location("skill_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)               # the skill is code we run
    if not hasattr(module, "TECHNIQUES"):
        raise AttributeError(f"{path} defines no TECHNIQUES table")
    return module.TECHNIQUES


def skill_answer(task: dict, techniques: dict) -> str:
    params = task["params"]
    if task["kind"] == "kv":
        if "csv_row" in params:
            return techniques["csv_lookup"](task["input"], params["csv_row"],
                                            params["csv_col"])
        return techniques["ini_lookup"](task["input"], params["key"], **params)
    fn = techniques[params["how"]]
    if params["how"] == "whole_word_count":
        return fn(task["input"], params["word"])
    return fn(task["input"])


# ---------------------------------------------------------------------------
# shared CSV helper (all three arms need it; none of them gets it wrong)
# ---------------------------------------------------------------------------

def _csv_lookup(text: str, row_key: str, col: str) -> str:
    rows = [ln for ln in text.splitlines() if ln.strip()]
    header = [c.strip() for c in rows[0].split(",")]
    want = header.index(col)
    for row in rows[1:]:
        cells = row.split(",")
        if cells and cells[0].strip() == row_key:
            return cells[want].strip()
    return ""
