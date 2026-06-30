from __future__ import annotations

import json
import os
import signal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config.env import env
from app.config.env_catalog import (
    ENV_CATALOG,
    ENV_GROUP_ORDER,
    EnvVarSpec,
    find_env_var,
    humanize_bytes,
    normalize_env_value,
)
from app.config.env_overrides import (
    OVERRIDES_PATH,
    clear_all_overrides,
    clear_override,
    is_overridden,
    set_override,
)
from app.utils.auth.env_auth import env_auth_guard
from app.utils.logging.logger import logger

router = APIRouter(dependencies=[Depends(env_auth_guard)])


def _display_value(spec: EnvVarSpec) -> str:
    raw = os.environ.get(spec.key, '')
    if spec.kind == 'secret':
        return ''
    return humanize_bytes(raw) if spec.kind == 'bytes' else raw


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
            'options': spec.options,
            'min': spec.min,
            'max': spec.max,
            'preview': spec.preview,
            'value': _display_value(spec),
            'overridden': is_overridden(spec.key),
            'isSet': bool(os.environ.get(spec.key, '')),
        }
        by_group.setdefault(spec.group, []).append(state)

    def rank(name: str) -> int:
        return ENV_GROUP_ORDER.index(name) if name in ENV_GROUP_ORDER else len(ENV_GROUP_ORDER)

    groups = [{'name': name, 'vars': vars_} for name, vars_ in sorted(by_group.items(), key=lambda kv: rank(kv[0]))]
    return {'overridesPath': str(OVERRIDES_PATH), 'groups': groups}


@router.get('/api/state')
async def api_state() -> JSONResponse:
    return JSONResponse(_build_state())


@router.post('/api/save')
async def api_save(request: Request) -> JSONResponse:
    body = await request.json()
    updates = body.get('updates') if isinstance(body, dict) else None
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

    for key, value in clean:
        set_override(key, value)
    if clean:
        logger.info('config', f'applied {len(clean)} override(s): {", ".join(k for k, _ in clean)}')
    return JSONResponse(_build_state())


@router.post('/api/reset')
async def api_reset(request: Request) -> JSONResponse:
    body = await request.json()
    key = body.get('key') if isinstance(body, dict) else None
    if key is None:
        clear_all_overrides()
        logger.info('config', 'cleared all overrides')
        return JSONResponse(_build_state())
    if not isinstance(key, str) or not find_env_var(key):
        return JSONResponse({'error': f'"{key}" is not an editable variable'}, status_code=400)
    clear_override(key)
    logger.info('config', f'cleared override: {key}')
    return JSONResponse(_build_state())


_MAIN_PY = Path(__file__).resolve().parent.parent / 'main.py'  # a file the --reload watcher tracks


@router.post('/api/restart')
async def api_restart() -> JSONResponse:
    if not env.is_production:
        # Dev runs under `uvicorn --reload`. Bumping a watched source file's mtime makes the
        # reloader restart the worker — exactly like editing a file — which re-reads
        # env.overrides.json and applies LOG_LEVEL. The reloader stays up, so it actually
        # comes back (killing the worker would take the reloader down with it).
        try:
            _MAIN_PY.touch()
            logger.warn('config', 'restart requested — bumped app/main.py to trigger the reloader')
            return JSONResponse({'ok': True, 'method': 'reload'})
        except OSError as err:
            logger.warn('config', f'reload trigger failed ({err}); falling back to shutdown')
    # Production / no reloader: exit and rely on the process supervisor to bring us back.
    logger.warn('config', 'restart requested via config UI — signalling shutdown (supervisor must restart)')
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except OSError:
        pass
    return JSONResponse({'ok': True, 'method': 'shutdown'})


_CONFIG_HTML = (Path(__file__).parent / 'html' / 'config_ui.html').read_text(encoding='utf-8')


def _render_ui(state: dict[str, Any]) -> str:
    # Embed the state as a JS object literal; escape `<` so a description can't
    # break out of the <script> block.
    state_json = json.dumps(state, ensure_ascii=False).replace('<', '\\u003c')
    return _CONFIG_HTML.replace('__STATE_JSON__', state_json)


@router.get('')
@router.get('/')
async def page() -> HTMLResponse:
    return HTMLResponse(_render_ui(_build_state()))
