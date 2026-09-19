from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_roles
from app.api.utils import model_dict
from app.domain.enums import Platform, UserRole
from app.models import PublishingSettings, User
from app.observability.tracing import current_trace_id
from app.services.audit_service import write_audit_log
from app.services.capability_service import effective_capabilities
from app.services.publishing_policy_service import load_publishing_policy, publishing_scope_key

router = APIRouter(prefix="/system", tags=["system"])


class PublishingSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["REVIEW", "AUTO"] | None = None
    auto_disclosure_enabled: bool | None = None

    @model_validator(mode="after")
    def no_explicit_nulls(self) -> PublishingSettingsUpdate:
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Publishing settings cannot be null")
        return self


async def _response(session: AsyncSession, user: User) -> dict[str, Any]:
    from app.platforms.runtime import platform_integration_statuses

    record = await session.get(PublishingSettings, publishing_scope_key(user.tenant_id))
    policy = await load_publishing_policy(session, user.tenant_id)
    statuses = {item.platform: item for item in await platform_integration_statuses()}
    readiness = []
    for platform in (Platform.XIAOHONGSHU, Platform.DOUYIN, Platform.MOCK):
        effective, _ = await effective_capabilities(session, platform)
        integration = statuses[platform]
        readiness.append({
            "platform": platform.value,
            "top_level_comment": effective.top_level_comment.value,
            "automatic_publish_available": (
                integration.top_level_publish_configured
                and effective.top_level_comment.value in {"SUPPORTED", "CONDITIONAL"}
            ),
            "reason": integration.reason,
            "source_urls": integration.source_urls,
        })
    return {
        "mode": policy.mode,
        "auto_disclosure_enabled": policy.auto_disclosure_enabled,
        "can_edit": user.role in {UserRole.ADMIN, UserRole.BRAND_MANAGER},
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "updated_at": record.updated_at.isoformat() if record else None,
        "platform_readiness": readiness,
    }


@router.get("/publishing-settings")
async def get_publishing_settings(
    session: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await _response(session, user)


@router.patch("/publishing-settings")
async def update_publishing_settings(
    body: PublishingSettingsUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    key = publishing_scope_key(user.tenant_id)
    record = await session.scalar(select(PublishingSettings).where(
        PublishingSettings.scope_key == key,
    ).with_for_update())
    before = model_dict(record) if record else None
    if record is None:
        policy = await load_publishing_policy(session, user.tenant_id)
        record = PublishingSettings(
            scope_key=key, tenant_id=user.tenant_id,
            mode=policy.mode, auto_disclosure_enabled=policy.auto_disclosure_enabled,
        )
        session.add(record)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    await session.flush()
    await write_audit_log(
        session, action="publishing.settings.update", resource_type="PublishingSettings",
        tenant_id=user.tenant_id, actor_type="USER", actor_id=user.id,
        trace_id=current_trace_id(), before=before, after=model_dict(record),
    )
    await session.commit()
    return await _response(session, user)
