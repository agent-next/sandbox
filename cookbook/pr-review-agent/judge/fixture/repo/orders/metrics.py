"""Process-wide counters shared between worker threads."""

import json
import threading


class Counter:
    """A counter persisted to a JSON file, shared between worker threads."""

    def __init__(self, path):
        self._path = str(path)
        self._lock = threading.Lock()
        self._write(0)

    def _read(self):
        with open(self._path, encoding="utf-8") as handle:
            return json.load(handle)["value"]

    def _write(self, value):
        with open(self._path, "w", encoding="utf-8") as handle:
            json.dump({"value": value}, handle)

    def increment(self, amount=1):
        """Add ``amount`` to the counter, atomically."""
        with self._lock:
            self._write(self._read() + amount)

    @property
    def value(self):
        """The current count."""
        return self._read()


def count_concurrently(counter, amounts, workers=8):
    """Increment ``counter`` by every value in ``amounts``, from ``workers`` threads.

    The final ``counter.value`` must equal ``sum(amounts)``.
    """
    def work(chunk):
        for amount in chunk:
            counter.increment(amount)

    chunks = [amounts[i::workers] for i in range(workers)]
    threads = [threading.Thread(target=work, args=(c,)) for c in chunks]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return counter.value
