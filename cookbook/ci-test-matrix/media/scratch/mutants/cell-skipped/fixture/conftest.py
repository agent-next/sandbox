"""pytest bootstrap for the fixture package.

* puts the fixture root on ``sys.path`` so ``import demolib`` works without
  installing anything;
* exposes the version-specific-failure toggle (``DEMOLIB_MATCH``);
* stamps every JUnit XML file with the interpreter that produced it, so the
  judge can check interpreter identity per cell.
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

TOGGLE_VALUES = ("1", "true", "yes", "on")
TOGGLE_NAME = "DEMOLIB_MATCH"


def toggle_enabled():
    """True when the version-specific-failure toggle is switched on."""
    return os.environ.get(TOGGLE_NAME, "").strip().lower() in TOGGLE_VALUES


@pytest.fixture(scope="session", autouse=True)
def _stamp_interpreter(record_testsuite_property):
    """Write the interpreter that ran this cell into the JUnit XML."""
    import platform

    record_testsuite_property("python", platform.python_version())
    record_testsuite_property("executable", sys.executable)
    record_testsuite_property("implementation", platform.python_implementation())
