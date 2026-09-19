from __future__ import annotations

from .base import PlatformIntegrationStatus
from .douyin.adapter import DouyinAdapter
from .mock.adapter import MockPlatformAdapter
from .mock.persistent_service import PersistentMockPlatformService
from .mock.service import MockPlatformService
from .registry import PlatformRegistry
from .wechat_channels.adapter import WechatChannelsAdapter
from .xiaohongshu.adapter import XiaohongshuAdapter

mock_service = PersistentMockPlatformService()


def build_platform_registry(
    *, mock_service: MockPlatformService | PersistentMockPlatformService | None = None
) -> PlatformRegistry:
    """Build an explicit registry; real adapters remain fail-closed skeletons."""

    return PlatformRegistry(
        [
            MockPlatformAdapter(mock_service or globals()["mock_service"]),
            DouyinAdapter(),
            XiaohongshuAdapter(),
            WechatChannelsAdapter(),
        ]
    )


runtime_registry = build_platform_registry()


async def platform_integration_statuses(
    registry: PlatformRegistry | None = None,
) -> list[PlatformIntegrationStatus]:
    """Describe real runtime wiring without treating account auth as API support."""

    selected = runtime_registry if registry is None else registry
    return [
        await selected.get(platform).get_integration_status()
        for platform in selected.registered_platforms()
    ]


__all__ = [
    "build_platform_registry",
    "mock_service",
    "platform_integration_statuses",
    "runtime_registry",
]
