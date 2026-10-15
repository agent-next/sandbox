"""Python 3.10+ only module (the version-specific failure).

``match`` becomes a keyword in Python 3.10 (PEP 634).  On CPython 3.9 and
below, parsing this module raises ``SyntaxError``, so a test that imports
it fails on exactly those interpreters.  Every other module in the fixture
is 3.9-compatible on purpose: the interpreter version is the only thing
that decides whether this cell passes.
"""


def classify(value):
    match value:                          # SyntaxError before Python 3.10
        case 0:
            return "zero"
        case int() as n if n > 0:
            return "positive"
        case _:
            return "other"
