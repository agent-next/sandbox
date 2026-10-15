"""Process-wide counters shared between worker threads."""

import threading


class Counter:
    """A counter that worker threads may increment concurrently."""

    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()

    def increment(self, amount=1):
        """Add ``amount`` to the counter, atomically."""
        with self._lock:
            self._value += amount

    @property
    def value(self):
        """The current count."""
        return self._value


def count_concurrently(counter, amounts, workers=8):
    """Increment ``counter`` by every value in ``amounts``, from ``workers`` threads.

    The final ``counter.value`` must equal ``sum(amounts)``.
    """
    done = []
    done_lock = threading.Lock()

    def work(chunk):
        for amount in chunk:
            counter.increment(amount)
            with done_lock:
                done.append(amount)

    chunks = [amounts[i::workers] for i in range(workers)]
    threads = [threading.Thread(target=work, args=(c,)) for c in chunks]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return done
