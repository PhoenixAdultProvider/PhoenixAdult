from __future__ import annotations

import os
import signal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.config.env import env
from phoenixadult.config.env_catalog import (
    ENV_CATALOG,
    ENV_GROUP_ORDER,
    ENV_TABS,
    GROUP_TAB,
    GROUP_TITLES,
    TAB_TITLES,
    EnvVarSpec,
    find_env_var,
    humanize_bytes,
    normalize_env_value,
)
from phoenixadult.config.env_overrides import (
    OVERRIDES_PATH,
    clear_all_overrides,
    clear_override,
    is_overridden,
    set_override,
)
from phoenixadult.i18n import gettext
from phoenixadult.registry import SITE_DEFINITIONS
from phoenixadult.routes import THEME_NAMES, nav_username, read_json_body, render_page
from phoenixadult.utils.auth import user_store, user_tokens
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, resolve_user, user_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.logging.session_log import DEFAULT_LINES, LINE_CHOICES, session_log
from phoenixadult.utils.plex import client_hits

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])
_admin = [Depends(admin_auth_guard)]


def _display_value(spec: EnvVarSpec) -> str:
    raw = os.environ.get(spec.key, '')
    if spec.kind == 'secret':
        return ''
    return humanize_bytes(raw) if spec.kind == 'bytes' else raw


def _options_for(spec: EnvVarSpec) -> list[str]:
    if spec.key == 'SEARCH_STRIP_ACTORS':
        names = {s.name for s in SITE_DEFINITIONS}
        names |= {s.sub_group for s in SITE_DEFINITIONS if s.sub_group}
        names |= {s.provider_name for s in SITE_DEFINITIONS if s.provider_name}
        return sorted(names)
    return spec.options


def _current_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, 'user', None)
    return {'username': user.username, 'isAdmin': user.is_admin} if user is not None else {}


def _build_state(user: dict[str, Any] | None = None, has_metadataapi_token: bool = False) -> dict[str, Any]:
    if not (user or {}).get('isAdmin'):
        return {'overridesPath': '', 'groups': [], 'tabs': [], 'user': user or {}, 'metadataapi': {'hasToken': has_metadataapi_token}}

    hidden = {'LOG_REDACT_HOSTS', 'LOG_REDACT_TOKEN'} if env.is_production else set()
    by_group: dict[str, list[dict[str, Any]]] = {}
    for spec in ENV_CATALOG:
        if spec.key in hidden:
            continue
        label_key, description_key = spec.text_keys()
        state = {
            'key': spec.key,
            'label': gettext(label_key),
            'description': gettext(description_key),
            'group': spec.group,
            'optionLabels': spec.option_labels,
            'kind': spec.kind,
            'defaultValue': spec.default_value,
            'requiresRestart': spec.requires_restart,
            'options': _options_for(spec),
            'min': spec.min,
            'max': spec.max,
            'preview': spec.preview,
            'secretItems': spec.secret_items,
            'value': _display_value(spec),
            'overridden': is_overridden(spec.key),
            'isSet': bool(os.environ.get(spec.key, '')),
        }
        by_group.setdefault(spec.group, []).append(state)

    def rank(name: str) -> int:
        return ENV_GROUP_ORDER.index(name) if name in ENV_GROUP_ORDER else len(ENV_GROUP_ORDER)

    ordered = sorted(by_group.items(), key=lambda kv: rank(kv[0]))
    groups = [{'id': name, 'name': gettext(GROUP_TITLES[name]), 'tab': GROUP_TAB.get(name, 'system'), 'vars': vars_} for name, vars_ in ordered]
    return {
        'overridesPath': str(OVERRIDES_PATH),
        'groups': groups,
        'tabs': [{'id': tab, 'title': gettext(TAB_TITLES[tab])} for tab, _tab_groups in ENV_TABS],
        'user': user or {},
        'metadataapi': {'hasToken': has_metadataapi_token},
    }


async def _state_for(request: Request) -> dict[str, Any]:
    user = await resolve_user(request)
    assert user is not None
    has_token = bool(await run_in('store', user_store.metadataapi_token_encrypted, user.id))
    return _build_state(_current_user(request), has_token)


@router.get('/api/state')
async def api_state(request: Request) -> JSONResponse:
    return JSONResponse(await _state_for(request))


@router.post('/api/save', dependencies=_admin)
async def api_save(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    updates = body.get('updates')
    if not isinstance(updates, dict):
        return JSONResponse({'error': gettext('settings_errors.bad_body')}, status_code=400)

    clean: list[tuple[str, str]] = []
    for key, raw in updates.items():
        spec = find_env_var(key)
        if not spec:
            return JSONResponse({'error': gettext('settings_errors.not_editable') % {'key': key}}, status_code=400)
        if not isinstance(raw, str):
            return JSONResponse({'error': gettext('settings_errors.not_string') % {'key': key}}, status_code=400)
        ok, value = normalize_env_value(spec, raw)
        if not ok:
            return JSONResponse({'error': value}, status_code=400)
        clean.append((key, value))

    if clean:

        def _apply() -> None:
            for key, value in clean:
                set_override(key, value)

        await run_in('fs', _apply)
        logger.info('config', f'applied {len(clean)} override(s): {", ".join(k for k, _ in clean)}')
    return JSONResponse(await _state_for(request))


@router.post('/api/reveal', dependencies=_admin)
async def api_reveal(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    key = str(body.get('key') or '')
    spec = next((s for s in ENV_CATALOG if s.key == key), None)
    if spec is None or spec.kind != 'secret':
        return JSONResponse({'error': gettext('settings_errors.not_secret')}, status_code=400)
    return JSONResponse({'key': key, 'value': os.environ.get(key, '')})


@router.post('/api/reset', dependencies=_admin)
async def api_reset(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse({'error': gettext('settings_errors.bad_json')}, status_code=400)
    key = body.get('key') if isinstance(body, dict) else None
    if key is None:
        await run_in('fs', clear_all_overrides)
        logger.info('config', 'cleared all overrides')
        return JSONResponse(await _state_for(request))
    if not isinstance(key, str) or not find_env_var(key):
        return JSONResponse({'error': gettext('settings_errors.not_editable') % {'key': key}}, status_code=400)
    await run_in('fs', clear_override, key)
    logger.info('config', f'cleared override: {key}')
    return JSONResponse(await _state_for(request))


_MAIN_PY = Path(__file__).resolve().parent.parent / 'main.py'


@router.post('/api/restart', dependencies=_admin)
async def api_restart() -> JSONResponse:
    if not env.is_production:
        try:
            _MAIN_PY.touch()
            logger.warn('config', 'restart requested — bumped app/main.py to trigger the reloader')
            return JSONResponse({'ok': True, 'method': 'reload'})
        except OSError as err:
            logger.warn('config', f'reload trigger failed ({err}); falling back to shutdown')
    logger.warn('config', 'restart requested via config UI — signalling shutdown (supervisor must restart)')
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except OSError:
        pass
    return JSONResponse({'ok': True, 'method': 'shutdown'})


@router.get('/api/logs', dependencies=_admin)
async def api_logs(since: int = 0, limit: int = DEFAULT_LINES) -> JSONResponse:
    seq, lines, reset = session_log.tail(since, limit)
    return JSONResponse({'seq': seq, 'lines': lines, 'reset': reset, 'choices': list(LINE_CHOICES)})


@router.post('/api/theme')
async def api_theme(request: Request) -> JSONResponse:
    user = await resolve_user(request)
    assert user is not None
    body = await read_json_body(request)
    dark = str(body.get('dark') or '')
    light = str(body.get('light') or '')
    if (dark and dark not in THEME_NAMES) or (light and light not in THEME_NAMES):
        return JSONResponse({'error': gettext('settings_errors.unknown_theme')}, status_code=400)
    await run_in('store', user_store.set_theme, user.id, dark, light)
    return JSONResponse({'ok': True})


@router.post('/api/metadataapi')
async def api_metadataapi(request: Request) -> JSONResponse:
    user = await resolve_user(request)
    assert user is not None
    body = await read_json_body(request)
    token = str(body.get('token') or '').strip()
    await run_in('store', user_tokens.save_token_for_user, user.id, token)
    logger.info('config', f'{user.username} {"set" if token else "cleared"} their MetadataAPI token')
    return JSONResponse({'hasToken': bool(token)})


@router.get('/api/clients', dependencies=_admin)
async def api_clients() -> JSONResponse:
    return JSONResponse({'clients': await run_in('store', client_hits.list_hits)})


def _render_ui(state: dict[str, Any], username: str) -> str:
    return render_page('config_ui', active='config', username=username, state=state)


@router.get('')
@router.get('/')
async def page(request: Request) -> HTMLResponse:
    return HTMLResponse(_render_ui(await _state_for(request), nav_username(request)))
