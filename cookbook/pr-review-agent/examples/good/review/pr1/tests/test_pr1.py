"""The off-by-one in page_bounds drops the last item of every full page."""

from orders.pagination import page_of


def test_a_full_page_is_not_truncated():
    # The buggy bound returns [3, 4] -- page 2 of 3-per-page loses item 5.
    assert page_of([0, 1, 2, 3, 4, 5], 2, 3) == [3, 4, 5]
