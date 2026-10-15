"""Incrementing without the lock loses concurrent updates to the file."""

import threading

from orders.metrics import Counter, count_concurrently


def test_concurrent_increments_are_not_lost(tmp_path):
    # The buggy increment reads, adds and writes with no lock held across
    # the three steps, so two threads interleave and one update is lost.
    counter = Counter(tmp_path / "counter.json")
    total = count_concurrently(counter, [1] * 400, workers=8)
    assert total == 400
    assert counter.value == 400


def test_the_counter_is_still_a_counter(tmp_path):
    # A trivially "safe" counter that never increments would pass the test
    # above; this pins the ordinary behaviour so the pair discriminates.
    counter = Counter(tmp_path / "counter.json")
    counter.increment(5)
    counter.increment()
    assert counter.value == 6
