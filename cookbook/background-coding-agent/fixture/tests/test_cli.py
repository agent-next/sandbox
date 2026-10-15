"""Tests for the command-line interface and the table output."""

import pytest

from measurectl.cli import build_parser, format_number, main, ordered
from measurectl.stats import summarise

SAMPLE = """\
metric,value
alpha,1.0
beta,42
gamma,-2.5
alpha,2.5
"""


def write(tmp_path, text):
    path = tmp_path / "input.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_table_lists_metrics_sorted_by_name(tmp_path, capsys):
    path = write(tmp_path, SAMPLE)
    assert main([path]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["metric", "count", "mean", "min", "max"]
    assert [line.split()[0] for line in lines[2:]] == ["alpha", "beta", "gamma"]


def test_table_reports_the_mean(tmp_path, capsys):
    path = write(tmp_path, SAMPLE)
    main([path])
    out = capsys.readouterr().out
    assert "1.75" in out  # (1.0 + 2.5) / 2


def test_sort_by_count_is_descending(tmp_path, capsys):
    path = write(tmp_path, SAMPLE)
    main([path, "--sort", "count"])
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines[2:]] == ["alpha", "beta", "gamma"]


def test_missing_file_exits_two_with_stderr(tmp_path, capsys):
    assert main([str(tmp_path / "nope.csv")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "measurectl:" in captured.err


def test_malformed_row_exits_two(tmp_path, capsys):
    path = write(tmp_path, "alpha,1\nbeta,fast\n")
    assert main([path]) == 2
    assert capsys.readouterr().out == ""


def test_empty_file_exits_two(tmp_path, capsys):
    path = write(tmp_path, "# nothing here\n")
    assert main([path]) == 2
    assert "no data rows" in capsys.readouterr().err


def test_format_number_trims_trailing_zeros():
    assert format_number(2.0) == "2"
    assert format_number(2.5) == "2.5"
    assert format_number(1 / 3) == "0.333333"
    assert format_number(-0.0) == "0"


def test_sort_rejects_unknown_key():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["x.csv", "--sort", "mean"])


def test_ordered_breaks_count_ties_by_name():
    metrics = summarise([("beta", 1.0), ("alpha", 1.0), ("gamma", 1.0)])
    assert [m.name for m in ordered(metrics, "count")] == \
        ["alpha", "beta", "gamma"]
