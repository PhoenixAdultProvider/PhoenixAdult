from __future__ import annotations

from contextvars import ContextVar

from fastapi import Request

THEMES_BY_MODE: dict[str, tuple[str, ...]] = {'dark': ('midnight', 'forest'), 'light': ('sky', 'meadow')}
VIEW_COOKIE = 'pa_view'

current_theme_view: ContextVar[tuple[str, str] | None] = ContextVar('current_theme_view', default=None)


def parse_view(raw: str | None) -> tuple[str, str] | None:
    if not raw or '.' not in raw:
        return None
    mode, _, name = raw.partition('.')
    if mode not in THEMES_BY_MODE or name not in THEMES_BY_MODE[mode]:
        return None
    return mode, name


def adopt(request: Request) -> None:
    current_theme_view.set(parse_view(request.cookies.get(VIEW_COOKIE)))


def _name_for(mode: str, saved: str | None, cookie: tuple[str, str] | None) -> str:
    allowed = THEMES_BY_MODE[mode]
    if saved in allowed:
        return str(saved)
    if cookie and cookie[0] == mode and cookie[1] in allowed:
        return cookie[1]
    return allowed[0]


def theme_view() -> dict[str, str]:
    from phoenixadult.utils.auth.user_auth import user_theme

    saved = user_theme()
    cookie = current_theme_view.get()
    dark = _name_for('dark', saved.get('dark'), cookie)
    light = _name_for('light', saved.get('light'), cookie)
    mode = cookie[0] if cookie else ''
    return {'mode': mode, 'name': dark if mode == 'dark' else light, 'dark': dark, 'light': light}
