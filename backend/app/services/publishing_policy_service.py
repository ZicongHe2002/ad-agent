from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.publishing_settings import PublishingSettings


def publishing_scope_key(tenant_id: UUID | None) -> str:
    return f"tenant:{tenant_id}" if tenant_id is not None else "global"


@dataclass(frozen=True)
class PublishingPolicy:
    mode: str = "REVIEW"
    auto_disclosure_enabled: bool = False


async def load_publishing_policy(session: AsyncSession, tenant_id: UUID | None) -> PublishingPolicy:
    record = await session.get(PublishingSettings, publishing_scope_key(tenant_id), populate_existing=True)
    if record is not None:
        return PublishingPolicy(record.mode, record.auto_disclosure_enabled)
    settings = get_settings()
    return PublishingPolicy(
        mode="AUTO" if settings.comment_mode == "AUTO" and settings.auto_publish_default else "REVIEW"
    )
