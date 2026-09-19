from __future__ import annotations

try:
    from dramatiq.middleware import AsyncIO
except ImportError:  # pragma: no cover - older Dramatiq compatibility
    AsyncIO = None  # type: ignore[assignment,misc]

from .broker import broker

if AsyncIO is not None and not any(type(item).__name__ == "AsyncIO" for item in broker.middleware):
    broker.add_middleware(AsyncIO())
