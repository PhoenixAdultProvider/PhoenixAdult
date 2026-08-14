from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from phoenixadult.config.env import env

THEME_NAMES = ('midnight', 'forest', 'sky', 'meadow')

_NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ('metadata', 'Metadata', '/metadata'),
    ('people', 'People', '/people'),
    ('logos', 'Logos', '/logos'),
    ('queue', 'Queue', '/queue'),
)
_NAV_SEARCHES_ITEM = ('searches', 'Searches', '/searches')
_NAV_DEV_ITEM = ('dev', 'Dev', '/dev')
_NAV_CONFIG_ITEM = ('config', 'Config', '/config')


def nav_items() -> list[tuple[str, str, str]]:
    from phoenixadult.utils.auth.user_auth import is_admin

    searches = (_NAV_SEARCHES_ITEM,) if is_admin() else ()
    return [*_NAV_ITEMS, *searches, *((_NAV_DEV_ITEM,) if env.dev_ui_enabled else ()), _NAV_CONFIG_ITEM]


from phoenixadult.utils.auth.user_auth import is_admin, user_theme  # noqa: E402

_jinja = jinja2.Environment(loader=jinja2.FileSystemLoader(Path(__file__).parent / 'html'), autoescape=True)
_jinja.globals['nav_items'] = nav_items
_jinja.globals['user_theme'] = user_theme
_jinja.globals['is_admin'] = is_admin


def render_page(name: str, **context: Any) -> str:
    return _jinja.get_template(f'{name}.html').render(**context)


def render_nav(active: str, username: str = '') -> str:
    return render_page('nav', active=active, username=username)


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
