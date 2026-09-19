from __future__ import annotations

from collections import Counter
from threading import Lock

from prometheus_client import Counter as PrometheusCounter
from prometheus_client import Histogram

JOBS_TOTAL = PrometheusCounter(
    "firstcomment_jobs_total", "Comment pipeline state transitions", ("state",)
)
RISK_DECISIONS_TOTAL = PrometheusCounter(
    "firstcomment_risk_decisions_total", "Final risk decisions", ("decision",)
)
QUALITY_DECISIONS_TOTAL = PrometheusCounter(
    "firstcomment_quality_decisions_total", "Quality decisions", ("decision",)
)
PUBLISH_TOTAL = PrometheusCounter(
    "firstcomment_publish_total", "Publishing outcomes", ("platform", "result")
)
DETECTION_LATENCY = Histogram(
    "firstcomment_detection_latency_seconds", "Post creation to detection latency"
)
GENERATION_LATENCY = Histogram(
    "firstcomment_generation_latency_seconds", "Comment generation latency"
)
PUBLISH_LATENCY = Histogram("firstcomment_publish_latency_seconds", "External publish latency")
RANK_MEASUREMENT_TOTAL = PrometheusCounter(
    "firstcomment_rank_measurement_total",
    "Rank observations",
    ("type", "confidence"),
)


class InProcessMetrics:
    """Dependency-free fallback used by tests and local development.

    Production deployments may expose the same names through prometheus-client.
    Labels are intentionally bounded to avoid cardinality explosions.
    """

    def __init__(self) -> None:
        self._counter: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self._lock = Lock()

    def increment(self, name: str, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._counter[key] += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                f"{name}{dict(labels) if labels else ''}": value
                for (name, labels), value in self._counter.items()
            }


metrics = InProcessMetrics()


def record_job_state(state: str) -> None:
    JOBS_TOTAL.labels(state=state).inc()
    metrics.increment("firstcomment_jobs_total", state=state)


def record_quality_decision(decision: str) -> None:
    QUALITY_DECISIONS_TOTAL.labels(decision=decision).inc()


def record_risk_decision(decision: str) -> None:
    RISK_DECISIONS_TOTAL.labels(decision=decision).inc()


def record_publish(platform: str, result: str) -> None:
    PUBLISH_TOTAL.labels(platform=platform, result=result).inc()
