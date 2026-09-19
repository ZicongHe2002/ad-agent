from __future__ import annotations

from hashlib import sha256
from uuid import UUID, uuid4


def new_uuid() -> UUID:
    return uuid4()


def build_publish_idempotency_key(
    *,
    tenant_id: UUID | str,
    platform: str,
    brand_account_id: UUID | str,
    external_post_id: str,
    campaign_id: UUID | str,
    intent_key: str = "TOP_LEVEL_PRIMARY",
) -> str:
    parts = (
        str(tenant_id),
        platform.strip().upper(),
        str(brand_account_id),
        external_post_id.strip(),
        str(campaign_id),
        intent_key.strip().upper(),
    )
    if any(not part for part in parts):
        raise ValueError("idempotency-key components must be non-empty")
    return sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
