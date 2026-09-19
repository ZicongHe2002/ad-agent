from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .clock import utc_now

_PASSWORD_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("password must contain at least 10 characters")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(
    *,
    subject: UUID | str,
    secret: str,
    expires_delta: timedelta,
    algorithm: str = "HS256",
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = utc_now()
    claims: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "type": "access",
    }
    if extra_claims:
        reserved = {"sub", "iat", "exp", "type"}
        claims.update({key: value for key, value in extra_claims.items() if key not in reserved})
    return jwt.encode(claims, secret, algorithm=algorithm)


def decode_access_token(token: str, *, secret: str, algorithm: str = "HS256") -> dict[str, Any]:
    claims = jwt.decode(token, secret, algorithms=[algorithm], options={"require": ["sub", "exp"]})
    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("token has an invalid type")
    return claims
