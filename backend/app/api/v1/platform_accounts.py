from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, is_global_admin, require_roles
from app.api.utils import audit_resource, model_dict, paginate
from app.core.clock import utc_now
from app.core.config import get_settings
from app.core.encryption import CredentialCipher
from app.domain.enums import AccountKind, AuthStatus, Platform
from app.models import AccountIdentityProfile, Brand, BrandAccount, User, VoiceProfile

router = APIRouter(prefix="/platform-accounts", tags=["platform-accounts"])
identity_router = APIRouter(prefix="/identity-profiles", tags=["identity-profiles"])
voice_router = APIRouter(prefix="/voice-profiles", tags=["voice-profiles"])


class IdentityCreate(BaseModel):
    legal_or_operating_entity: str = Field(min_length=1, max_length=255)
    account_kind: AccountKind
    public_identity_text: str = Field(min_length=1)
    may_speak_as_consumer: bool = False
    may_use_first_person_experience: bool = False
    requires_brand_disclosure: bool = True
    requires_ai_disclosure_policy_check: bool = True
    approval_evidence: dict[str, Any] = Field(default_factory=dict)


class IdentityUpdate(BaseModel):
    legal_or_operating_entity: str | None = Field(default=None, min_length=1, max_length=255)
    public_identity_text: str | None = Field(default=None, min_length=1, max_length=2000)
    requires_brand_disclosure: bool | None = None
    requires_ai_disclosure_policy_check: bool | None = None
    active: bool | None = None


class VoiceCreate(BaseModel):
    brand_id: UUID
    name: str = Field(min_length=1, max_length=100)
    tone_attributes: list[str] = Field(default_factory=list)
    preferred_sentence_length: str = "SHORT"
    emoji_policy: dict[str, object] = Field(default_factory=dict)
    allowed_phrases: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    approved_examples: list[str] = Field(default_factory=list)
    active: bool = True


class AccountCreate(BaseModel):
    brand_id: UUID
    platform: Platform
    external_account_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=160)
    account_kind: AccountKind
    identity_profile_id: UUID
    voice_profile_id: UUID
    auto_publish_enabled: bool = False
    max_comments_per_day: int = Field(default=20, gt=0)
    credentials: dict[str, Any] | None = None


class AccountUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    identity_profile_id: UUID | None = None
    voice_profile_id: UUID | None = None
    auto_publish_enabled: bool | None = None
    max_comments_per_day: int | None = Field(default=None, gt=0)
    credentials: dict[str, Any] | None = None


class VoiceUpdate(BaseModel):
    tone_attributes: list[str] | None = None
    preferred_sentence_length: str | None = None
    emoji_policy: dict[str, object] | None = None
    allowed_phrases: list[str] | None = None
    forbidden_phrases: list[str] | None = None
    approved_examples: list[str] | None = None
    active: bool | None = None


class KillSwitchUpdate(BaseModel):
    enabled: bool


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


async def _identity_for_user(
    session: AsyncSession, identity_id: UUID, user: User
) -> AccountIdentityProfile | None:
    stmt = select(AccountIdentityProfile).where(AccountIdentityProfile.id == identity_id)
    if not is_global_admin(user):
        stmt = stmt.where(
            AccountIdentityProfile.tenant_id == user.tenant_id,
            AccountIdentityProfile.tenant_id.is_not(None),
        )
    return cast(AccountIdentityProfile | None, await session.scalar(stmt))


async def _voice_for_user(
    session: AsyncSession, voice_id: UUID, user: User
) -> VoiceProfile | None:
    stmt = select(VoiceProfile).join(Brand).where(VoiceProfile.id == voice_id)
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    return cast(VoiceProfile | None, await session.scalar(stmt))


async def _account_for_user(
    session: AsyncSession, account_id: UUID, user: User
) -> BrandAccount | None:
    stmt = select(BrandAccount).join(Brand).where(BrandAccount.id == account_id)
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    return cast(BrandAccount | None, await session.scalar(stmt))


@identity_router.post("", status_code=201)
async def create_identity(
    body: IdentityCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    if body.account_kind == AccountKind.BRAND_OFFICIAL and (
        body.may_speak_as_consumer or body.may_use_first_person_experience
    ):
        raise HTTPException(status_code=422, detail="A brand account cannot impersonate a consumer")
    if body.may_use_first_person_experience and not body.approval_evidence:
        raise HTTPException(status_code=422, detail="Experience permission requires explicit approval evidence")
    values = body.model_dump(exclude={"approval_evidence"})
    if body.may_use_first_person_experience:
        values.update(
            approved_by_user_id=user.id,
            approved_at=utc_now(),
        )
    profile = AccountIdentityProfile(tenant_id=user.tenant_id, **values)
    session.add(profile)
    await audit_resource(session, profile, user, "identity.create")
    if body.approval_evidence:
        from app.observability.tracing import current_trace_id
        from app.services.audit_service import write_audit_log

        await write_audit_log(session, action="identity.experience_approval", resource_type="AccountIdentityProfile",
            resource_id=profile.id, actor_type="USER", actor_id=user.id, trace_id=current_trace_id(),
            after={"evidence": body.approval_evidence})
    await session.commit()
    return model_dict(profile)


@voice_router.post("", status_code=201)
async def create_voice(
    body: VoiceCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    if await _brand_for_user(session, body.brand_id, user) is None:
        raise LookupError(f"Brand {body.brand_id} was not found")
    await session.scalar(select(Brand).where(Brand.id == body.brand_id).with_for_update())
    latest = await session.scalar(
        select(VoiceProfile.version)
        .where(VoiceProfile.brand_id == body.brand_id, VoiceProfile.name == body.name)
        .order_by(VoiceProfile.version.desc())
        .limit(1)
    )
    profile = VoiceProfile(**body.model_dump(), version=(latest or 0) + 1)
    session.add(profile)
    await audit_resource(session, profile, user, "voice.create")
    await session.commit()
    return model_dict(profile)


@router.post("", status_code=201)
async def create_account(
    body: AccountCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER")),
) -> dict[str, Any]:
    brand = await _brand_for_user(session, body.brand_id, user)
    identity = await _identity_for_user(session, body.identity_profile_id, user)
    voice = await _voice_for_user(session, body.voice_profile_id, user)
    if brand is None or identity is None or voice is None:
        raise HTTPException(status_code=422, detail="Identity and voice profiles are required")
    if identity.tenant_id != brand.tenant_id or voice.brand_id != brand.id:
        raise HTTPException(
            status_code=422,
            detail="Identity and voice profiles must belong to the account brand",
        )
    if not identity.active or not voice.active:
        raise HTTPException(status_code=422, detail="Active identity and voice profiles are required")
    if identity.account_kind != body.account_kind:
        raise HTTPException(status_code=422, detail="Account and identity kinds must match")
    values = body.model_dump(exclude={"credentials"})
    account = BrandAccount(**values)
    session.add(account)
    await session.flush()
    if body.credentials is not None:
        key = get_settings().token_encryption_key
        if key is None:
            raise HTTPException(
                status_code=503, detail="Credential encryption key is not configured"
            )
        cipher = CredentialCipher(
            key.get_secret_value(), key_version=get_settings().token_encryption_key_version
        )
        encrypted = cipher.encrypt(
            json.dumps(body.credentials, separators=(",", ":")),
            associated_data=str(account.id).encode(),
        )
        account.credentials_ciphertext = encrypted.ciphertext
        account.credentials_nonce = encrypted.nonce
        account.credentials_key_version = encrypted.key_version
        account.auth_status = AuthStatus.PENDING
    await audit_resource(session, account, user, "account.create")
    await session.commit()
    return model_dict(account)


@router.get("")
async def list_accounts(
    platform: Platform | None = None,
    offset: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = select(BrandAccount).join(Brand)
    if not is_global_admin(user):
        stmt = stmt.where(
            Brand.tenant_id == user.tenant_id,
            Brand.tenant_id.is_not(None),
        )
    if platform:
        stmt = stmt.where(BrandAccount.platform == platform)
    stmt = stmt.order_by(BrandAccount.created_at.desc())
    return await paginate(session, stmt, offset=offset, limit=limit)


@router.post("/{account_id}/verify-auth")
async def verify_auth(
    account_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    account = await _account_for_user(session, account_id, user)
    if account is None:
        raise LookupError(f"BrandAccount {account_id} was not found")
    if account.platform == Platform.MOCK:
        account.auth_status = AuthStatus.VALID
        account.last_auth_verified_at = utc_now()
        await audit_resource(session, account, user, "account.verify_auth")
        await session.commit()
    else:
        raise HTTPException(status_code=409, detail="Official platform authorization verification is not integrated; status is unchanged")
    return {"account_id": str(account.id), "auth_status": account.auth_status.value}


@router.post("/{account_id}/kill-switch")
async def account_kill_switch(
    account_id: UUID,
    body: KillSwitchUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    account = await _account_for_user(session, account_id, user)
    if account is None:
        raise LookupError(f"BrandAccount {account_id} was not found")
    before = model_dict(account)
    account.publisher_kill_switch = body.enabled
    await audit_resource(session, account, user, "account.kill_switch", before=before)
    await session.commit()
    return model_dict(account)


@identity_router.get("")
async def list_identities(
    offset: int = 0, limit: int = 100,
    session: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    stmt = select(AccountIdentityProfile).order_by(AccountIdentityProfile.created_at.desc())
    if not is_global_admin(user):
        stmt = stmt.where(AccountIdentityProfile.tenant_id == user.tenant_id, AccountIdentityProfile.tenant_id.is_not(None))
    return await paginate(session, stmt, offset=offset, limit=limit)


@identity_router.get("/{identity_id}")
async def get_identity(identity_id: UUID, session: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    profile = await _identity_for_user(session, identity_id, user)
    if profile is None:
        raise LookupError(f"Identity {identity_id} was not found")
    return model_dict(profile)


@identity_router.patch("/{identity_id}")
async def update_identity(identity_id: UUID, body: IdentityUpdate, session: AsyncSession = Depends(get_db),
                          user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER"))) -> dict[str, Any]:
    profile = await _identity_for_user(session, identity_id, user)
    if profile is None:
        raise LookupError(f"Identity {identity_id} was not found")
    before = model_dict(profile)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            raise HTTPException(status_code=422, detail=f"{key} cannot be null")
        setattr(profile, key, value)
    await audit_resource(session, profile, user, "identity.update", before=before)
    await session.commit()
    return model_dict(profile)


@voice_router.get("")
async def list_voices(brand_id: UUID | None = None, offset: int = 0, limit: int = 100,
                      session: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    stmt = select(VoiceProfile).join(Brand).order_by(VoiceProfile.created_at.desc())
    if not is_global_admin(user):
        stmt = stmt.where(Brand.tenant_id == user.tenant_id, Brand.tenant_id.is_not(None))
    if brand_id:
        stmt = stmt.where(VoiceProfile.brand_id == brand_id)
    return await paginate(session, stmt, offset=offset, limit=limit)


@voice_router.get("/{voice_id}")
async def get_voice(voice_id: UUID, session: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    profile = await _voice_for_user(session, voice_id, user)
    if profile is None:
        raise LookupError(f"Voice {voice_id} was not found")
    return model_dict(profile)


@voice_router.patch("/{voice_id}")
async def update_voice(voice_id: UUID, body: VoiceUpdate, session: AsyncSession = Depends(get_db),
                       user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER"))) -> dict[str, Any]:
    profile = await _voice_for_user(session, voice_id, user)
    if profile is None:
        raise LookupError(f"Voice {voice_id} was not found")
    changes = body.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Voice fields cannot be null")
    # Content versions are immutable. An account explicitly selects the new ID;
    # existing accounts and historical generated content keep their old version.
    return await create_voice(VoiceCreate.model_validate({**model_dict(profile), **changes}), session, user)


# Static identity/voice paths must be registered before /{account_id}.
router.include_router(identity_router)
router.include_router(voice_router)


@router.get("/{account_id}")
async def get_account(account_id: UUID, session: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    account = await _account_for_user(session, account_id, user)
    if account is None:
        raise LookupError(f"Account {account_id} was not found")
    identity = await session.get(AccountIdentityProfile, account.identity_profile_id)
    voice = await session.get(VoiceProfile, account.voice_profile_id)
    return {**model_dict(account), "identity": model_dict(identity) if identity else None, "voice": model_dict(voice) if voice else None}


@router.patch("/{account_id}")
async def update_account(account_id: UUID, body: AccountUpdate, session: AsyncSession = Depends(get_db),
                         user: User = Depends(require_roles("ADMIN", "BRAND_MANAGER"))) -> dict[str, Any]:
    account = await _account_for_user(session, account_id, user)
    if account is None:
        raise LookupError(f"Account {account_id} was not found")
    changes = body.model_dump(exclude_unset=True, exclude={"credentials"})
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Account fields cannot be null")
    identity = await _identity_for_user(session, body.identity_profile_id or account.identity_profile_id, user)
    voice = await _voice_for_user(session, body.voice_profile_id or account.voice_profile_id, user)
    brand = await _brand_for_user(session, account.brand_id, user)
    if not identity or not voice or not brand or not identity.active or not voice.active:
        raise HTTPException(status_code=422, detail="Active identity and voice profiles are required")
    if identity.account_kind != account.account_kind or identity.tenant_id != brand.tenant_id or voice.brand_id != brand.id:
        raise HTTPException(status_code=422, detail="Identity and voice must match the account kind and brand")
    before = model_dict(account)
    for key, value in changes.items():
        setattr(account, key, value)
    if body.credentials is not None:
        key_value = get_settings().token_encryption_key
        if key_value is None:
            raise HTTPException(status_code=503, detail="Credential encryption key is not configured")
        encrypted = CredentialCipher(key_value.get_secret_value(), key_version=get_settings().token_encryption_key_version).encrypt(
            json.dumps(body.credentials, separators=(",", ":")), associated_data=str(account.id).encode(),
        )
        account.credentials_ciphertext = encrypted.ciphertext
        account.credentials_nonce = encrypted.nonce
        account.credentials_key_version = encrypted.key_version
        account.auth_status = AuthStatus.PENDING
        account.last_auth_verified_at = None
    await audit_resource(session, account, user, "account.update", before=before)
    await session.commit()
    return model_dict(account)
