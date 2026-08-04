from __future__ import annotations

from phoenixadult.utils.auth import passwords


def test_hash_and_verify_roundtrip() -> None:
    h = passwords.hash_password('correct horse battery staple')
    assert h.startswith('$argon2id$')
    assert passwords.verify_password('correct horse battery staple', h) is True
    assert passwords.verify_password('wrong', h) is False


def test_verify_rejects_garbage_without_raising() -> None:
    assert passwords.verify_password('x', 'not-a-hash') is False
    assert passwords.verify_password('x', '') is False


def test_each_hash_is_salted_differently() -> None:
    assert passwords.hash_password('same') != passwords.hash_password('same')


def test_api_key_shape_and_hash() -> None:
    plain, key_hash, hint = passwords.generate_api_key()
    assert plain.startswith('pa_')
    assert passwords.hash_token(plain) == key_hash
    assert hint.startswith('pa_') and hint.endswith(plain[-4:])
    assert plain != passwords.generate_api_key()[0]


def test_session_token_hash_matches() -> None:
    plain, token_hash = passwords.generate_session_token()
    assert passwords.hash_token(plain) == token_hash
