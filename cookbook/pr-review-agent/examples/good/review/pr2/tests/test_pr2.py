"""The string-formatted query makes a customer name into SQL."""

from orders.store import add_order, connect, find_by_customer, init_db


def test_a_customer_name_is_data_not_sql():
    conn = connect(":memory:")
    init_db(conn)
    add_order(conn, 1, "Ada", 100)
    add_order(conn, 2, "Grace", 200)
    # The buggy query interpolates the name, so this quote-bearing name
    # matches rows it should not (or raises a syntax error).
    assert [o["id"] for o in find_by_customer(conn, "Ada' OR '1'='1")] == []
    assert [o["id"] for o in find_by_customer(conn, "Ada")] == [1]
