from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID, uuid4

trace_id_var: ContextVar[UUID | None] = ContextVar("trace_id", default=None)


def current_trace_id() -> UUID:
    value = trace_id_var.get()
    if value is None:
        value = uuid4()
        trace_id_var.set(value)
    return value
