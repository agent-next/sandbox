"""Tests shipped with the fixture repo."""

from orders.config import load_config
from orders.pagination import page_of
from orders.metrics import Counter, count_concurrently
from orders.store import (
    add_order,
    connect,
    find_by_customer,
    init_db,
    order_total_with_tax,
)
from orders.worker import run_jobs


def test_page_of_returns_a_full_page():
    assert page_of(list(range(10)), 2, 3) == [3, 4, 5]


def test_find_by_customer_returns_only_that_customer():
    conn = connect(":memory:")
    init_db(conn)
    add_order(conn, 1, "Ada", 100)
    add_order(conn, 2, "Grace", 200)
    assert [o["id"] for o in find_by_customer(conn, "Ada")] == [1]


def test_run_jobs_returns_results_in_order():
    assert run_jobs([lambda: 1, lambda: 2]) == [1, 2]


def test_load_config_defaults_without_a_file():
    assert load_config()["page_size"] == 20


def test_count_concurrently_counts_every_increment(tmp_path):
    counter = Counter(tmp_path / "counter.json")
    assert count_concurrently(counter, [1] * 200, workers=8) == 200


def test_order_total_with_tax_of_a_missing_order_is_none():
    conn = connect(":memory:")
    init_db(conn)
    assert order_total_with_tax(conn, 999, 0.1) is None
