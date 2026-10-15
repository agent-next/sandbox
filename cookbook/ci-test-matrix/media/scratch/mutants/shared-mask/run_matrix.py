#!/usr/bin/env python3
"""Matrix test runner for the ci-test-matrix demo.

Reads ``matrix.yaml``, runs the fixture suite once per listed CPython
version -- each cell under its own uv-managed interpreter -- collects one
JUnit XML file per cell, aggregates them into a pass/fail matrix table and
prints it.  Exits non-zero if any cell fails.

Standard library only; ``uv`` does the interpreter and pytest work (see
``judge/setup.sh`` for the pinned versions).

Usage:
    run_matrix.py [--matrix PATH] [--toggle on|off] [--jobs N]
"""
import argparse
import concurrent.futures
import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

MATRIX_FILE = "matrix.yaml"
JUNIT_NAME = "cell-{version}.xml"


# --------------------------------------------------------------------------
# matrix.yaml — a deliberately small reader/writer for this file's shape
# --------------------------------------------------------------------------
def parse_matrix(path):
    """Read matrix.yaml into a dict of the four required keys."""
    cfg = {}
    with open(path) as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, sep, value = line.partition(":")
            if not sep:
                raise ValueError(f"{path}:{lineno}: not a 'key: value' line: "
                                 f"{line.strip()!r}")
            cfg[key.strip()] = value.strip()
    return cfg


def parse_versions(value):
    """Parse a YAML inline flow sequence of quoted version strings."""
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        raise ValueError(f"python_versions must be a [...] list, got {value!r}")
    return [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]


def dump_matrix(cfg, table):
    """Serialise the definition plus the aggregated matrix table as YAML."""
    out = []
    out.append("# matrix.yaml — the matrix definition, aggregated by "
               "run_matrix.py.\n")
    out.append("python_versions: ["
               + ", ".join(f'"{v}"' for v in table_versions(table)) + "]\n")
    out.append(f"fixture: {cfg['fixture']}\n")
    out.append(f"toggle: {cfg['toggle']}\n")
    out.append(f"junit_dir: {cfg['junit_dir']}\n")
    out.append("\n# Aggregated matrix table: one row per cell, pass/fail per\n"
               "# interpreter, with the test count that cell reported.\n")
    out.append("matrix:\n")
    for row in table:
        # BAD: report every cell as a pass whatever the JUnit XML said
        out.append(f"  \"{row['version']}\": {{status: pass, "
                   f"tests: {row['tests']}}}\n")
    return "".join(out)


def table_versions(table):
    return [row["version"] for row in table]


# --------------------------------------------------------------------------
# cells
# --------------------------------------------------------------------------
def find_uv():
    uv = shutil.which("uv")
    if uv is None:
        sys.exit("uv not found on PATH; run judge/setup.sh first")
    return uv


def make_venv(uv, version, workdir):
    """Create a uv venv with interpreter *version* into *workdir*."""
    venv = os.path.join(workdir, f".venv-{version}")
    r = subprocess.run([uv, "venv", "--python", version, venv],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"uv venv --python {version} failed: "
                           f"{r.stderr.strip()[:400]}")
    return venv


def install_pytest(uv, venv, requirements):
    """Install the pinned, hash-checked pytest wheel set into *venv*."""
    r = subprocess.run([uv, "pip", "install", "--python",
                        os.path.join(venv, "bin", "python"),
                        "--require-hashes", "-r", requirements],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"uv pip install failed: {r.stderr.strip()[:400]}")
    return venv


def run_cell(uv, version, cfg, workdir, requirements, toggle_on, timeout=600):
    """Run one cell: its own interpreter, one JUnit XML file, parsed."""
    cell = os.path.join(workdir, f"cell-{version}")
    os.makedirs(cell, exist_ok=True)
    t0 = time.time()
    try:
        venv = make_venv(uv, version, cell)
        install_pytest(uv, venv, requirements)
        py = os.path.join(venv, "bin", "python")
        stamp = subprocess.run([py, "-c", "import platform;print(platform.python_version())"],
                               capture_output=True, text=True)
        if stamp.returncode != 0:
            raise RuntimeError(f"interpreter {py} would not start: "
                               f"{stamp.stderr.strip()[:300]}")
        interpreter_version = stamp.stdout.strip()
        junit = os.path.join(cfg["junit_dir"], JUNIT_NAME.format(version=version))
        os.makedirs(cfg["junit_dir"], exist_ok=True)

        env = dict(os.environ)
        if toggle_on:
            env[cfg["toggle"]] = "1"
        else:
            env.pop(cfg["toggle"], None)
        r = subprocess.run([py, "-m", "pytest", cfg["fixture"],
                            "-p", "no:cacheprovider", "-q",
                            "--junitxml", junit,
                            "-o", f"junit_suite_name=cell-{version}"],
                           cwd=os.getcwd(), env=env, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"cell {version} timed out after {timeout}s")
    return dict(version=version, rc=r.returncode, junit=junit,
                stdout=r.stdout.strip(), stderr=r.stderr.strip(),
                interpreter_version=interpreter_version,
                seconds=round(time.time() - t0, 2))


def parse_junit(path):
    """Parse one cell's JUnit XML into (test_count, failures+errors, version)."""
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise RuntimeError(f"{path}: no <testsuite> element")
    tests = int(suite.get("tests", "0"))
    bad = int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
    version = None
    props = suite.find("properties")
    if props is not None:
        for p in props.findall("property"):
            if p.get("name") == "python":
                version = p.get("value")
    if version is None:                      # fall back to the hostname stamp
        version = suite.get("hostname")
    return tests, bad, version


def default_requirements():
    """Find the pinned, hash-checked requirements file.

    The runner lives in ``examples/good`` but is run from a copy of the demo
    directory too, so look next to this file first, then walk up to the demo
    root, then fall back to the installed location.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (here, os.path.dirname(here), os.path.dirname(os.path.dirname(here))):
        cand = os.path.join(base, "judge", "requirements.txt")
        if os.path.exists(cand):
            return cand
    return os.path.join(here, "..", "..", "judge", "requirements.txt")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matrix", default=MATRIX_FILE, help="matrix.yaml to read")
    ap.add_argument("--toggle", choices=("on", "off"), default=None,
                    help="override the version-specific-failure toggle")
    ap.add_argument("--requirements", default=None,
                    help="pinned, hash-checked pytest wheels (default: the "
                         "judge's requirements.txt, found next to the demo)")
    ap.add_argument("--jobs", type=int, default=0,
                    help="cells in parallel (0 = auto, 1 = serial)")
    args = ap.parse_args()
    if args.requirements is None:
        args.requirements = default_requirements()
        if not os.path.exists(args.requirements):
            sys.exit(f"pinned requirements not found at {args.requirements}; "
                     "run judge/setup.sh, or pass --requirements")

    cfg = parse_matrix(args.matrix)
    for key in ("python_versions", "fixture", "toggle", "junit_dir"):
        if key not in cfg:
            sys.exit(f"{args.matrix}: missing required key {key!r}")
    versions = parse_versions(cfg["python_versions"])
    if len(set(versions)) != len(versions):
        sys.exit(f"{args.matrix}: duplicate python_versions: {versions}")

    # the toggle defaults to ON -- the demo's headline behaviour is the
    # version-specific failure -- so the judge drives the OFF state by
    # setting the declared variable to 0, and the ON state by setting it to 1.
    # A runner that ignores matrix.yaml and just passes the environment
    # through therefore gets exactly one of the two states right.
    env_toggle = os.environ.get(cfg["toggle"], "1")
    default_on = env_toggle.strip().lower() in ("1", "true", "yes", "on", "")
    toggle_on = default_on if args.toggle is None else args.toggle == "on"

    uv = find_uv()
    print(f"matrix: {args.matrix}  fixture: {cfg['fixture']}  "
          f"toggle {cfg['toggle']}={1 if toggle_on else 0}")
    print(f"cells: {', '.join(versions)}")

    workdir = tempfile.mkdtemp(prefix="matrix-cells-")
    jobs = args.jobs or min(len(versions), (os.cpu_count() or 1))
    jobs = max(1, min(jobs, len(versions)))
    try:
        t_all = time.time()
        results = []
        if jobs == 1:
            for v in versions:
                results.append(run_cell(uv, v, cfg, workdir,
                                        args.requirements, toggle_on))
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
                futs = {ex.submit(run_cell, uv, v, cfg, workdir,
                                  args.requirements, toggle_on): v
                        for v in versions}
                for fut in concurrent.futures.as_completed(futs):
                    results.append(fut.result())
        total = round(time.time() - t_all, 2)
        results.sort(key=lambda r: versions.index(r["version"]))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    table = []
    for r in results:
        try:
            tests, bad, version = parse_junit(r["junit"])
        except Exception as exc:                      # noqa: BLE001 - report
            tests, bad, version = -1, -1, f"unreadable: {exc}"
        table.append(dict(version=r["version"], tests=tests, bad=bad,
                          stamp=version, rc=r["rc"], result=r))

    col = max(len(v) for v in versions) + 2   # e.g. '3.13  '
    print(f"\n{'python':<7} {'version':<{col}} {'status':<7} {'tests':>5}  "
          f"{'failed':>6}  {'interpreter':<12} cell time")
    for row in table:
        status = "pass" if (row["bad"] == 0 and row["rc"] == 0) else "fail"
        row["status"] = status
        print(f"python {row['version']:<{col}} {status:<7} "
              f"{row['tests']:>5} {row['bad']:>6}  "
              f"{str(row['stamp']):<12} {row['result']['seconds']:>6.2f}s")
    print(f"\ntotal: {total:.2f}s across {len(table)} cells "
          f"({jobs} cell{'s' if jobs > 1 else ''} at a time)")

    # aggregate into matrix.yaml (sibling matrix-result.yaml is equivalent)
    with open(os.path.splitext(args.matrix)[0] + "-result.yaml", "w") as f:
        f.write(dump_matrix(cfg, table))
    print(f"matrix table written to "
          f"{os.path.splitext(args.matrix)[0]}-result.yaml")

    failed = [row["version"] for row in table if row["status"] != "pass"]
    if failed:
        print(f"failing cells: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("all cells pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
