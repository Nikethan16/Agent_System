"""Tests for at-rest encryption of the UI-managed key store (core/keypool.py)."""
import os
import json
import tempfile

import pytest

from core import keypool


@pytest.fixture()
def store(monkeypatch):
    d = tempfile.mkdtemp()
    path = os.path.join(d, "keys.json")
    monkeypatch.setattr(keypool, "_STORE", path)
    return path


def test_plaintext_when_no_secret(store, monkeypatch):
    monkeypatch.delenv("AGENT_SECRET_KEY", raising=False)
    keypool._save_store({"gemini": ["abc12345"]})
    on_disk = open(store).read()
    assert "abc12345" in on_disk          # plaintext (legacy/back-compat)
    assert keypool._load_store() == {"gemini": ["abc12345"]}


def test_encrypted_when_secret_set(store, monkeypatch):
    monkeypatch.setenv("AGENT_SECRET_KEY", "super-secret-passphrase")
    keypool._save_store({"gemini": ["topsecretkey99"]})
    on_disk = open(store).read()
    assert "topsecretkey99" not in on_disk   # the raw key is NOT on disk
    assert '"_enc"' in on_disk
    # round-trips with the same secret
    assert keypool._load_store() == {"gemini": ["topsecretkey99"]}


def test_legacy_plaintext_still_readable_with_secret(store, monkeypatch):
    # An existing plaintext store written before encryption was enabled.
    with open(store, "w") as f:
        json.dump({"openrouter": ["legacykey123"]}, f)
    monkeypatch.setenv("AGENT_SECRET_KEY", "s3cret")
    assert keypool._load_store() == {"openrouter": ["legacykey123"]}


def test_wrong_secret_reads_empty_not_crash(store, monkeypatch):
    monkeypatch.setenv("AGENT_SECRET_KEY", "right-secret")
    keypool._save_store({"gemini": ["k1234567"]})
    monkeypatch.setenv("AGENT_SECRET_KEY", "wrong-secret")
    assert keypool._load_store() == {}      # unreadable, but no crash


def test_refuse_overwrite_when_locked(store, monkeypatch):
    # Save under one secret, then rotate: the store is now undecryptable, so a save
    # must REFUSE rather than silently destroy the prior keys.
    monkeypatch.setenv("AGENT_SECRET_KEY", "original")
    keypool._save_store({"gemini": ["origkey123"]})
    monkeypatch.setenv("AGENT_SECRET_KEY", "rotated")
    assert keypool._store_locked() is True
    import pytest as _pytest
    with _pytest.raises(RuntimeError):
        keypool._save_store({"gemini": ["newkey456"]})
    # restoring the original secret makes it readable again (data intact)
    monkeypatch.setenv("AGENT_SECRET_KEY", "original")
    assert keypool._load_store() == {"gemini": ["origkey123"]}


def test_atomic_write_leaves_no_tmp(store, monkeypatch):
    monkeypatch.delenv("AGENT_SECRET_KEY", raising=False)
    keypool._save_store({"openrouter": ["abcdef12"]})
    assert not os.path.exists(store + ".tmp")
    assert keypool._load_store() == {"openrouter": ["abcdef12"]}
