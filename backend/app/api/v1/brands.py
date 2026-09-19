from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, is_global_admin, require_roles
from app.api.utils import model_dict, paginate
from app.domain.enums import BrandStatus
from app.models import Brand, User
from app.observability.tracing import current_trace_id
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/brands", tags=["brands"])


class BrandCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    default_language: str = Field(default="zh-CN", min_length=2, max_length=16)


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    default_language: str | None = Field(default=None, min_length=2, max_length=16)
    status: BrandStatus | None = None


@router.post("", status_code=201)
async def create_brand(
    body: BrandCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    brand = Brand(tenant_id=user.tenant_id, **body.model_dump())
    session.add(brand)
    await session.flush()
    await write_audit_log(
        session,
        action="brand.create",
        resource_type="Brand",
        resource_id=brand.id,
        actor_type="USER",
        actor_id=user.id,
        trace_id=current_trace_id(),
        after=model_dict(brand),
    )
    await session.commit()
    return model_dict(brand)


@router.get("")
async def list_brands(
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = select(Brand)
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    stmt = stmt.order_by(Brand.created_at.desc())
    return await paginate(session, stmt, offset=offset, limit=limit)


@router.get("/{brand_id}")
async def get_brand(
    brand_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = select(Brand).where(Brand.id == brand_id)
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    brand = await session.scalar(stmt)
    if brand is None:
        raise LookupError(f"Brand {brand_id} was not found")
    return model_dict(brand)


@router.patch("/{brand_id}")
async def update_brand(
    brand_id: UUID,
    body: BrandUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    stmt = select(Brand).where(Brand.id == brand_id)
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    brand = await session.scalar(stmt)
    if brand is None:
        raise LookupError(f"Brand {brand_id} was not found")
    before = model_dict(brand)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(brand, key, value)
    await session.flush()
    await write_audit_log(
        session,
        action="brand.update",
        resource_type="Brand",
        resource_id=brand.id,
        actor_type="USER",
        actor_id=user.id,
        trace_id=current_trace_id(),
        before=before,
        after=model_dict(brand),
    )
    await session.commit()
    return model_dict(brand)
