from __future__ import annotations

import asyncio
import json
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
from phoenixadult.registry import SITE_DEFINITIONS
from phoenixadult.routes import read_json_body, render_nav
from phoenixadult.utils.auth.env_auth import csrf_guard, env_auth_guard
from phoenixadult.utils.helpers.helpers import load_data
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.logging.session_log import DEFAULT_LINES, LINE_CHOICES, session_log

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])


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


def _build_state() -> dict[str, Any]:
    by_group: dict[str, list[dict[str, Any]]] = {}
    for spec in ENV_CATALOG:
        state = {
            'key': spec.key,
            'label': spec.label,
            'description': spec.description,
            'group': spec.group,
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

    groups = [{'name': name, 'tab': GROUP_TAB.get(name, 'System'), 'vars': vars_} for name, vars_ in sorted(by_group.items(), key=lambda kv: rank(kv[0]))]
    return {'overridesPath': str(OVERRIDES_PATH), 'groups': groups, 'tabs': [tab for tab, _tab_groups in ENV_TABS]}


@router.get('/api/state')
async def api_state() -> JSONResponse:
    return JSONResponse(_build_state())


@router.post('/api/save')
async def api_save(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    updates = body.get('updates')
    if not isinstance(updates, dict):
        return JSONResponse({'error': 'Request body must be { updates: { KEY: value, … } }'}, status_code=400)

    clean: list[tuple[str, str]] = []
    for key, raw in updates.items():
        spec = find_env_var(key)
        if not spec:
            return JSONResponse({'error': f'"{key}" is not an editable variable'}, status_code=400)
        if not isinstance(raw, str):
            return JSONResponse({'error': f'"{key}" value must be a string'}, status_code=400)
        ok, value = normalize_env_value(spec, raw)
        if not ok:
            return JSONResponse({'error': value}, status_code=400)
        clean.append((key, value))

    if clean:

        def _apply() -> None:
            for key, value in clean:
                set_override(key, value)

        await asyncio.to_thread(_apply)
        logger.info('config', f'applied {len(clean)} override(s): {", ".join(k for k, _ in clean)}')
    return JSONResponse(_build_state())


@router.post('/api/reveal')
async def api_reveal(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    key = str(body.get('key') or '')
    spec = next((s for s in ENV_CATALOG if s.key == key), None)
    if spec is None or spec.kind != 'secret':
        return JSONResponse({'error': 'not a secret key'}, status_code=400)
    return JSONResponse({'key': key, 'value': os.environ.get(key, '')})


@router.post('/api/reset')
async def api_reset(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse({'error': 'invalid JSON body'}, status_code=400)
    key = body.get('key') if isinstance(body, dict) else None
    if key is None:
        await asyncio.to_thread(clear_all_overrides)
        logger.info('config', 'cleared all overrides')
        return JSONResponse(_build_state())
    if not isinstance(key, str) or not find_env_var(key):
        return JSONResponse({'error': f'"{key}" is not an editable variable'}, status_code=400)
    await asyncio.to_thread(clear_override, key)
    logger.info('config', f'cleared override: {key}')
    return JSONResponse(_build_state())


_MAIN_PY = Path(__file__).resolve().parent.parent / 'main.py'


@router.post('/api/restart')
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


@router.get('/api/logs')
async def api_logs(since: int = 0, limit: int = DEFAULT_LINES) -> JSONResponse:
    seq, lines, reset = session_log.tail(since, limit)
    return JSONResponse({'seq': seq, 'lines': lines, 'reset': reset, 'choices': list(LINE_CHOICES)})


_CONFIG_HTML: str = load_data(__file__, 'config_ui', kind='html')


def _render_ui(state: dict[str, Any]) -> str:
    state_json = json.dumps(state, ensure_ascii=False).replace('<', '\\u003c')
    return _CONFIG_HTML.replace('__NAV__', render_nav('config')).replace('__STATE_JSON__', state_json)


@router.get('')
@router.get('/')
async def page() -> HTMLResponse:
    return HTMLResponse(_render_ui(_build_state()))
