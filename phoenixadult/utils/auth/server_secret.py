from __future__ import annotations

import base64
import hashlib
import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from filelock import FileLock

from phoenixadult.config.env import env

_SECRET_BYTES = 32
_lock = threading.Lock()
_cache: tuple[str, bytes] | None = None
_fernet_cache: tuple[str, Fernet] | None = None


def secret_path() -> Path:
    return Path(env.state_db_path).resolve().parent / 'secret.key'


def _load_or_create(path: Path) -> bytes:
    if path.exists():
        return base64.urlsafe_b64decode(path.read_text(encoding='ascii').strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + '.lock'):
        if path.exists():
            return base64.urlsafe_b64decode(path.read_text(encoding='ascii').strip())
        raw = os.urandom(_SECRET_BYTES)
        tmp = path.with_suffix('.key.tmp')
        tmp.unlink(missing_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='ascii') as handle:
            handle.write(base64.urlsafe_b64encode(raw).decode('ascii'))
        os.replace(tmp, path)
    return raw


def server_secret() -> bytes:
    global _cache
    key = env.state_db_path
    with _lock:
        if _cache is None or _cache[0] != key:
            _cache = (key, _load_or_create(secret_path()))
        return _cache[1]


def signing_key() -> bytes:
    return hashlib.sha256(b'phoenixadult.sign.v1' + server_secret()).digest()


def fernet() -> Fernet:
    global _fernet_cache
    secret = server_secret()
    key = env.state_db_path
    with _lock:
        if _fernet_cache is None or _fernet_cache[0] != key:
            material = hashlib.sha256(b'phoenixadult.fernet.v1' + secret).digest()
            _fernet_cache = (key, Fernet(base64.urlsafe_b64encode(material)))
        return _fernet_cache[1]


def encrypt(plaintext: str) -> str:
    return fernet().encrypt(plaintext.encode()).decode('ascii')


def decrypt(token: str) -> str | None:
    if not token:
        return None
    try:
        return fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
