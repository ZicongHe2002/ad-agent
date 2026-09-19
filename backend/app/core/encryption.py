from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12
KEY_BYTES = 32


@dataclass(frozen=True, slots=True)
class EncryptedPayload:
    ciphertext: bytes
    nonce: bytes
    key_version: int


def _decode_key(encoded_key: str | bytes) -> bytes:
    if isinstance(encoded_key, bytes):
        if len(encoded_key) == KEY_BYTES:
            return encoded_key
        encoded_key = encoded_key.decode("ascii")

    candidate = encoded_key.strip()
    decoders = (
        lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)),
        base64.b64decode,
        bytes.fromhex,
    )
    for decoder in decoders:
        try:
            decoded = decoder(candidate)
        except (ValueError, binascii.Error):
            continue
        if len(decoded) == KEY_BYTES:
            return decoded
    raise ValueError("TOKEN_ENCRYPTION_KEY must encode exactly 32 bytes")


class CredentialCipher:
    """AES-256-GCM credential encryption with explicit key rotation metadata."""

    def __init__(self, key: str | bytes, *, key_version: int = 1) -> None:
        if key_version < 1:
            raise ValueError("key_version must be positive")
        self._cipher = AESGCM(_decode_key(key))
        self.key_version = key_version

    def encrypt(
        self, plaintext: str | bytes, *, associated_data: bytes | None = None
    ) -> EncryptedPayload:
        raw = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = self._cipher.encrypt(nonce, raw, associated_data)
        return EncryptedPayload(ciphertext, nonce, self.key_version)

    def decrypt(
        self,
        payload: EncryptedPayload,
        *,
        associated_data: bytes | None = None,
    ) -> bytes:
        if payload.key_version != self.key_version:
            raise ValueError(f"No key configured for credential key version {payload.key_version}")
        if len(payload.nonce) != NONCE_BYTES:
            raise ValueError("AES-GCM nonce must be 12 bytes")
        return self._cipher.decrypt(payload.nonce, payload.ciphertext, associated_data)

    def decrypt_text(
        self,
        payload: EncryptedPayload,
        *,
        associated_data: bytes | None = None,
    ) -> str:
        return self.decrypt(payload, associated_data=associated_data).decode("utf-8")
