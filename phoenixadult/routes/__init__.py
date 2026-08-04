from __future__ import annotations

from html import escape as html_escape
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from phoenixadult.config.env import env
from phoenixadult.utils.helpers.helpers import load_data

THEME_NAMES = ('midnight', 'forest', 'day', 'meadow')

_THEME_TEMPLATE: str = load_data(__file__, 'theme', kind='html')
_NAV_TEMPLATE: str = load_data(__file__, 'nav', kind='html')
_NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ('metadata', 'Metadata', '/metadata'),
    ('people', 'People', '/people'),
    ('logos', 'Logos', '/logos'),
    ('queue', 'Queue', '/queue'),
)
_NAV_DEV_ITEM = ('dev', 'Dev', '/dev')
_NAV_CONFIG_ITEM = ('config', 'Config', '/config')


def render_nav(active: str, username: str = '') -> str:
    items = [*_NAV_ITEMS, *(() if env.is_production else (_NAV_DEV_ITEM,)), _NAV_CONFIG_ITEM]
    links = ''
    for key, label, href in items:
        attrs = ' class="active" aria-current="page"' if key == active else ''
        links += f'<a href="{href}"{attrs}>{label}</a>'
    user_menu = ''
    if username:
        safe = html_escape(username)
        user_menu = f'<a href="/account" class="nav-user" title="Account">{safe}</a><button type="button" class="nav-logout" title="Log out">Log Out</button>'
    return _THEME_TEMPLATE + _NAV_TEMPLATE.replace('__NAV_LINKS__', links).replace('__USER_MENU__', user_menu)


def nav_username(request: Request) -> str:
    user = getattr(request.state, 'user', None)
    return user.username if user is not None else ''


def plex_json(model: BaseModel, status_code: int = 200) -> JSONResponse:
    return JSONResponse(model.model_dump(by_alias=True, exclude_none=True), status_code=status_code)


async def read_json_body(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}
