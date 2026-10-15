"""Accumulating rows into per-metric summaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Metric:
    """Running summary of one metric."""

    name: str
    count: int = 0
    total: float = 0.0
    min: float = 0.0
    max: float = 0.0

    @property
    def mean(self) -> float:
        return self.total / self.count


def summarise(rows: list[tuple[str, float]]) -> dict[str, Metric]:
    """Accumulate ``(metric, value)`` rows into ``{metric: Metric}``.

    Duplicate metric names accumulate into a single entry.  Insertion
    order follows first appearance in ``rows``.
    """
    metrics: dict[str, Metric] = {}
    for name, value in rows:
        metric = metrics.get(name)
        if metric is None:
            metrics[name] = Metric(name=name, count=1, total=value,
                                   min=value, max=value)
            continue
        metric.count += 1
        metric.total += value
        if value < metric.min:
            metric.min = value
        if value > metric.max:
            metric.max = value
    return metrics
