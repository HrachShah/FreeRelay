"""
FreeRelay — Cryptographic Utilities
=====================================
AES-256-GCM encryption for API keys at rest,
HMAC-SHA256 signing for audit record integrity.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from typing import Any

# ─── AES-256-GCM ─────────────────────────────────────────────────────────────


def encrypt_key(plaintext: str, secret: bytes) -> str:
    """
    Encrypt a plaintext string (e.g. API key) using AES-256-GCM.

    The output format is base64-encoded: [12-byte nonce][16-byte tag][ciphertext]

    Args:
        plaintext: The secret to encrypt.
        secret: 32-byte encryption key.

    Returns:
        Base64-encoded ciphertext bundle.

    Raises:
        ValueError: If secret is not 32 bytes.
    """
    import base64

    if len(secret) != 32:
        raise ValueError("AES-256-GCM requires a 32-byte key")

    nonce = os.urandom(12)
    plaintext_bytes = plaintext.encode("utf-8")

    tag, ciphertext = _aes_gcm_encrypt(plaintext_bytes, secret, nonce)

    bundle = nonce + tag + ciphertext
    return base64.b64encode(bundle).decode("ascii")


def decrypt_key(ciphertext: str, secret: bytes) -> str:
    """
    Decrypt a ciphertext bundle produced by encrypt_key.

    Args:
        ciphertext: Base64-encoded bundle.
        secret: 32-byte encryption key (same one used for encryption).

    Returns:
        Original plaintext string.

    Raises:
        ValueError: If decryption fails or tag verification fails.
    """
    import base64

    if len(secret) != 32:
        raise ValueError("AES-256-GCM requires a 32-byte key")

    try:
        bundle = base64.b64decode(ciphertext)
    except Exception as exc:
        raise ValueError("Invalid base64 ciphertext") from exc

    if len(bundle) < 28:  # 12 (nonce) + 16 (tag) minimum
        raise ValueError("Ciphertext too short")

    nonce = bundle[:12]
    tag = bundle[12:28]
    encrypted = bundle[28:]

    plaintext_bytes = _aes_gcm_decrypt(encrypted, secret, nonce, tag)
    return plaintext_bytes.decode("utf-8")


def _aes_gcm_encrypt(plaintext: bytes, key: bytes, nonce: bytes) -> tuple[bytes, bytes]:
    """
    Pure-Python AES-256-GCM encryption.
    Returns (tag, ciphertext).
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, plaintext, None)
        # cryptography lib returns tag || ciphertext
        tag = ct[:16]
        ciphertext = ct[16:]
        return tag, ciphertext
    except ImportError:
        raise RuntimeError(
            "cryptography package required for AES-256-GCM. "
            "Install with: pip install cryptography"
        )


def _aes_gcm_decrypt(ciphertext: bytes, key: bytes, nonce: bytes, tag: bytes) -> bytes:
    """
    Pure-Python AES-256-GCM decryption.
    Returns plaintext.
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, tag + ciphertext, None)
    except ImportError:
        raise RuntimeError(
            "cryptography package required for AES-256-GCM. "
            "Install with: pip install cryptography"
        )
    except Exception as exc:
        raise ValueError("Decryption failed: invalid key or corrupted data") from exc


# ─── HMAC-SHA256 Audit Signing ───────────────────────────────────────────────


def sign_audit_record(record_fields: dict[str, Any], tenant_secret: str) -> str:
    """
    Sign an audit record with HMAC-SHA256.

    The record fields are canonicalized to JSON with sorted keys
    to ensure deterministic signing.

    Args:
        record_fields: Dictionary of audit record fields (excluding 'signature').
        tenant_secret: Per-tenant secret for HMAC signing.

    Returns:
        Hex-encoded HMAC-SHA256 signature.
    """
    canonical = json.dumps(record_fields, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        tenant_secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_audit_record(
    record_fields: dict[str, Any],
    tenant_secret: str,
    signature: str,
) -> bool:
    """
    Verify an audit record's HMAC-SHA256 signature using constant-time comparison.

    Args:
        record_fields: Dictionary of audit record fields (excluding 'signature').
        tenant_secret: Per-tenant secret used during signing.
        signature: Hex-encoded signature to verify.

    Returns:
        True if signature is valid, False otherwise.
    """
    expected = sign_audit_record(record_fields, tenant_secret)
    return hmac.compare_digest(expected, signature)


# ─── Utility ─────────────────────────────────────────────────────────────────


def generate_tenant_secret() -> str:
    """Generate a cryptographically secure 64-character hex secret."""
    return secrets.token_hex(32)


def hash_for_logging(value: str) -> str:
    """One-way SHA-256 hash suitable for log correlation (non-reversible)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
