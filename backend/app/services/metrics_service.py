from __future__ import annotations

from collections.abc import Iterable, Sequence


def percentile(values: Sequence[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile_value
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def latency_summary(values: Iterable[float]) -> dict[str, float | int | None]:
    materialized = list(values)
    return {
        "count": len(materialized),
        "p50": percentile(materialized, 0.50),
        "p90": percentile(materialized, 0.90),
        "p95": percentile(materialized, 0.95),
        "p99": percentile(materialized, 0.99),
    }


def ranking_summary(ranks: Iterable[int | None]) -> dict[str, float | int]:
    materialized = list(ranks)
    measured = [rank for rank in materialized if rank is not None]
    total = len(materialized)
    denominator = len(measured)
    return {
        "samples": total,
        "measured": denominator,
        "measurement_coverage": denominator / total if total else 0.0,
        "first_comment_success_rate": (
            sum(rank == 1 for rank in measured) / denominator if denominator else 0.0
        ),
        "top5_success_rate": (
            sum(rank <= 5 for rank in measured) / denominator if denominator else 0.0
        ),
    }
