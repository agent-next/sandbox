"""demo fixture: a small pinned library with tests (ci-test-matrix demo).

This is the fixture under test.  It is intentionally small and pinned so the
demo's five interpreter cells (CPython 3.9-3.13, one uv-managed interpreter
each) run in seconds.  The library is pure stdlib and has no dependencies.
"""

__all__ = ["add", "greet", "parse_scalar_entry"]

__version__ = "1.0.0"
