"""The fixture's test suite: 6 tests, identical on every interpreter.

Five always pass (they are pure stdlib).  The sixth imports the 3.10+ only
module and is skipped unless the toggle is on, so the per-cell test count
stays 6 whichever way the toggle is set.
"""

import os

import pytest

from demolib import add, greet, parse_scalar_entry

TOGGLE_ON = os.environ.get("DEMOLIB_MATCH", "").strip().lower() in ("1", "true", "yes", "on")


def test_add_ints():
    assert add(2, 3) == 5


def test_add_floats():
    assert abs(add(0.1, 0.2) - 0.3) < 1e-12


def test_greet():
    assert greet("ada") == "hello, ada"


def test_parse_scalar():
    assert parse_scalar_entry("nu 0.01;") == 0.01


def test_parse_dimensioned():
    assert parse_scalar_entry("nu [0 2 -1 0 0 0 0] 1.5e-5;") == 1.5e-5


def test_parse_missing_semicolon():
    with pytest.raises(ValueError):
        parse_scalar_entry("nu 0.01")


@pytest.mark.skipif(not TOGGLE_ON,
                    reason="version-specific-failure toggle off")
def test_match_syntax_module():
    from demolib import matchsyntax            # SyntaxError on CPython < 3.10

    assert matchsyntax.classify(0) == "zero"
    assert matchsyntax.classify(7) == "positive"
    assert matchsyntax.classify("x") == "other"
