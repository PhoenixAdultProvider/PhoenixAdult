from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_API_KEY_PREFIX = 'pa_'
_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8
PASSWORD_RULE = 'Password needs 8+ characters with an uppercase letter, a number, and a special character.'


def password_error(password: str) -> str | None:
    ok = (
        len(password) >= MIN_PASSWORD_LENGTH
        and any(c.isupper() for c in password)
        and any(c.isdigit() for c in password)
        and any(not c.isalnum() for c in password)
    )
    return None if ok else PASSWORD_RULE


def password_strength(password: str) -> dict[str, object]:
    from zxcvbn import zxcvbn

    if not password:
        return {'score': 0, 'feedback': ''}
    result = zxcvbn(password[:72])
    feedback = result.get('feedback') or {}
    suggestions = feedback.get('suggestions') or []
    return {'score': int(result['score']), 'feedback': str(feedback.get('warning') or (suggestions[0] if suggestions else ''))}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored: str) -> bool:
    try:
        return _hasher.verify(stored, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored)
    except InvalidHashError:
        return True


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    plain = _API_KEY_PREFIX + secrets.token_urlsafe(32)
    return plain, hash_token(plain), f'{plain[:6]}…{plain[-4:]}'


def generate_session_token() -> tuple[str, str]:
    plain = secrets.token_urlsafe(32)
    return plain, hash_token(plain)
