from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from phoenixadult import __version__
from phoenixadult.config.env import env
from phoenixadult.i18n import N_, gettext, ngettext, strings
from phoenixadult.routes.assets import asset_version
from phoenixadult.utils.auth.passwords import PASSWORD_RULE
from phoenixadult.utils.auth.theme_view import THEMES_BY_MODE, theme_view, user_theme
from phoenixadult.utils.auth.user_auth import is_admin
from phoenixadult.utils.http.connectivity import network_down

THEME_NAMES = tuple(name for names in THEMES_BY_MODE.values() for name in names)
FONT_NAMES = ('archivo-latin', 'jetbrains-mono-latin')

_NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ('metadata', N_('nav.metadata'), '/metadata'),
    ('people', N_('nav.people'), '/people'),
    ('logos', N_('nav.logos'), '/logos'),
    ('queue', N_('nav.queue'), '/queue'),
)
_NAV_SEARCHES_ITEM = ('searches', N_('nav.searches'), '/searches')
_NAV_DEV_ITEM = ('dev', N_('nav.dev'), '/dev')
_NAV_CONFIG_ITEM = ('config', N_('nav.config'), '/config')


def nav_items() -> list[tuple[str, str, str]]:
    searches = (_NAV_SEARCHES_ITEM,) if is_admin() else ()
    return [*_NAV_ITEMS, *searches, *((_NAV_DEV_ITEM,) if env.dev_ui_enabled else ()), _NAV_CONFIG_ITEM]


def ui_language() -> str:
    return env.ui_language


def app_version() -> str:
    return __version__


def theme_version(name: str) -> str:
    return asset_version(Path(__file__).parent / 'html' / 'themes' / f'{name}.css')


def theme_versions() -> dict[str, str]:
    return {name: theme_version(name) for name in THEME_NAMES}


_jinja = jinja2.Environment(
    loader=jinja2.FileSystemLoader(Path(__file__).parent / 'html'), autoescape=True, auto_reload=not env.is_production, extensions=['jinja2.ext.i18n']
)
_jinja.install_gettext_callables(gettext, ngettext, newstyle=True)  # type: ignore[attr-defined]
_jinja.globals['ui_language'] = ui_language
_jinja.globals['strings'] = strings
_jinja.globals['nav_items'] = nav_items
_jinja.globals['network_down'] = network_down
_jinja.globals['user_theme'] = user_theme
_jinja.globals['theme_view'] = theme_view
_jinja.globals['theme_version'] = theme_version
_jinja.globals['theme_versions'] = theme_versions
_jinja.globals['is_admin'] = is_admin
_jinja.globals['app_version'] = app_version
_jinja.globals['password_rule'] = PASSWORD_RULE


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
