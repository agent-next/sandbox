"""demolib — the small pinned fixture library this demo tests.

Pure standard library, no dependencies, hand-written for this demo so the
five interpreter cells run in seconds and the expected test count (6) and
failure behaviour are known exactly:

  * 5 tests pass on every CPython from 3.9 to 3.13;
  * ``test_match_syntax_module`` (below) imports
    ``demolib.matchsyntax`` and is *skipped* unless the toggle is on.
    That module uses a ``match`` statement, which is a SyntaxError on
    CPython 3.9 -- ``match`` is a keyword only from 3.10.  So with the
    toggle on, exactly the 3.9 cell fails, on every other version it passes.
"""

__all__ = ["add", "greet", "parse_scalar_entry"]

__version__ = "1.0.0"


def add(a, b):
    """Return the sum of two numbers."""
    return a + b


def greet(name):
    """Return a greeting for *name*."""
    return f"hello, {name}"


def parse_scalar_entry(text):
    """Parse a solver dictionary scalar entry.

    ``nu 0.01;`` -> 0.01; the dimensioned form
    ``nu [0 2 -1 0 0 0 0] 0.01;`` -> 0.01; anything without the trailing
    ``;`` raises ValueError.
    """
    text = text.strip()
    if not text.endswith(";"):
        raise ValueError("missing ';'")
    body = text[:-1].strip()
    head, _, rest = body.partition(" ")
    if head == "nu":
        # the value is the last whitespace-separated token, so the
        # dimensioned form is accepted as well
        return float(rest.split()[-1])
    return body
