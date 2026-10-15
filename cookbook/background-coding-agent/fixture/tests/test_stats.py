"""Tests for the accumulator."""

from measurectl.stats import summarise


def test_counts_and_totals_each_metric():
    metrics = summarise([("alpha", 1.0), ("alpha", 2.0), ("beta", 5.0)])
    assert metrics["alpha"].count == 2
    assert metrics["alpha"].total == 3.0
    assert metrics["beta"].count == 1


def test_mean_is_total_over_count():
    metrics = summarise([("alpha", 1.0), ("alpha", 2.0), ("alpha", 3.0)])
    assert metrics["alpha"].mean == 2.0


def test_min_and_max_track_extremes():
    metrics = summarise([("alpha", 3.0), ("alpha", -1.0), ("alpha", 2.0)])
    assert metrics["alpha"].min == -1.0
    assert metrics["alpha"].max == 3.0


def test_single_row_metric_has_equal_extremes():
    metrics = summarise([("beta", 7.5)])
    assert metrics["beta"].min == metrics["beta"].max == metrics["beta"].mean


def test_insertion_order_follows_first_appearance():
    metrics = summarise([("gamma", 1.0), ("alpha", 2.0), ("gamma", 3.0)])
    assert list(metrics) == ["gamma", "alpha"]


def test_empty_input_gives_no_metrics():
    assert summarise([]) == {}
