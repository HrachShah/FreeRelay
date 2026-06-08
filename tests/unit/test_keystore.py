"""Tests for KeyStore AES-256-GCM encrypted key storage."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _has_cryptography() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        return True
    except (ImportError, ModuleNotFoundError):
        return False


skip_if_no_crypto = pytest.mark.skipif(
    not _has_cryptography(), reason="cryptography package not installed"
)


@skip_if_no_crypto
def test_save_and_load_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from freerelay.shared.security.keystore import KeyStore

    master_key = os.urandom(32).hex()
    monkeypatch.setenv("FREERELAY_MASTER_KEY", master_key)
    monkeypatch.delenv("FREERELAY_MASTER_PASSPHRASE", raising=False)

    store = KeyStore(path=tmp_path / "keys.enc", salt_path=tmp_path / "keys.salt")
    store.set("GROQ_API_KEY", "gsk_test_value")
    store.set("MISTRAL_API_KEY", "mistral_test_value")
    assert store.save()

    store2 = KeyStore(path=tmp_path / "keys.enc", salt_path=tmp_path / "keys.salt")
    loaded = store2.load()
    assert loaded["GROQ_API_KEY"] == "gsk_test_value"
    assert loaded["MISTRAL_API_KEY"] == "mistral_test_value"


@skip_if_no_crypto
def test_wrong_key_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from freerelay.shared.security.keystore import KeyStore

    good_key = os.urandom(32).hex()
    monkeypatch.setenv("FREERELAY_MASTER_KEY", good_key)

    store = KeyStore(path=tmp_path / "keys.enc", salt_path=tmp_path / "keys.salt")
    store.set("SOME_KEY", "some_value")
    store.save()

    bad_key = os.urandom(32).hex()
    monkeypatch.setenv("FREERELAY_MASTER_KEY", bad_key)

    store2 = KeyStore(path=tmp_path / "keys.enc", salt_path=tmp_path / "keys.salt")
    loaded = store2.load()
    assert loaded == {}


@skip_if_no_crypto
def test_no_master_key_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from freerelay.shared.security.keystore import KeyStore

    monkeypatch.delenv("FREERELAY_MASTER_KEY", raising=False)
    monkeypatch.delenv("FREERELAY_MASTER_PASSPHRASE", raising=False)

    store = KeyStore(path=tmp_path / "keys.enc", salt_path=tmp_path / "keys.salt")
    loaded = store.load()
    assert loaded == {}


@skip_if_no_crypto
def test_list_masked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from freerelay.shared.security.keystore import KeyStore

    master_key = os.urandom(32).hex()
    monkeypatch.setenv("FREERELAY_MASTER_KEY", master_key)

    store = KeyStore(path=tmp_path / "keys.enc", salt_path=tmp_path / "keys.salt")
    store.set("GROQ_API_KEY", "gsk_abcdefgh")
    masked = store.list_masked()
    assert "GROQ_API_KEY" in masked
    assert "gsk_" in masked["GROQ_API_KEY"]
    assert "abcd" not in masked["GROQ_API_KEY"][4:]  # middle is hidden


@skip_if_no_crypto
def test_remove_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from freerelay.shared.security.keystore import KeyStore

    master_key = os.urandom(32).hex()
    monkeypatch.setenv("FREERELAY_MASTER_KEY", master_key)

    store = KeyStore(path=tmp_path / "keys.enc", salt_path=tmp_path / "keys.salt")
    store.set("KEY_A", "val_a")
    store.set("KEY_B", "val_b")
    assert store.remove("KEY_A")
    assert not store.remove("KEY_NONEXISTENT")
    assert "KEY_A" not in store.list_masked()


@skip_if_no_crypto
def test_generate_master_key_is_64_hex_chars() -> None:
    from freerelay.shared.security.keystore import KeyStore

    key = KeyStore.generate_master_key()
    assert len(key) == 64
    int(key, 16)  # should not raise
