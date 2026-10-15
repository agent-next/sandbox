#!/usr/bin/env python3
"""Generate known-bad artifacts as single-edit mutants of examples/good.

Usage: mutants.py <out_dir>

Each mutant is one edit away from the known-good artifact, so the judge
self-test proves the judge can fail: a runner that silently skips a cell,
reuses one interpreter, or masks a failure must not pass.

The five mutants SPEC.md names:
  cell-skipped    3.9 removed from python_versions
  same-interpreter every cell stamped 3.12
  failure-masked   runner exits 0 despite a failing cell (bad table, no trace)
  junit-missing   no JUnit XML written for one cell
  wrong-count     the aggregated table reports 6 tests instead of 7

...plus four more that each break a different gate:
  no-versions-key matrix.yaml missing python_versions
  toggle-swapped  the toggle drives a different env var than it declares
  shared-mask     the aggregated table claims all-pass while a cell failed
  no-runner      run_matrix.py deleted
"""

import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = os.path.join(HERE, "..", "examples", "good")
MATRIX = os.path.join(GOOD, "matrix.yaml")
RUNNER = os.path.join(GOOD, "run_matrix.py")

# the names SPEC.md lists first, in order
SPEC_MUTANTS = ("cell-skipped", "same-interpreter", "failure-masked",
                "junit-missing", "wrong-count")


def load():
    with open(MATRIX) as f:
        matrix = f.read()
    with open(RUNNER) as f:
        runner = f.read()
    with open(os.path.join(GOOD, "fixture", "conftest.py")) as f:
        conftest = f.read()
    return matrix, runner, conftest


def emit(outdir, name, matrix=None, runner=None, conftest=None,
         drop_runner=False):
    """Write one mutant directory (good fixture + the mutated files)."""
    d = os.path.join(outdir, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    shutil.copytree(GOOD, d)
    if matrix is not None:
        with open(os.path.join(d, "matrix.yaml"), "w") as f:
            f.write(matrix)
    if runner is not None:
        with open(os.path.join(d, "run_matrix.py"), "w") as f:
            f.write(runner)
    if conftest is not None:
        with open(os.path.join(d, "fixture", "conftest.py"), "w") as f:
            f.write(conftest)
    if drop_runner:
        os.remove(os.path.join(d, "run_matrix.py"))
    for junk in ("junit", "matrix-result.yaml"):
        p = os.path.join(d, junk)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)
    return name


# ------------------------------------------------------------------ edits
def m_cell_skipped(outdir, matrix, runner, conftest):
    """G1: drop the 3.9 cell, so the runner that fails on 3.9 looks healthy."""
    return emit(outdir, "cell-skipped",
                matrix=matrix.replace('"3.9", ', ""))


def m_same_interpreter(outdir, matrix, runner, conftest):
    """G3: every cell stamped 3.12 — one interpreter for all five."""
    # the stamp the fixture's conftest records into each cell's JUnit XML
    patched = conftest.replace(
        'record_testsuite_property("python", platform.python_version())',
        'record_testsuite_property("python", "3.12.14")')
    if patched == conftest:
        raise RuntimeError("same-interpreter patch did not apply")
    return emit(outdir, "same-interpreter", conftest=patched)


def m_failure_masked(outdir, matrix, runner, conftest):
    """G7+G6: swallow the failing cell and always exit 0."""
    patched = runner.replace(
        '''    failed = [row["version"] for row in table if row["status"] != "pass"]
    if failed:
        print(f"failing cells: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("all cells pass")
    return 0''',
        '''    # BAD: a failing cell is downgraded to a pass and the exit code is 0
    for row in table:
        if row["status"] != "pass":
            row["status"] = "pass"
    print("all cells pass")
    return 0''')
    if patched == runner:
        raise RuntimeError("failure-masked patch did not apply")
    return emit(outdir, "failure-masked", runner=patched)


def m_junit_missing(outdir, matrix, runner, conftest):
    """G2: the 3.12 cell's JUnit XML never reaches the junit_dir."""
    patched = runner.replace(
        '''        junit = os.path.join(cfg["junit_dir"], JUNIT_NAME.format(version=version))
        os.makedirs(cfg["junit_dir"], exist_ok=True)''',
        '''        junit = os.path.join(cell, JUNIT_NAME.format(version=version))
        # BAD: written next to the cell instead of junit_dir, so the
        # aggregated table for the 3.12 cell is missing
        if version == "3.12":
            os.makedirs(cell, exist_ok=True)''')
    if patched == runner:
        raise RuntimeError("junit-missing patch did not apply")
    return emit(outdir, "junit-missing", runner=patched)


def m_wrong_count(outdir, matrix, runner, conftest):
    """G5: the aggregated count is off from what the cells actually ran."""
    patched = runner.replace(
        '''    table = []
    for r in results:
        try:
            tests, bad, version = parse_junit(r["junit"])
        except Exception as exc:                      # noqa: BLE001 - report
            tests, bad, version = -1, -1, f"unreadable: {exc}"''',
        '''    table = []
    for r in results:
        try:
            tests, bad, version = parse_junit(r["junit"])
        except Exception as exc:                      # noqa: BLE001 - report
            tests, bad, version = -1, -1, f"unreadable: {exc}"
        # BAD: drop the skipped test from the aggregated count
        tests = tests - 1''')
    if patched == runner:
        raise RuntimeError("wrong-count patch did not apply")
    return emit(outdir, "wrong-count", runner=patched)


def m_no_versions_key(outdir, matrix, runner, conftest):
    """G1: matrix.yaml no longer declares the cells at all."""
    return emit(outdir, "no-versions-key",
                matrix=re.sub(r'^python_versions:.*\n', '', matrix,
                              flags=re.MULTILINE))


def m_toggle_swapped(outdir, matrix, runner, conftest):
    """G4: the runner reads a different env var than matrix.yaml declares,
    so the judge's toggle never reaches the fixture."""
    patched = runner.replace(
        '            env[cfg["toggle"]] = "1"',
        '            env["DEMOLIB_MATCH_TOGGLE"] = "1"').replace(
        '            env.pop(cfg["toggle"], None)',
        '            env.pop("DEMOLIB_MATCH_TOGGLE", None)')
    if patched == runner:
        raise RuntimeError("toggle-swapped patch did not apply")
    return emit(outdir, "toggle-swapped", runner=patched)


def m_shared_mask(outdir, matrix, runner, conftest):
    """G6+G7: the aggregated table claims every cell passed."""
    patched = runner.replace(
        '''    for row in table:
        out.append(f"  \\"{row['version']}\\": {{status: {row['status']}, "
                   f"tests: {row['tests']}}}\\n")''',
        '''    for row in table:
        # BAD: report every cell as a pass whatever the JUnit XML said
        out.append(f"  \\"{row['version']}\\": {{status: pass, "
                   f"tests: {row['tests']}}}\\n")''')
    if patched == runner:
        raise RuntimeError("shared-mask patch did not apply")
    return emit(outdir, "shared-mask", runner=patched)


def m_no_runner(outdir, matrix, runner, conftest):
    """G1: the graded runner is not in the artifact at all."""
    return emit(outdir, "no-runner", drop_runner=True)


MUTANTS = [m_cell_skipped, m_same_interpreter, m_failure_masked,
           m_junit_missing, m_wrong_count, m_no_versions_key,
           m_toggle_swapped, m_shared_mask, m_no_runner]


def main():
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    matrix, runner, conftest = load()
    made = []
    for fn in MUTANTS:
        made.append(fn(outdir, matrix, runner, conftest))
    print("\n".join(made))


if __name__ == "__main__":
    main()
