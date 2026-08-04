from __future__ import annotations

from pathlib import Path

import pytest

from phoenixadult.utils.auth import server_secret


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    server_secret._cache = None
    server_secret._fernet_cache = None


def test_secret_is_created_and_stable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    assert not server_secret.secret_path().exists()
    first = server_secret.server_secret()
    assert server_secret.secret_path().exists()
    assert len(first) == 32
    assert server_secret.server_secret() == first


def test_secret_follows_state_db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'a' / 'state.db'))
    (tmp_path / 'a').mkdir()
    a = server_secret.server_secret()
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'b' / 'state.db'))
    (tmp_path / 'b').mkdir()
    b = server_secret.server_secret()
    assert a != b


def test_derivations_are_domain_separated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    assert server_secret.signing_key() != server_secret.server_secret()
    assert len(server_secret.signing_key()) == 32


def test_encrypt_decrypt_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    token = server_secret.encrypt('plex-token-xyz')
    assert token != 'plex-token-xyz'
    assert server_secret.decrypt(token) == 'plex-token-xyz'


def test_decrypt_bad_ciphertext_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    assert server_secret.decrypt('not-a-valid-token') is None
    assert server_secret.decrypt('') is None
