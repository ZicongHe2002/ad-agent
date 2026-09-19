"""Cross-process metrics derived from committed database records.

The API and workers do not share Python memory. A fresh scrape registry reads
durable records, so restarting the API does not reset worker business metrics.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    HistogramMetricFamily,
    Metric,
)
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CommentJob,
    CommentQualityEvaluation,
    Post,
    PublishedComment,
    PublishJob,
    RiskEvent,
    TimelineEvent,
)


class _SnapshotCollector:
    def __init__(self, samples: list[Metric]):
        self.samples = samples

    def collect(self) -> Iterable[Metric]:
        return iter(self.samples)


async def generate_durable_metrics(session: AsyncSession) -> bytes:
    samples: list[Metric] = []
    for model, column, name, description, label in (
        (CommentJob, CommentJob.state, "firstcomment_job_state", "Current committed job states", "state"),
        (PublishJob, PublishJob.state, "firstcomment_publish_job_state", "Current committed publish states", "state"),
    ):
        gauge = GaugeMetricFamily(name, description, labels=[label])
        for value, count in (await session.execute(select(column, func.count()).select_from(model).group_by(column))).all():
            gauge.add_metric([value.value], count)
        samples.append(gauge)
    transitions = CounterMetricFamily("firstcomment_jobs", "Persisted pipeline transitions", labels=["state"])
    for event, count in (await session.execute(select(TimelineEvent.event_type, func.count()).where(
        TimelineEvent.event_type.like("job.%")
    ).group_by(TimelineEvent.event_type))).all():
        transitions.add_metric([event.removeprefix("job.").upper()], count)
    samples.append(transitions)
    for evaluation_model, decision_column, name in (
        (CommentQualityEvaluation, CommentQualityEvaluation.decision, "firstcomment_quality_decisions"),
        (RiskEvent, RiskEvent.final_decision, "firstcomment_risk_decisions"),
    ):
        counter = CounterMetricFamily(name, "Persisted evaluation outcomes", labels=["decision"])
        for decision, count in (await session.execute(select(decision_column, func.count()).select_from(evaluation_model).group_by(decision_column))).all():
            counter.add_metric([decision.value], count)
        samples.append(counter)
    published = CounterMetricFamily("firstcomment_publish", "Confirmed publication ledger", labels=["platform", "result"])
    for platform, count in (await session.execute(select(PublishedComment.platform, func.count()).group_by(PublishedComment.platform))).all():
        published.add_metric([platform.value, "PUBLISHED"], count)
    samples.append(published)

    dialect = session.get_bind().dialect.name
    duration: Any = (
        (func.julianday(Post.detected_at) - func.julianday(Post.published_at)) * 86400
        if dialect == "sqlite" else func.extract("epoch", Post.detected_at - Post.published_at)
    )
    duration = case((duration < 0, 0), else_=duration)
    bounds = [0.1, 0.5, 1, 2, 5, 10, 30, 60]
    row = (await session.execute(select(
        *[func.sum(case((duration <= bound, 1), else_=0)) for bound in bounds],
        func.count(Post.id), func.sum(duration),
    ))).one()
    histogram = HistogramMetricFamily("firstcomment_detection_latency_seconds", "Persisted post creation to detection latency")
    histogram.add_metric([], [(str(bound), row[index] or 0) for index, bound in enumerate(bounds)] + [("+Inf", row[-2])], sum_value=float(row[-1] or 0))
    samples.append(histogram)
    registry = CollectorRegistry()
    registry.register(_SnapshotCollector(samples))
    return generate_latest(registry)
