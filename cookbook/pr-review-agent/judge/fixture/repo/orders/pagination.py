"""Page helpers for listing orders."""


def page_bounds(page, page_size):
    """Return the ``(start, stop)`` slice for a 1-based ``page``."""
    start = (page - 1) * page_size
    stop = start + page_size
    return start, stop


def page_of(items, page, page_size):
    """Return the items on ``page``, 1-based, ``page_size`` per page."""
    start, stop = page_bounds(page, page_size)
    return items[start:stop]
