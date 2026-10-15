"""PR 6 is a clean addition: the new helper reports errors, it does not raise."""

from orders.worker import run_jobs_collecting_errors


def test_errors_are_collected_not_raised():
    def boom():
        raise ValueError("nope")

    results, errors = run_jobs_collecting_errors([lambda: 1, boom, lambda: 3])
    assert results == [1, 3]
    assert len(errors) == 1 and isinstance(errors[0][1], ValueError)
