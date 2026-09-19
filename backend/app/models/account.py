from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AggregateMixin, Base, JSONType, enum_type
from app.domain.enums import AccountKind, AuthStatus, Platform

_CREDENTIAL_BUNDLE_CHECK = """
(
  credentials_ciphertext IS NULL
  AND credentials_nonce IS NULL
  AND credentials_key_version IS NULL
)
OR
(
  credentials_ciphertext IS NOT NULL
  AND credentials_nonce IS NOT NULL
  AND credentials_key_version IS NOT NULL
)
"""


class BrandAccount(AggregateMixin, Base):
    __tablename__ = "brand_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "external_account_id", name="platform_external_account"),
        CheckConstraint("length(trim(external_account_id)) > 0", name="external_id_nonempty"),
        CheckConstraint("length(trim(display_name)) > 0", name="display_name_nonempty"),
        CheckConstraint("max_comments_per_day > 0", name="daily_limit_positive"),
        CheckConstraint(_CREDENTIAL_BUNDLE_CHECK, name="credential_bundle_complete"),
        CheckConstraint(
            "credentials_nonce IS NULL OR length(credentials_nonce) = 12",
            name="credential_nonce_12_bytes",
        ),
        CheckConstraint(
            "credentials_key_version IS NULL OR credentials_key_version > 0",
            name="credential_key_version_positive",
        ),
    )

    brand_id: Mapped[UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[Platform] = mapped_column(enum_type(Platform), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    account_kind: Mapped[AccountKind] = mapped_column(enum_type(AccountKind), nullable=False)
    identity_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("account_identity_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    voice_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("voice_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    auto_publish_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    publisher_kill_switch: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    max_comments_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, server_default="20"
    )
    auth_status: Mapped[AuthStatus] = mapped_column(
        enum_type(AuthStatus),
        nullable=False,
        default=AuthStatus.UNCONFIGURED,
        server_default="UNCONFIGURED",
    )
    credentials_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    credentials_nonce: Mapped[bytes | None] = mapped_column(LargeBinary(12))
    credentials_key_version: Mapped[int | None] = mapped_column(Integer)
    credential_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
    last_auth_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformAuthorization(AggregateMixin, Base):
    __tablename__ = "platform_authorizations"
    __table_args__ = (
        UniqueConstraint(
            "platform", "external_subject_id", "authorization_type", name="platform_subject_type"
        ),
        CheckConstraint("length(trim(external_subject_id)) > 0", name="external_subject_nonempty"),
        CheckConstraint("length(trim(authorization_type)) > 0", name="authorization_type_nonempty"),
        CheckConstraint(
            "(token_ciphertext IS NULL AND token_nonce IS NULL AND token_key_version IS NULL) OR "
            "(token_ciphertext IS NOT NULL AND token_nonce IS NOT NULL AND token_key_version IS NOT NULL)",
            name="token_bundle_complete",
        ),
        CheckConstraint(
            "token_nonce IS NULL OR length(token_nonce) = 12",
            name="token_nonce_12_bytes",
        ),
        CheckConstraint(
            "token_key_version IS NULL OR token_key_version > 0",
            name="token_key_version_positive",
        ),
        CheckConstraint(
            "expires_at IS NULL OR authorized_at IS NULL OR expires_at > authorized_at",
            name="expiry_after_authorization",
        ),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    brand_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("brand_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    platform: Mapped[Platform] = mapped_column(enum_type(Platform), nullable=False)
    external_subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    authorization_type: Mapped[str] = mapped_column(String(80), nullable=False, default="OAUTH2")
    status: Mapped[AuthStatus] = mapped_column(
        enum_type(AuthStatus), nullable=False, default=AuthStatus.PENDING, server_default="PENDING"
    )
    scopes: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    conditions: Mapped[dict[str, object]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'")
    )
    token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_nonce: Mapped[bytes | None] = mapped_column(LargeBinary(12))
    token_key_version: Mapped[int | None] = mapped_column(Integer)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
