from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, is_global_admin, require_roles
from app.api.utils import audit_resource, model_dict, paginate
from app.core.clock import utc_now
from app.domain.enums import ClaimStatus
from app.models import Brand, Product, ProductClaim, User
from app.observability.tracing import current_trace_id
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/products", tags=["products"])


class ProductCreate(BaseModel):
    brand_id: UUID
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=100)
    material: str | None = None
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    approved_claims: list[dict[str, object]] = Field(default_factory=list)
    forbidden_claims: list[dict[str, object]] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_range(self) -> ProductCreate:
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise ValueError("price_min must not exceed price_max")
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    material: str | None = None
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    approved_claims: list[dict[str, object]] | None = None
    forbidden_claims: list[dict[str, object]] | None = None
    active: bool | None = None


class ClaimCreate(BaseModel):
    claim_text: str = Field(min_length=1, max_length=2000)
    evidence: dict[str, object] = Field(default_factory=dict)
    expires_at: datetime | None = None


async def _brand_for_user(
    session: AsyncSession, brand_id: UUID, user: User
) -> Brand | None:
    stmt = select(Brand).where(Brand.id == brand_id)
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    return cast(Brand | None, await session.scalar(stmt))


async def _product_for_user(
    session: AsyncSession, product_id: UUID, user: User
) -> Product | None:
    stmt = select(Product).join(Brand).where(Product.id == product_id)
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    return cast(Product | None, await session.scalar(stmt))


@router.post("", status_code=201)
async def create_product(
    body: ProductCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    brand = await _brand_for_user(session, body.brand_id, user)
    if brand is None:
        raise LookupError(f"Brand {body.brand_id} was not found")
    product = Product(**body.model_dump())
    session.add(product)
    await audit_resource(session, product, user, "product.create")
    await session.commit()
    return model_dict(product)


@router.get("/{product_id}/claims")
async def list_claims(
    product_id: UUID,
    offset: int = 0, limit: int = 100,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if await _product_for_user(session, product_id, user) is None:
        raise LookupError(f"Product {product_id} was not found")
    return await paginate(session,
            select(ProductClaim)
            .where(ProductClaim.product_id == product_id)
            .order_by(ProductClaim.created_at.desc())
        , offset=offset, limit=limit)


@router.post("/{product_id}/claims", status_code=201)
async def create_claim(
    product_id: UUID,
    body: ClaimCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    product = await _product_for_user(session, product_id, user)
    if product is None:
        raise LookupError(f"Product {product_id} was not found")
    claim = ProductClaim(product_id=product_id, **body.model_dump())
    session.add(claim)
    await session.flush()
    await write_audit_log(
        session,
        action="product_claim.create",
        resource_type="ProductClaim",
        resource_id=claim.id,
        actor_type="USER",
        actor_id=user.id,
        trace_id=current_trace_id(),
        after={"claim_text": claim.claim_text, "status": claim.status.value},
    )
    await session.commit()
    return model_dict(claim)


@router.post("/{product_id}/claims/{claim_id}/approve")
async def approve_claim(
    product_id: UUID,
    claim_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    product = await _product_for_user(session, product_id, user)
    if product is None:
        raise LookupError(f"Product {product_id} was not found")
    claim = await session.scalar(
        select(ProductClaim).where(
            ProductClaim.id == claim_id,
            ProductClaim.product_id == product.id,
        )
    )
    if claim is None:
        raise LookupError(f"ProductClaim {claim_id} was not found")
    if not product.active or not claim.evidence:
        raise HTTPException(status_code=422, detail="Approval requires an active product and evidence")
    expiry = claim.expires_at
    if expiry and (expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)) <= utc_now():
        raise HTTPException(status_code=422, detail="Expired claims cannot be approved")
    claim.status = ClaimStatus.APPROVED
    claim.approved_by_user_id = user.id
    claim.approved_at = utc_now()
    await write_audit_log(
        session,
        action="product_claim.approve",
        resource_type="ProductClaim",
        resource_id=claim.id,
        actor_type="USER",
        actor_id=user.id,
        trace_id=current_trace_id(),
        after={"status": claim.status.value},
    )
    await session.commit()
    return model_dict(claim)


@router.get("")
async def list_products(
    brand_id: UUID,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if await _brand_for_user(session, brand_id, user) is None:
        raise LookupError(f"Brand {brand_id} was not found")
    stmt = select(Product).where(Product.brand_id == brand_id).order_by(Product.created_at.desc())
    return await paginate(session, stmt, offset=offset, limit=limit)


@router.patch("/{product_id}")
async def update_product(
    product_id: UUID,
    body: ProductUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    product = await _product_for_user(session, product_id, user)
    if product is None:
        raise LookupError(f"Product {product_id} was not found")
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None and key not in {"material", "price_min", "price_max"}:
            raise HTTPException(status_code=422, detail=f"{key} cannot be null")
    ProductCreate.model_validate({**model_dict(product), **changes})
    before = model_dict(product)
    for key, value in changes.items():
        setattr(product, key, value)
    await write_audit_log(
        session, action="product.update", resource_type="Product", resource_id=product.id,
        actor_type="USER", actor_id=user.id, trace_id=current_trace_id(),
        before=before, after=model_dict(product),
    )
    await session.commit()
    return model_dict(product)


@router.post("/{product_id}/claims/{claim_id}/revoke")
async def revoke_claim(
    product_id: UUID, claim_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    if await _product_for_user(session, product_id, user) is None:
        raise LookupError(f"Product {product_id} was not found")
    claim = await session.scalar(select(ProductClaim).where(
        ProductClaim.id == claim_id, ProductClaim.product_id == product_id,
    ).with_for_update())
    if claim is None:
        raise LookupError(f"ProductClaim {claim_id} was not found")
    before = model_dict(claim)
    claim.status = ClaimStatus.REJECTED
    await write_audit_log(
        session, action="product_claim.revoke", resource_type="ProductClaim", resource_id=claim.id,
        actor_type="USER", actor_id=user.id, trace_id=current_trace_id(),
        before=before, after=model_dict(claim),
    )
    await session.commit()
    return model_dict(claim)
