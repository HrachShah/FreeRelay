"""Tests for SessionAffinity sticky-session routing."""

from __future__ import annotations

import time

from freerelay.core.routing.session_affinity import SessionAffinity


def test_get_unknown_returns_none() -> None:
    sa = SessionAffinity()
    assert sa.get("no-such-id") is None


def test_pin_and_get() -> None:
    sa = SessionAffinity()
    sa.pin("sess-1", "groq")
    assert sa.get("sess-1") == "groq"


def test_pin_overwrites() -> None:
    sa = SessionAffinity()
    sa.pin("sess-1", "groq")
    sa.pin("sess-1", "mistral")
    assert sa.get("sess-1") == "mistral"


def test_clear_removes_entry() -> None:
    sa = SessionAffinity()
    sa.pin("sess-1", "groq")
    sa.clear("sess-1")
    assert sa.get("sess-1") is None


def test_clear_nonexistent_is_noop() -> None:
    sa = SessionAffinity()
    sa.clear("ghost")  # should not raise


def test_ttl_expiry() -> None:
    sa = SessionAffinity(ttl_secs=0.05)
    sa.pin("sess-1", "groq")
    assert sa.get("sess-1") == "groq"
    time.sleep(0.1)
    assert sa.get("sess-1") is None


def test_evict_expired() -> None:
    sa = SessionAffinity(ttl_secs=0.05)
    sa.pin("s1", "groq")
    sa.pin("s2", "mistral")
    time.sleep(0.1)
    sa.pin("s3", "google")  # not expired
    removed = sa.evict_expired()
    assert removed == 2
    assert len(sa) == 1


def test_derive_from_header() -> None:
    sid = SessionAffinity.derive_session_id(header="my-header-id")
    assert sid == "my-header-id"


def test_derive_from_user_field() -> None:
    sid = SessionAffinity.derive_session_id(user_field="user-123")
    assert sid == "user-123"


def test_derive_from_messages() -> None:
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    sid = SessionAffinity.derive_session_id(messages=msgs)
    assert sid is not None
    assert sid.startswith("conv-")
    # Stable across calls
    sid2 = SessionAffinity.derive_session_id(messages=msgs)
    assert sid == sid2


def test_derive_single_message_returns_none() -> None:
    msgs = [{"role": "user", "content": "hi"}]
    sid = SessionAffinity.derive_session_id(messages=msgs)
    assert sid is None


def test_derive_no_info_returns_none() -> None:
    sid = SessionAffinity.derive_session_id()
    assert sid is None
