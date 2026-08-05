from __future__ import annotations

from contextvars import ContextVar

from cachetools import TTLCache

from phoenixadult.utils.auth.server_secret import decrypt, encrypt

current_metadataapi_token: ContextVar[str | None] = ContextVar('metadataapi_token', default=None)

_FALLBACK_TTL = 60.0
_fallback_cache: TTLCache[str, str] = TTLCache(maxsize=4, ttl=_FALLBACK_TTL)


def metadataapi_token() -> str | None:
    token = current_metadataapi_token.get()
    if token:
        return token
    return _fallback_token() or None


def _fallback_token() -> str:
    from phoenixadult.utils.auth import user_store

    hit = _fallback_cache.get('token')
    if hit is not None:
        return hit
    try:
        token = decrypt(user_store.first_metadataapi_token_encrypted()) or ''
    except Exception:  # noqa: BLE001 - no DB yet (first boot) means no token
        token = ''
    _fallback_cache['token'] = token
    return token


def clear_fallback_cache() -> None:
    _fallback_cache.clear()


def token_for_user(user_id: int) -> str | None:
    from phoenixadult.utils.auth import user_store

    return decrypt(user_store.metadataapi_token_encrypted(user_id))


def save_token_for_user(user_id: int, token: str) -> None:
    from phoenixadult.utils.auth import user_store

    user_store.set_metadataapi_token(user_id, encrypt(token) if token else '')
    clear_fallback_cache()


def migrate_env_token() -> bool:
    import os

    from phoenixadult.config.env_overrides import clear_override
    from phoenixadult.utils.auth import user_store

    token = (os.environ.get('METADATAAPI_TOKEN') or '').strip()
    if not token or user_store.any_metadataapi_token():
        return False
    owner = user_store.oldest_admin_id()
    if owner is None:
        return False
    save_token_for_user(owner, token)
    clear_override('METADATAAPI_TOKEN')
    return True
