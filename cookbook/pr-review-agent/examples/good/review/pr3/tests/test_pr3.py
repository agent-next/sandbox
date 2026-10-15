"""order_total_with_tax dereferences a total that may be None."""

from orders.store import connect, init_db, order_total_with_tax


def test_tax_of_a_missing_order_is_none_not_a_crash():
    conn = connect(":memory:")
    init_db(conn)
    # The buggy version computes int(None * 1.1) -> TypeError.
    assert order_total_with_tax(conn, 999, 0.1) is None
