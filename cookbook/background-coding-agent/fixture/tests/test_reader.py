"""Tests for the CSV reader."""

import pytest

from measurectl.reader import InputError, read_rows


def write(tmp_path, text):
    path = tmp_path / "input.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_reads_values_in_file_order(tmp_path):
    path = write(tmp_path, "alpha,1\nbeta,2.5\n")
    assert read_rows(path) == [("alpha", 1.0), ("beta", 2.5)]


def test_skips_blank_and_comment_lines(tmp_path):
    path = write(tmp_path, "# note\n\nalpha,1\n   \n# another\nbeta,2\n")
    assert read_rows(path) == [("alpha", 1.0), ("beta", 2.0)]


def test_skips_header_row(tmp_path):
    path = write(tmp_path, "metric,value\nalpha,1\n")
    assert read_rows(path) == [("alpha", 1.0)]


def test_keeps_numeric_first_row(tmp_path):
    # A first row whose second column is a number is data, not a header.
    path = write(tmp_path, "metric,3\n")
    assert read_rows(path) == [("metric", 3.0)]


def test_strips_metric_whitespace(tmp_path):
    path = write(tmp_path, "  alpha , 1 \n")
    assert read_rows(path) == [("alpha", 1.0)]


def test_accepts_exponent_and_sign(tmp_path):
    path = write(tmp_path, "alpha,-1.5e3\nbeta,+2\n")
    assert read_rows(path) == [("alpha", -1500.0), ("beta", 2.0)]


def test_rejects_missing_file(tmp_path):
    with pytest.raises(InputError):
        read_rows(str(tmp_path / "nope.csv"))


def test_rejects_wrong_column_count(tmp_path):
    path = write(tmp_path, "alpha,1,2\n")
    with pytest.raises(InputError):
        read_rows(path)


def test_rejects_non_numeric_value(tmp_path):
    path = write(tmp_path, "alpha,fast\n")
    with pytest.raises(InputError):
        read_rows(path)


def test_rejects_non_finite_value(tmp_path):
    path = write(tmp_path, "alpha,nan\n")
    with pytest.raises(InputError):
        read_rows(path)


def test_rejects_empty_metric_name(tmp_path):
    path = write(tmp_path, ",1\n")
    with pytest.raises(InputError):
        read_rows(path)
