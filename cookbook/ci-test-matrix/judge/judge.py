#!/usr/bin/env python3
"""Judge for the ci-test-matrix demo.

Usage: judge/judge.py <artifact-dir> [--seed N] [--json out.json]
                      [--toggle on|off|both]

<artifact-dir> holds the two graded files (see SPEC.md):
  matrix.yaml     python_versions, fixture, toggle, junit_dir
  run_matrix.py   the runner under test

Gates:

  parse     matrix.yaml is valid YAML with the four required keys and
            python_versions == ["3.9", "3.10", "3.11", "3.12", "3.13"]
  coverage  the runner produced one non-empty JUnit XML per cell (5 files)
  identity  every cell's JUnit XML records a distinct interpreter version
            (a <properties> stamp or the hostname attribute) that matches
            python_versions -- no two cells share an interpreter
  detection with the toggle ON, exactly the 3.9 cell fails; with it OFF,
            no cell fails
  counts    every cell's JUnit XML reports the same test count
  table     the runner writes an aggregated matrix table, and its rows
            agree with the JUnit XML it collected (a table that says
            all-pass while a cell failed is masking the failure)
  mask      the aggregated table's pass/fail pattern equals the expected
            mask (fail only at 3.9 with the toggle on)
  exit_code run_matrix.py exits 0 when all cells pass and non-zero when
            one fails -- a runner that always exits 0 is masking a failure

Why the verdict is not just "it ran": the expectation comes from the Python
language specification (``match`` becomes a keyword in 3.10, so the
fixture's match-statement module is a SyntaxError on 3.9), so a runner that
skips a cell, reuses one interpreter or masks a failure fails a gate.

The judge copies the artifact into a temp dir and runs the copy, so the
artifact under test never touches the judge tree.  Every numeric result is
deterministic: --seed is accepted for interface parity with the other
cookbook judges and does not change the verdict.

Exits 0 only if every gate passes.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

EXPECTED_VERSIONS = ["3.9", "3.10", "3.11", "3.12", "3.13"]
MATCH_LANGUAGE_VERSION = (3, 10)   # `match` is a keyword from Python 3.10
RUNNER_TIMEOUT = 1800
REQUIRED_KEYS = ("python_versions", "fixture", "toggle", "junit_dir")
GATE_ORDER = ("parse", "coverage", "identity", "detection", "counts",
              "table", "mask", "exit_code")

T0 = time.time()


def emit(gates, metrics, json_out):
    """Print the verdict JSON and exit 0 only if every gate passed."""
    ok = all(g["pass_"] for g in gates.values())
    out = dict(verdict="PASS" if ok else "FAIL",
               timing=dict(wall_s=round(time.time() - T0, 1)),
               gates={k: {"pass": gates[k]["pass_"],
                          "detail": gates[k]["detail"]} for k in GATE_ORDER
                      if k in gates},
               metrics=metrics)
    text = json.dumps(out, indent=2)
    if json_out:
        with open(json_out, "w") as f:
            f.write(text + "\n")
    print(text)
    sys.exit(0 if ok else 1)


def fail_all(gates, metrics, reason, json_out):
    """Close every gate that has not been decided yet, then emit."""
    for name in GATE_ORDER:
        if name not in gates:
            gates[name] = dict(pass_=False, detail=reason)
    emit(gates, metrics, json_out)


# ------------------------------------------------------------------ YAML
def read_yaml_keys(path):
    """Read the 'key: value' block a matrix.yaml opens with.

    Stops at the aggregated ``matrix:`` table a runner appends, so the table
    cannot redefine the graded keys.  Raises ValueError on any line it
    cannot read: a malformed artifact fails the parse gate loudly rather
    than half-parsing.
    """
    cfg = {}
    with open(path) as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line.strip().startswith("matrix:"):
                break
            key, sep, value = line.partition(":")
            if not sep:
                raise ValueError(f"line {lineno}: not a 'key: value' line: "
                                 f"{line.strip()!r}")
            cfg[key.strip()] = value.strip()
    return cfg


def parse_flow_list(value):
    """Parse a YAML inline flow sequence: ["3.9", "3.10", ...]."""
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        raise ValueError(f"not an inline [...] list: {value!r}")
    out = []
    for item in value[1:-1].split(","):
        item = item.strip()
        if not item:
            continue
        if len(item) >= 2 and item[0] == item[-1] and item[0] in "\"'":
            item = item[1:-1]
        out.append(item)
    return out


# ---------------------------------------------------------------- JUnit
def parse_junit(path):
    """Parse one cell's JUnit XML.

    Returns dict with the test count, failures+errors and the interpreter
    stamp: a ``<properties><property name="python">`` value if the runner
    wrote one, else pytest's ``hostname`` attribute.
    """
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise ValueError(f"{os.path.basename(path)}: no <testsuite> element")
    stamp = None
    props = suite.find("properties")
    if props is not None:
        for p in props.findall("property"):
            if p.get("name") in ("python", "python_version"):
                stamp = p.get("value")
    if stamp is None:
        stamp = suite.get("hostname")
    return dict(tests=int(suite.get("tests", "0")),
                bad=int(suite.get("failures", "0")) + int(suite.get("errors", "0")),
                stamp=stamp, name=suite.get("name"))


def major_minor(stamp):
    """'3.9.25' -> (3, 9); None when *stamp* is not a version string."""
    if not isinstance(stamp, str):
        return None
    parts = stamp.strip().split(".")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


# ------------------------------------------------------------------ run
def read_matrix_table(path):
    """Read the aggregated matrix table the runner wrote, if any.

    The runner may append a ``matrix:`` mapping to matrix.yaml or write a
    sibling ``matrix-result.yaml``; both are accepted (SPEC.md).  A row may
    be a bare status (``"3.9": fail``) or a mapping
    (``"3.9": {status: fail, tests: 7}``); both are read.

    Returns {version: {"status": str, "tests": int-or-None}} and {} when no
    table is found.
    """
    table = {}
    for cand in (path, os.path.splitext(path)[0] + "-result.yaml"):
        if not os.path.exists(cand):
            continue
        seen_table = False
        with open(cand) as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                if line.strip().startswith("matrix:"):
                    seen_table = True
                    continue
                if not seen_table:
                    continue
                m = re.match(r'^\s*"?([0-9.]+)"?\s*:\s*(.+?)\s*$', line)
                if not m:
                    continue
                version, value = m.group(1), m.group(2)
                if value.startswith("{"):
                    status = re.search(r'status\s*:\s*([A-Za-z]+)', value)
                    tests = re.search(r'tests\s*:\s*(-?\d+)', value)
                    table[version] = dict(
                        status=status.group(1).lower() if status else None,
                        tests=int(tests.group(1)) if tests else None)
                else:
                    table[version] = dict(
                        status=value.strip().strip("\"'").lower(), tests=None)
        if table:
            return table
    return {}


def run_runner(runner_path, workdir, cfg, toggle_on, log, timeout=RUNNER_TIMEOUT):
    """Run the artifact's runner; return its exit code.

    The declared toggle is *removed* from the child environment first: the
    runner is what is under test, so the fixture may only see the toggle if
    the runner itself sets the variable matrix.yaml names.  A runner that
    ignores the declared name therefore leaves the fixture with every cell
    passing, which the detection gate catches.
    """
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    toggle = cfg.get("toggle")
    if toggle:
        # The declared variable is removed from the child environment and the
        # state is passed instead on the command line as ``--toggle on|off``.
        # Only a runner that reads matrix.yaml and honours that flag reaches
        # both states; one that merely forwards the ambient environment (or
        # sets a different variable) leaves the fixture with the toggle
        # unset, which the detection gate catches.
        env.pop(toggle, None)
    cmd = [sys.executable, runner_path, "--toggle", "on" if toggle_on else "off"]
    try:
        r = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"the runner did not finish within {timeout}s")
    log.write(f"$ {' '.join(cmd)}\n\n--- rc={r.returncode} ---\n{r.stdout}\n"
              f"{r.stderr}\n\n")
    log.flush()
    return r.returncode, r.stdout + r.stderr


def read_cells(junit_dir, versions):
    """Read each cell's JUnit XML: {version: row-or-None}."""
    rows = {}
    for v in versions:
        path = os.path.join(junit_dir, f"cell-{v}.xml")
        if not os.path.exists(path):
            rows[v] = None
            continue
        try:
            rows[v] = parse_junit(path)
        except Exception:                                          # noqa: BLE001
            rows[v] = None
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact", help="directory with matrix.yaml + run_matrix.py")
    ap.add_argument("--seed", type=int, default=42,
                    help="determinism seed (interface parity; unused)")
    ap.add_argument("--json", help="also write the verdict JSON to this file")
    ap.add_argument("--toggle", choices=("on", "off", "both"), default="both",
                    help="which toggle state(s) to grade (default: both)")
    args = ap.parse_args()

    adir = args.artifact
    gates, metrics = {}, {}

    # ---- G1 parse -------------------------------------------------------
    try:
        cfg = read_yaml_keys(os.path.join(adir, "matrix.yaml"))
        missing = [k for k in REQUIRED_KEYS if k not in cfg]
        if missing:
            raise ValueError("matrix.yaml is missing: " + ", ".join(missing))
        versions = parse_flow_list(cfg["python_versions"])
    except (OSError, ValueError) as exc:
        gates["parse"] = dict(pass_=False,
                              detail=f"matrix.yaml unreadable or invalid: {exc}")
        fail_all(gates, metrics, "no valid matrix.yaml; no gate can run",
                 args.json)

    runner_path = os.path.join(adir, "run_matrix.py")
    if not os.path.exists(runner_path):
        gates["parse"] = dict(pass_=False,
                             detail="parse gate ok, but run_matrix.py is missing")
        fail_all(gates, metrics, "run_matrix.py not found", args.json)

    dupes = sorted({v for v in versions if versions.count(v) > 1})
    if dupes:
        gates["parse"] = dict(pass_=False,
                             detail=f"python_versions has duplicates: "
                                    f"{', '.join(dupes)}")
    elif versions != EXPECTED_VERSIONS:
        gates["parse"] = dict(pass_=False,
                             detail=f"python_versions must be exactly "
                                    f"{EXPECTED_VERSIONS}, got {versions}")
    else:
        gates["parse"] = dict(pass_=True,
                             detail=f"matrix.yaml has {list(REQUIRED_KEYS)} and "
                                    f"python_versions == {versions} "
                                    f"(5 cells, no duplicates)")
    metrics["versions"] = versions
    if not gates["parse"]["pass_"]:
        fail_all(gates, metrics, "matrix.yaml failed the parse gate", args.json)

    # ---- grade on a *copy* of the artifact -------------------------------
    work = tempfile.mkdtemp(prefix="matrix-judge-")
    art = os.path.join(work, "artifact")
    shutil.copytree(adir, art)
    art_runner = os.path.join(art, "run_matrix.py")
    junit_dir = os.path.join(art, cfg["junit_dir"])
    # Put the judge's pinned, hash-checked wheel pins where the runner finds
    # them (its own ../judge/requirements.txt lookup), and never in a place
    # the artifact under test can edit.
    os.makedirs(os.path.join(work, "judge"), exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    shutil.copy(os.path.join(here, "requirements.txt"),
                os.path.join(work, "judge", "requirements.txt"))
    log = open(os.path.join(work, "runner.log"), "w")

    if not shutil.which("uv"):
        fail_all(gates, metrics, "uv not found on PATH; run judge/setup.sh first",
                 args.json)

    states = [("on", True), ("off", False)] if args.toggle == "both" \
        else [("on", True)] if args.toggle == "on" else [("off", False)]

    runs = {}
    try:
        for label, toggle_on in states:
            shutil.rmtree(junit_dir, ignore_errors=True)   # no stale cells
            rc, out = run_runner(art_runner, art, cfg, toggle_on, log)
            runs[label] = dict(rc=rc, out=out,
                               cells=read_cells(junit_dir, versions),
                               table=read_matrix_table(os.path.join(
                                   art, "matrix.yaml")))
    except RuntimeError as exc:
        fail_all(gates, metrics, str(exc), args.json)
    finally:
        log.close()

    # ---- G2 coverage -----------------------------------------------------
    cov_bits, ok = [], True
    for label, r in runs.items():
        for v in versions:
            if r["cells"][v] is None:
                ok = False
                cov_bits.append(f"toggle {label}: no JUnit XML for python {v}")
            elif r["cells"][v]["tests"] == 0:
                ok = False
                cov_bits.append(f"toggle {label}: cell-{v}.xml records 0 tests")
    on_counts = {v: runs["on"]["cells"][v]["tests"]
                 for v in versions
                 if "on" in runs and runs["on"]["cells"][v] is not None}
    gates["coverage"] = dict(
        pass_=ok,
        detail=("one non-empty JUnit XML per cell: "
                + ", ".join(f"cell-{v}.xml={on_counts.get(v)} tests"
                            for v in versions)) if ok
        else ("; ".join(cov_bits) or "no JUnit XML produced"))
    metrics["junit_files_per_state"] = {
        label: sum(1 for v in versions if r["cells"][v] is not None)
        for label, r in runs.items()}

    # ---- G3 interpreter identity -----------------------------------------
    ident_bits, ok = [], True
    for label, r in runs.items():
        stamps = {v: r["cells"][v]["stamp"] for v in versions
                  if r["cells"][v] is not None}
        if len(stamps) != len(versions):
            ok = False
            ident_bits.append(f"toggle {label}: "
                              f"{len(versions) - len(stamps)} cells have no "
                              "interpreter stamp")
            continue
        for v, stamp in stamps.items():
            mm = major_minor(stamp)
            if mm is None:
                ok = False
                ident_bits.append(f"toggle {label}: cell {v} stamp {stamp!r} "
                                  "is not a version string")
                continue
            want = tuple(int(x) for x in v.split("."))
            if mm != want:
                ok = False
                ident_bits.append(f"toggle {label}: cell {v} ran under "
                                  f"{stamp}, not {v}")
        shared = {}
        for v, stamp in stamps.items():
            mm = major_minor(stamp)
            if mm is not None:
                shared.setdefault(mm, []).append(v)
        for mm, vs in shared.items():
            if len(vs) > 1:
                ok = False
                ident_bits.append(
                    f"toggle {label}: cells {', '.join(sorted(vs))} share "
                    f"interpreter .{'.'.join(str(x) for x in mm)}")
    on_stamps = {v: runs["on"]["cells"][v]["stamp"] for v in versions
                 if "on" in runs and runs["on"]["cells"][v] is not None}
    gates["identity"] = dict(
        pass_=ok,
        detail=("each cell ran under its own interpreter: "
                + ", ".join(f"{v}={on_stamps.get(v)}" for v in versions)) if ok
        else ("; ".join(ident_bits) or "no interpreter stamps found"))

    # ---- G5 equal test counts ---------------------------------------------
    count_bits, ok = [], True
    for label, r in runs.items():
        counts = {v: r["cells"][v]["tests"] for v in versions
                  if r["cells"][v] is not None}
        distinct = sorted(set(counts.values()))
        if len(distinct) > 1:
            ok = False
            count_bits.append(f"toggle {label}: test counts differ "
                              + ", ".join(f"{v}={counts[v]}" for v in versions))
    on_tests = on_counts.get(versions[0]) if on_counts else None
    gates["counts"] = dict(
        pass_=ok,
        detail=(f"all {len(versions)} cells report the same test count "
                f"({on_tests} tests per cell)" if on_tests is not None
                else f"all cells report the same test count ({on_counts})")
        if ok else ("; ".join(count_bits) or "no counts"))
    if on_counts:
        metrics["tests_per_cell"] = on_tests

    # ---- G4 failure detection ---------------------------------------------
    det_bits, ok = [], True
    for label in ("on", "off"):
        if label not in runs:
            continue
        cells = runs[label]["cells"]
        failed = [v for v in versions if cells[v] is not None
                  and cells[v]["bad"] > 0]
        missing = [v for v in versions if cells[v] is None]
        if missing:
            ok = False
            det_bits.append(f"toggle {label}: no JUnit XML for "
                            + ", ".join(missing))
            continue
        if label == "on":
            if failed != ["3.9"]:
                ok = False
                det_bits.append(
                    f"toggle on: exactly the 3.9 cell must fail; failing cells "
                    f"were {failed or 'none'}")
            else:
                passed = [v for v in versions if v != "3.9"]
                det_bits.append(
                    f"toggle on: exactly the 3.9 cell fails, "
                    + ", ".join(passed)
                    + " pass (the fixture's match-statement module is a "
                      "SyntaxError below Python 3.10)")
        else:
            if failed:
                ok = False
                det_bits.append(f"toggle off: no cell may fail; failing cells "
                                f"were {failed}")
            else:
                det_bits.append("toggle off: all five cells pass")
    gates["detection"] = dict(pass_=ok,
                             detail="; ".join(det_bits) or "no state graded")

    # ---- table: the aggregated table must agree with the JUnit XML -------
    table_bits, ok = [], True
    aggregated = {}
    for label, r in runs.items():
        claimed = r["table"]
        if not claimed:
            ok = False
            table_bits.append(f"toggle {label}: no aggregated matrix table "
                              "was written (matrix.yaml has no matrix: mapping)")
            continue
        aggregated[label] = claimed
        cells = r["cells"]
        for v in versions:
            row = claimed.get(v)
            if row is None or row.get("status") is None:
                ok = False
                table_bits.append(f"toggle {label}: the aggregated table has "
                                  f"no status for python {v}")
                continue
            if cells[v] is None:
                continue
            want = "pass" if cells[v]["bad"] == 0 else "fail"
            if row["status"] != want:
                ok = False
                table_bits.append(
                    f"toggle {label}: the table says {v}={row['status']} but "
                    f"cell-{v}.xml says {want}")
            if row.get("tests") is not None and \
                    row["tests"] != cells[v]["tests"]:
                ok = False
                table_bits.append(
                    f"toggle {label}: the table says {v} ran {row['tests']} "
                    f"tests but cell-{v}.xml records {cells[v]['tests']}")
    gates["table"] = dict(
        pass_=ok,
        detail=("the aggregated table matches the collected JUnit XML on "
                "every cell (status and test count)") if ok
        else ("; ".join(table_bits) or "no state graded"))
    metrics["aggregated_table"] = aggregated

    # ---- G6 mask ----------------------------------------------------------
    expected_on = {v: (v != "3.9") for v in versions}
    expected_off = {v: True for v in versions}
    mask_bits, ok = [], True
    for label, expected in (("on", expected_on), ("off", expected_off)):
        if label not in runs:
            continue
        cells = runs[label]["cells"]
        for v in versions:
            got = cells[v] is not None and cells[v]["bad"] == 0
            if got != expected[v]:
                ok = False
                mask_bits.append(f"toggle {label}: cell {v} = "
                                 f"{'pass' if got else 'fail'}, expected "
                                 f"{'pass' if expected[v] else 'fail'}")
    gates["mask"] = dict(
        pass_=ok,
        detail=("the pass/fail pattern matches the expected mask: on -> "
                "[pass, pass, pass, pass, fail] (the 3.9 SyntaxError), "
                "off -> [pass, pass, pass, pass, pass]") if ok
        else ("; ".join(mask_bits) or "no state graded"))
    metrics["mask_on"] = ["pass" if (runs["on"]["cells"][v] is not None
                                     and runs["on"]["cells"][v]["bad"] == 0)
                          else "fail" for v in versions] if "on" in runs else None
    metrics["mask_off"] = ["pass" if (runs["off"]["cells"][v] is not None
                                      and runs["off"]["cells"][v]["bad"] == 0)
                           else "fail" for v in versions] if "off" in runs \
        else None

    # ---- G7 exit code -----------------------------------------------------
    exit_bits, ok = [], True
    for label, expect_zero in (("off", True), ("on", False)):
        if label not in runs:
            continue
        rc = runs[label]["rc"]
        if expect_zero and rc != 0:
            ok = False
            exit_bits.append(f"toggle off (all cells pass): run_matrix.py "
                             f"exited {rc}, expected 0")
        if not expect_zero and rc == 0:
            ok = False
            exit_bits.append(f"toggle on (the 3.9 cell fails): run_matrix.py "
                             "exited 0 -- a runner that always exits 0 is "
                             "masking the failure")
    gates["exit_code"] = dict(
        pass_=ok,
        detail=("run_matrix.py exits 0 when all cells pass and non-zero when "
                "one fails (a runner that always exits 0 cannot pass this "
                "gate)") if ok else "; ".join(exit_bits))
    metrics["exit_codes"] = {label: runs[label]["rc"] for label in runs}
    metrics["cells"] = {
        v: dict(tests=on_counts.get(v), stamp=on_stamps.get(v),
                failed=("on" in runs and runs["on"]["cells"][v] is not None
                        and runs["on"]["cells"][v]["bad"] > 0))
        for v in versions}

    shutil.rmtree(work, ignore_errors=True)
    emit(gates, metrics, args.json)


if __name__ == "__main__":
    main()
