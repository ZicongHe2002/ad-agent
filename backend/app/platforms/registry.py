"""In-process registry for platform adapters."""

from __future__ import annotations

from collections.abc import Iterable

from ..domain.enums import Platform
from .base import PlatformAdapter
from .errors import PlatformNotRegisteredError


def _platform(value: Platform | str) -> Platform:
    if isinstance(value, Platform):
        return value
    raw = str(value)
    try:
        return Platform(raw.upper())
    except ValueError as exc:
        raise PlatformNotRegisteredError(
            "Unknown platform",
            platform=raw,
            details={"requested_platform": raw},
        ) from exc


class PlatformRegistry:
    """Maps each platform to exactly one explicitly registered adapter."""

    def __init__(self, adapters: Iterable[PlatformAdapter] | None = None) -> None:
        self._adapters: dict[Platform, PlatformAdapter] = {}
        for adapter in adapters or ():
            self.register(adapter)

    def register(
        self,
        adapter: PlatformAdapter,
        *,
        replace: bool = False,
    ) -> PlatformAdapter:
        platform = _platform(adapter.platform)
        if platform in self._adapters and not replace:
            raise ValueError(f"Adapter already registered for {platform.value}")
        self._adapters[platform] = adapter
        return adapter

    def get(self, platform: Platform | str) -> PlatformAdapter:
        key = _platform(platform)
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise PlatformNotRegisteredError(
                f"No adapter registered for {key.value}",
                platform=key.value,
            ) from exc

    def unregister(self, platform: Platform | str) -> PlatformAdapter | None:
        return self._adapters.pop(_platform(platform), None)

    def registered_platforms(self) -> tuple[Platform, ...]:
        return tuple(sorted(self._adapters, key=lambda item: item.value))

    def __contains__(self, platform: object) -> bool:
        try:
            key = _platform(platform)  # type: ignore[arg-type]
        except (PlatformNotRegisteredError, TypeError, ValueError):
            return False
        return key in self._adapters

    def __len__(self) -> int:
        return len(self._adapters)


platform_registry = PlatformRegistry()


def register(adapter: PlatformAdapter, *, replace: bool = False) -> PlatformAdapter:
    return platform_registry.register(adapter, replace=replace)


def get(platform: Platform | str) -> PlatformAdapter:
    return platform_registry.get(platform)


__all__ = ["PlatformRegistry", "get", "platform_registry", "register"]
