"""sqlite-backed storage for orders."""

import sqlite3


def connect(db_path):
    """Open a connection to the order database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    """Create the ``orders`` table if it is missing."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS orders ("
        " id INTEGER PRIMARY KEY,"
        " customer TEXT NOT NULL,"
        " total_cents INTEGER NOT NULL)"
    )
    conn.commit()


def add_order(conn, order_id, customer, total_cents):
    """Insert one order."""
    conn.execute(
        "INSERT INTO orders (id, customer, total_cents) VALUES (?, ?, ?)",
        (order_id, customer, total_cents),
    )
    conn.commit()


def find_by_customer(conn, customer):
    """Return every order for ``customer``, newest id first."""
    cur = conn.execute(
        "SELECT id, customer, total_cents FROM orders"
        " WHERE customer = ? ORDER BY id DESC",
        (customer,),
    )
    return [dict(row) for row in cur.fetchall()]


def order_total(conn, order_id):
    """Return the total in cents of one order, or ``None`` when it is absent."""
    cur = conn.execute(
        "SELECT total_cents FROM orders WHERE id = ?", (order_id,)
    )
    row = cur.fetchone()
    if row is None:
        return None
    return row["total_cents"]


def order_total_with_tax(conn, order_id, rate):
    """Return one order's total with tax, or ``None`` when it is absent."""
    total = order_total(conn, order_id)
    if total is None:
        return None
    return int(total * (1 + rate))
