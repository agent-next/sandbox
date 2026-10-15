"""A worker that runs queued jobs."""


def run_jobs(jobs):
    """Run every callable in ``jobs`` and return their results."""
    results = []
    for job in jobs:
        results.append(job())
    return results
