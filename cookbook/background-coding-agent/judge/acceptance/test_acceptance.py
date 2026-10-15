"""Hidden acceptance suite for the `--json` feature (judge-owned).

Copied into the patched checkout by `judge/grade.sh` and run there.  It
grades the contract in `fixture/ISSUE.md`:

  * the document's schema, key sets and types;
  * sorting, integer counts and the min/mean/max/sum identities;
  * `--json` replacing the table and ignoring `--sort`;
  * unchanged error handling (exit 2, nothing on stdout);
  * exact values on small inputs whose statistics are computed by hand.

Values here are computed analytically in the test, so a patch that
hardcodes the sample answers or rounds its output fails.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCHEMA = "measurectl/summary/v1"
TOP_KEYS = {"schema", "total_count", "metrics"}
METRIC_KEYS = {"name", "count", "sum", "mean", "min", "max"}

# The checkout the judge is grading; grade.sh sets this explicitly.
ROOT = Path(os.environ.get("MEASURECTL_CHECKOUT", Path(__file__).resolve().parents[1]))


def cli_env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_cli(*args, timeout=60):
    return subprocess.run(
        [sys.executable, "-m", "measurectl", *args],
        capture_output=True, text=True, timeout=timeout,
        cwd=str(ROOT), env=cli_env(),
    )


def run_json(tmp_path, text, *args):
    """Write ``text`` to a CSV and run ``--json`` on it."""
    path = tmp_path / "in.csv"
    path.write_text(text, encoding="utf-8")
    return run_cli("--json", str(path), *args)


def parse(tmp_path, text, *args):
    proc = run_json(tmp_path, text, *args)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def metric(doc, name):
    for entry in doc["metrics"]:
        if entry["name"] == name:
            return entry
    raise AssertionError(f"metric {name!r} missing from {doc['metrics']!r}")


def test_schema_string_is_the_documented_literal(tmp_path):
    assert parse(tmp_path, "alpha,1\n")["schema"] == SCHEMA


def test_top_level_keys_are_exactly_the_schema(tmp_path):
    doc = parse(tmp_path, "alpha,1\nbeta,2\n")
    assert set(doc) == TOP_KEYS


def test_metric_keys_are_exactly_the_schema(tmp_path):
    doc = parse(tmp_path, "alpha,1\n")
    assert set(doc["metrics"][0]) == METRIC_KEYS


def test_count_is_an_integer_not_a_float(tmp_path):
    entry = metric(parse(tmp_path, "alpha,1\nalpha,2\n"), "alpha")
    assert isinstance(entry["count"], int)
    assert not isinstance(entry["count"], bool)


def test_numeric_fields_are_json_numbers(tmp_path):
    entry = metric(parse(tmp_path, "alpha,1\nalpha,2\n"), "alpha")
    for key in ("sum", "mean", "min", "max"):
        assert isinstance(entry[key], (int, float)), (key, entry[key])


def test_total_count_counts_every_data_row(tmp_path):
    text = "# note\n\nalpha,1\nbeta,2\n\nalpha,3\n# tail\n"
    assert parse(tmp_path, text)["total_count"] == 3


def test_metrics_are_sorted_by_name(tmp_path):
    doc = parse(tmp_path, "gamma,1\nalpha,2\nbeta,3\n")
    names = [entry["name"] for entry in doc["metrics"]]
    assert names == sorted(names)


def test_values_match_hand_computed_statistics(tmp_path):
    entry = metric(parse(tmp_path, "alpha,1\nalpha,2.5\nalpha,3\n"), "alpha")
    assert entry["count"] == 3
    assert entry["sum"] == 6.5
    assert entry["mean"] == 6.5 / 3
    assert entry["min"] == 1.0
    assert entry["max"] == 3.0


def test_negative_and_exponent_values(tmp_path):
    entry = metric(parse(tmp_path, "alpha,-2.5\nalpha,-1.5e3\n"), "alpha")
    assert entry["count"] == 2
    assert entry["sum"] == -1502.5
    assert entry["min"] == -1500.0
    assert entry["max"] == -2.5


def test_single_row_metric_has_equal_extremes(tmp_path):
    entry = metric(parse(tmp_path, "beta,7.5\n"), "beta")
    assert entry["count"] == 1
    assert entry["min"] == entry["max"] == entry["mean"] == 7.5


def test_min_leq_mean_leq_max(tmp_path):
    text = "".join(f"alpha,{v}\n" for v in (-4.0, 0.0, 1.0, 9.5))
    entry = metric(parse(tmp_path, text), "alpha")
    assert entry["min"] <= entry["mean"] <= entry["max"]


def test_mean_equals_sum_over_count(tmp_path):
    text = "".join(f"alpha,{v}\n" for v in (0.1, 0.2, 0.3, 0.7, 1.1))
    entry = metric(parse(tmp_path, text), "alpha")
    assert abs(entry["mean"] - entry["sum"] / entry["count"]) < 1e-12


def test_json_ignores_sort_flag(tmp_path):
    text = "beta,2\nalpha,1\ngamma,3\n"
    assert run_json(tmp_path, text).stdout == \
        run_json(tmp_path, text, "--sort", "count").stdout


def test_json_stdout_is_only_the_document(tmp_path):
    proc = run_json(tmp_path, "alpha,1\nbeta,2\n")
    assert proc.returncode == 0
    assert proc.stdout.strip().startswith("{")
    json.loads(proc.stdout)  # nothing but JSON


def test_json_succeeds_on_a_many_metric_file(tmp_path):
    text = "".join(f"m{i:03d},{i}.5\n" for i in range(40))
    doc = parse(tmp_path, text)
    assert len(doc["metrics"]) == 40
    assert doc["total_count"] == 40


def test_metric_names_are_stripped(tmp_path):
    doc = parse(tmp_path, "  alpha ,1\n")
    assert [entry["name"] for entry in doc["metrics"]] == ["alpha"]


def test_sort_order_is_unicode_code_point_order(tmp_path):
    doc = parse(tmp_path, "Zeta,1\nalpha,1\nBeta,1\n")
    names = [entry["name"] for entry in doc["metrics"]]
    assert names == ["Beta", "Zeta", "alpha"]


def test_json_missing_file_exits_two_with_empty_stdout(tmp_path):
    proc = run_cli("--json", str(tmp_path / "nope.csv"))
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "measurectl:" in proc.stderr


def test_json_malformed_row_exits_two_with_empty_stdout(tmp_path):
    proc = run_json(tmp_path, "alpha,1\nbeta,fast\n")
    assert proc.returncode == 2
    assert proc.stdout == ""


def test_json_empty_file_exits_two(tmp_path):
    proc = run_json(tmp_path, "# nothing here\n")
    assert proc.returncode == 2
    assert proc.stdout == ""


def test_json_is_deterministic_across_runs(tmp_path):
    text = "alpha,1\nalpha,2.5\nbeta,-3\n"
    assert run_json(tmp_path, text).stdout == run_json(tmp_path, text).stdout


def test_table_output_is_unchanged_without_json(tmp_path):
    path = tmp_path / "in.csv"
    path.write_text("metric,value\nalpha,1\nalpha,2\n", encoding="utf-8")
    proc = run_cli(str(path))
    assert proc.returncode == 0
    assert proc.stdout.splitlines()[0].split() == \
        ["metric", "count", "mean", "min", "max"]


def test_sample_input_summarises_through_the_new_flag():
    proc = run_cli("--json", str(ROOT / "data" / "sample.csv"))
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["schema"] == SCHEMA
    assert metric(doc, "alpha")["count"] == 3
    assert metric(doc, "alpha")["sum"] == 6.5
    assert doc["total_count"] == 9
