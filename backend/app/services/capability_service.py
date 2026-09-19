from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.domain.capabilities import PlatformCapabilities
from app.domain.enums import CapabilityName, CapabilityStatus, Platform
from app.models import CapabilityRecord, CapabilitySnapshot, MockPlatformState


@dataclass(frozen=True)
class CapabilityDecision:
    allowed: bool
    status: str
    reason: str
    manual_only: bool = False
    record_id: UUID | None = None
    missing_scopes: tuple[str, ...] = ()


def verify_capability_record(
    record: Mapping[str, Any] | Any | None,
    *,
    account_type: str | None = None,
    target_content_type: str | None = None,
    has_authorization: bool = False,
    granted_scopes: Collection[str] = (),
    external_creator_id: str | None = None,
    conditions_satisfied: bool | None = None,
    now: datetime | None = None,
) -> CapabilityDecision:
    """Validate evidence freshness and scope before any adapter invocation."""

    if record is None:
        return CapabilityDecision(False, "UNKNOWN", "CAPABILITY_RECORD_MISSING", True)

    def read(name: str, default: Any = None) -> Any:
        if isinstance(record, Mapping):
            return record.get(name, default)
        return getattr(record, name, default)

    status_value = read("status", "UNKNOWN")
    status = str(getattr(status_value, "value", status_value)).upper()
    raw_record_id = read("id")
    record_id = raw_record_id if isinstance(raw_record_id, UUID) else None
    expires_at = read("expires_at")
    current = now or datetime.now(timezone.utc)
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= current:
            return CapabilityDecision(
                False,
                "UNKNOWN",
                "CAPABILITY_EVIDENCE_EXPIRED",
                True,
                record_id,
            )

    scope = read("scope", {}) or {}
    account_types = {str(item).upper() for item in scope.get("account_types", []) or []}
    target_types = {str(item).upper() for item in scope.get("target_content_types", []) or []}
    if account_types and str(account_type or "").upper() not in account_types:
        return CapabilityDecision(False, status, "ACCOUNT_TYPE_OUT_OF_SCOPE", True, record_id)
    if target_types and str(target_content_type or "").upper() not in target_types:
        return CapabilityDecision(False, status, "CONTENT_OUT_OF_SCOPE", True, record_id)
    allowed_creator_ids = {
        str(item) for item in scope.get("allowed_external_creator_ids", []) or []
    }
    if allowed_creator_ids and str(external_creator_id or "") not in allowed_creator_ids:
        return CapabilityDecision(False, status, "CREATOR_OUT_OF_SCOPE", True, record_id)
    if scope.get("authorization_required", False) and not has_authorization:
        return CapabilityDecision(False, "AUTH_REQUIRED", "AUTHORIZATION_REQUIRED", True, record_id)

    raw_required_scopes = scope.get(
        "required_authorization_scopes", scope.get("required_scopes", [])
    )
    required_scopes = {str(item) for item in raw_required_scopes or []}
    missing_scopes = tuple(sorted(required_scopes - {str(item) for item in granted_scopes}))
    if missing_scopes:
        return CapabilityDecision(
            False,
            "AUTH_REQUIRED",
            "AUTHORIZATION_SCOPE_MISSING",
            True,
            record_id,
            missing_scopes,
        )

    if status == "SUPPORTED":
        return CapabilityDecision(True, status, "VERIFIED", record_id=record_id)
    if status == "CONDITIONAL":
        conditions = [str(item) for item in read("conditions", []) or []]
        # A conditional capability is usable only when all stored conditions are
        # explicitly attested by the operation context.  An empty conditions list
        # still relies on the structured scope checks above.
        if conditions and conditions_satisfied is not True:
            return CapabilityDecision(False, status, "CONDITIONS_NOT_ATTESTED", True, record_id)
        if scope.get("authorization_required", False) and not has_authorization:
            return CapabilityDecision(
                False, "AUTH_REQUIRED", "AUTHORIZATION_REQUIRED", True, record_id
            )
        return CapabilityDecision(True, status, "CONDITIONS_SATISFIED", record_id=record_id)
    if status == "AUTH_REQUIRED" and has_authorization:
        return CapabilityDecision(True, status, "AUTHORIZATION_VERIFIED", record_id=record_id)
    if status in {"UNKNOWN", "MANUAL", "UNSUPPORTED", "AUTH_REQUIRED"}:
        return CapabilityDecision(False, status, "MANUAL_OR_UNAVAILABLE", True, record_id)
    if status == "RATE_LIMITED":
        return CapabilityDecision(False, status, "RATE_LIMITED", record_id=record_id)
    return CapabilityDecision(False, status, "DISABLED", record_id=record_id)


async def authorize_capability(
    session: AsyncSession,
    platform: Platform,
    capability: CapabilityName,
    *,
    account_type: str | None,
    target_content_type: str | None,
    has_authorization: bool,
    granted_scopes: Collection[str] = (),
    external_creator_id: str | None = None,
    conditions_satisfied: bool | None = None,
    now: datetime | None = None,
) -> CapabilityDecision:
    """Authorize one concrete operation against current evidence and scope.

    ``effective_capabilities`` is intentionally a display/discovery matrix.  An
    adapter invocation must use this contextual decision so that a globally
    verified status cannot silently authorize an out-of-scope account or target.
    """

    capabilities, records = await effective_capabilities(session, platform)
    record = next((item for item in records if item.capability == capability), None)
    if record is not None:
        return verify_capability_record(
            record,
            account_type=account_type,
            target_content_type=target_content_type,
            has_authorization=has_authorization,
            granted_scopes=granted_scopes,
            external_creator_id=external_creator_id,
            conditions_satisfied=conditions_satisfied,
            now=now,
        )
    if platform != Platform.MOCK:
        return CapabilityDecision(False, "UNKNOWN", "CAPABILITY_RECORD_MISSING", True)
    # Mock is the sole documented platform whose adapter declaration is itself
    # accepted as local evidence. Dynamic UNKNOWN/DISABLED test states still fail
    # closed through the same decision function.
    return verify_capability_record(
        {
            "status": capabilities.status_for(capability),
            "scope": {},
            "conditions": [],
        },
        account_type=account_type,
        target_content_type=target_content_type,
        has_authorization=has_authorization,
        granted_scopes=granted_scopes,
        external_creator_id=external_creator_id,
        conditions_satisfied=conditions_satisfied,
        now=now,
    )


async def effective_capabilities(
    session: AsyncSession,
    platform: Platform,
) -> tuple[PlatformCapabilities, list[CapabilityRecord]]:
    """Return the fail-closed capability matrix used by routing decisions."""

    from app.platforms.runtime import runtime_registry

    if platform == Platform.MOCK:
        state = await session.get(MockPlatformState, "default")
        adapter_values = (
            PlatformCapabilities(**state.capabilities)
            if state is not None and state.capabilities
            else PlatformCapabilities.mock_supported()
        )
    else:
        adapter_values = await runtime_registry.get(platform).get_capabilities()
    records = list(
        (
            await session.scalars(
                select(CapabilityRecord).where(CapabilityRecord.platform == platform)
            )
        ).all()
    )
    by_name = {item.capability: item for item in records}
    values: dict[str, CapabilityStatus] = {}
    for capability in CapabilityName:
        record = by_name.get(capability)
        if record is not None:
            decision = verify_capability_record(record)
            values[capability.value.lower()] = (
                CapabilityStatus.UNKNOWN
                if decision.reason == "CAPABILITY_EVIDENCE_EXPIRED"
                else record.status
            )
        elif platform == Platform.MOCK:
            values[capability.value.lower()] = adapter_values.status_for(capability)
        else:
            # Vendor adapter declarations are documentation, not evidence. Real
            # operations require a stored, scoped capability verification.
            values[capability.value.lower()] = CapabilityStatus.UNKNOWN
    return PlatformCapabilities(**values), records


async def capture_capability_snapshot(
    session: AsyncSession,
    platform: Platform,
    *,
    tenant_id: UUID | None = None,
) -> CapabilitySnapshot:
    capabilities, records = await effective_capabilities(session, platform)
    payload = capabilities.model_dump(mode="json")
    record_ids = sorted(str(item.id) for item in records)
    record_evidence = sorted(
        (
            {
                "id": str(item.id),
                "capability": item.capability.value,
                "status": item.status.value,
                "source_title": item.source_title,
                "source_url": item.source_url,
                "source_owner": item.source_owner,
                "scope": item.scope,
                "conditions": item.conditions,
                "limitations": item.limitations,
                "verified_at": item.verified_at,
                "expires_at": item.expires_at,
            }
            for item in records
        ),
        key=lambda item: str(item["capability"]),
    )
    material = json.dumps(
        {
            "capabilities": payload,
            "record_ids": record_ids,
            "record_evidence": record_evidence,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    records_hash = hashlib.sha256(material.encode()).hexdigest()
    snapshot = await session.scalar(
        select(CapabilitySnapshot).where(
            CapabilitySnapshot.platform == platform,
            CapabilitySnapshot.records_hash == records_hash,
        )
    )
    if snapshot is not None:
        return snapshot
    current = utc_now()
    future_expiries = []
    for item in records:
        if item.expires_at is None:
            continue
        expiry = (
            item.expires_at
            if item.expires_at.tzinfo is not None
            else item.expires_at.replace(tzinfo=timezone.utc)
        )
        if expiry > current:
            future_expiries.append(expiry)
    snapshot = CapabilitySnapshot(
        tenant_id=tenant_id,
        platform=platform,
        capabilities=payload,
        record_ids=record_ids,
        records_hash=records_hash,
        policy_version="capability-registry-v1",
        captured_at=current,
        expires_at=min(future_expiries) if future_expiries else None,
    )
    session.add(snapshot)
    await session.flush()
    return snapshot
