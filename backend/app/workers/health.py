from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any

from dramatiq.middleware import Middleware

from app.core.config import get_settings

logger = logging.getLogger(__name__)
HEARTBEAT_TTL_SECONDS = 30
HEARTBEAT_INTERVAL_SECONDS = 10
RUNTIME_HEARTBEAT_NAMES = (
    "scheduler",
    "outbox-relay",
    "worker-critical",
    "worker-default",
    "worker-low",
)


def heartbeat_key(worker_name: str) -> str:
    return f"worker_heartbeat:{worker_name}"


async def write_heartbeat(
    redis: Any,
    worker_name: str,
    ttl_seconds: int = HEARTBEAT_TTL_SECONDS,
) -> None:
    await redis.set(
        heartbeat_key(worker_name),
        datetime.now(timezone.utc).isoformat(),
        ex=ttl_seconds,
    )


async def heartbeat_status(redis: Any, worker_names: list[str]) -> dict[str, bool]:
    if not worker_names:
        return {}
    values = await redis.mget([heartbeat_key(name) for name in worker_names])
    return dict(zip(worker_names, [value is not None for value in values], strict=True))


class WorkerHeartbeatMiddleware(Middleware):
    """Emit a heartbeat while an otherwise-idle Dramatiq process is alive."""

    def __init__(
        self,
        *,
        worker_name: str | None = None,
        redis_url: str | None = None,
        interval_seconds: int = HEARTBEAT_INTERVAL_SECONDS,
        ttl_seconds: int = HEARTBEAT_TTL_SECONDS,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.worker_name = worker_name or os.environ.get("WORKER_HEARTBEAT_NAME")
        self.redis_url = redis_url or get_settings().redis_url
        self.interval_seconds = interval_seconds
        self.ttl_seconds = ttl_seconds
        self.client_factory = client_factory
        self._stop = Event()
        self._thread: Thread | None = None

    def after_process_boot(self, broker: Any) -> None:
        del broker
        self.start()

    def before_worker_shutdown(self, broker: Any, worker: Any) -> None:
        del broker, worker
        self.stop()

    def start(self) -> None:
        if not self.worker_name or (self._thread is not None and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = Thread(
            target=self._run,
            name=f"heartbeat-{self.worker_name}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(1, self.interval_seconds + 1))

    def _run(self) -> None:
        from redis import Redis

        factory = self.client_factory or Redis.from_url
        client = factory(self.redis_url)
        try:
            while not self._stop.is_set():
                try:
                    client.set(
                        heartbeat_key(self.worker_name or "unknown"),
                        datetime.now(timezone.utc).isoformat(),
                        ex=self.ttl_seconds,
                    )
                except Exception:
                    logger.exception("worker heartbeat failed worker=%s", self.worker_name)
                self._stop.wait(self.interval_seconds)
        finally:
            try:
                client.close()
            except Exception:
                logger.exception("worker heartbeat Redis close failed")
