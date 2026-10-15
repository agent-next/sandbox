"""A very small in-memory job queue."""


class JobQueue:
    """A FIFO queue of (name, callable) jobs."""

    def __init__(self):
        self._jobs = []

    def put(self, name, job):
        """Append a job to the queue."""
        self._jobs.append((name, job))

    def drain(self):
        """Return and clear every queued job, in order."""
        jobs, self._jobs = self._jobs, []
        return jobs
