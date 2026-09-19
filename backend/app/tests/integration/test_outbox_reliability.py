from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select

from app.models import DeadLetterJob, OutboxEvent
from app.workers import outbox_relay


async def test_poison_outbox_event_moves_to_dead_letter(clean_database, monkeypatch) -> None:
    event_id = uuid4()
    async with clean_database() as session, session.begin():
        session.add(
            OutboxEvent(
                id=event_id,
                aggregate_type="Post",
                aggregate_id=uuid4(),
                event_type="unknown.event",
                payload={"secret": "must-not-be-copied"},
                trace_id=uuid4(),
                idempotency_key=f"poison:{event_id}",
            )
        )

    def fail_dispatch(_event_type: str, _payload: dict[str, object]) -> str:
        raise RuntimeError("sensitive vendor body")

    monkeypatch.setattr(outbox_relay, "dispatch", fail_dispatch)
    for _ in range(outbox_relay.MAX_OUTBOX_ATTEMPTS):
        assert await outbox_relay.relay_once() == 1

    async with clean_database() as session:
        event = await session.get(OutboxEvent, event_id)
        dead = await session.scalar(select(DeadLetterJob))
        assert event is not None
        assert event.published_at is not None
        assert event.attempts == outbox_relay.MAX_OUTBOX_ATTEMPTS
        assert event.last_error == "RuntimeError"
        assert dead is not None
        assert dead.error == "RuntimeError"
        assert "sensitive" not in dead.error
        assert await session.scalar(select(func.count()).select_from(DeadLetterJob)) == 1

    assert await outbox_relay.relay_once() == 0
