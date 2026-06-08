"""
FreeRelay — KeyStore: AES-256-GCM encrypted API key storage.

Keys are stored in ``~/.freerelay/keys.enc`` as a JSON blob encrypted with
AES-256-GCM.  The master key is resolved from (in order):

  1. ``FREERELAY_MASTER_KEY`` environment variable (hex-encoded 32-byte key)
  2. scrypt-derived from ``FREERELAY_MASTER_PASSPHRASE`` + a stored salt

When neither is set the keystore is a no-op and loading returns an empty dict
— plaintext ``.env`` keys always take precedence via Pydantic settings.

Usage::

    store = KeyStore()
    store.set("GROQ_API_KEY", "gsk_...")
    store.save()

    # On next startup:
    merged = store.load()          # {env_var: value, ...}
    # Pass to ProviderKeys(**merged) or let main.py merge them
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("freerelay.keystore")

_STORE_PATH = Path.home() / ".freerelay" / "keys.enc"
_SALT_PATH = Path.home() / ".freerelay" / "keys.salt"

# Lazy import so the cryptography package is only required when actually used
def _get_crypto() -> tuple:  # type: ignore[return]
    try:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        return AESGCM, Scrypt, default_backend
    except ImportError as exc:
        raise ImportError(
            "Install the 'cryptography' package to use the encrypted keystore: "
            "pip install cryptography"
        ) from exc


class KeyStore:
    """Encrypted API key store (AES-256-GCM)."""

    def __init__(
        self,
        path: Path | None = None,
        salt_path: Path | None = None,
    ) -> None:
        self._path = path or _STORE_PATH
        self._salt_path = salt_path or _SALT_PATH
        self._data: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Master key resolution
    # ------------------------------------------------------------------

    def _resolve_master_key(self) -> bytes | None:
        """Return the 32-byte AES master key, or None if not configured."""
        raw_key = os.environ.get("FREERELAY_MASTER_KEY", "")
        if raw_key:
            try:
                key = bytes.fromhex(raw_key)
                if len(key) != 32:
                    logger.warning(
                        "FREERELAY_MASTER_KEY must be 64 hex chars (32 bytes); ignoring"
                    )
                    return None
                return key
            except ValueError:
                logger.warning("FREERELAY_MASTER_KEY is not valid hex; ignoring")
                return None

        passphrase = os.environ.get("FREERELAY_MASTER_PASSPHRASE", "")
        if passphrase:
            return self._derive_key(passphrase.encode())

        return None

    def _derive_key(self, passphrase: bytes) -> bytes:
        """Derive a 32-byte AES key from a passphrase using scrypt."""
        _, Scrypt, backend = _get_crypto()
        salt = self._load_or_create_salt()
        kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1, backend=backend())
        return kdf.derive(passphrase)

    def _load_or_create_salt(self) -> bytes:
        if self._salt_path.exists():
            return self._salt_path.read_bytes()
        salt = os.urandom(16)
        self._salt_path.parent.mkdir(parents=True, exist_ok=True)
        self._salt_path.write_bytes(salt)
        return salt

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def set(self, env_var: str, value: str) -> None:
        """Store *value* under *env_var* (e.g. ``"GROQ_API_KEY"``)."""
        self._data[env_var] = value

    def remove(self, env_var: str) -> bool:
        return self._data.pop(env_var, None) is not None

    def list_masked(self) -> dict[str, str]:
        """Return keys with values masked to ``sk-…[last4]``."""
        masked: dict[str, str] = {}
        for k, v in self._data.items():
            if len(v) > 8:
                masked[k] = f"{v[:4]}…{v[-4:]}"
            else:
                masked[k] = "****"
        return masked

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> bool:
        """Encrypt and save the keystore to disk. Returns False if no master key."""
        master_key = self._resolve_master_key()
        if master_key is None:
            logger.warning(
                "No master key configured — set FREERELAY_MASTER_KEY or "
                "FREERELAY_MASTER_PASSPHRASE to enable encrypted key storage"
            )
            return False

        AESGCM, _, _ = _get_crypto()
        plaintext = json.dumps(self._data).encode()
        nonce = os.urandom(12)
        ciphertext = AESGCM(master_key).encrypt(nonce, plaintext, None)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(nonce + ciphertext)
        logger.info("Encrypted keystore saved to %s", self._path)
        return True

    def load(self) -> dict[str, str]:
        """
        Decrypt and return the stored keys.

        Returns an empty dict if the file doesn't exist, the master key isn't
        configured, or decryption fails.  Env vars always win over stored keys
        — the caller is responsible for merging.
        """
        if not self._path.exists():
            return {}

        master_key = self._resolve_master_key()
        if master_key is None:
            return {}

        try:
            AESGCM, _, _ = _get_crypto()
            raw = self._path.read_bytes()
            nonce, ciphertext = raw[:12], raw[12:]
            plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, None)
            self._data = json.loads(plaintext.decode())
            logger.info(
                "Loaded %d keys from encrypted keystore", len(self._data)
            )
            return dict(self._data)
        except Exception:
            logger.warning("Failed to decrypt keystore — bad key or corrupted file")
            return {}

    @staticmethod
    def generate_master_key() -> str:
        """Generate a random 32-byte master key as a hex string."""
        return os.urandom(32).hex()
