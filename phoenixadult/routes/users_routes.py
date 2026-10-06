from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from phoenixadult.i18n import gettext
from phoenixadult.routes import read_json_body
from phoenixadult.utils.auth import user_store
from phoenixadult.utils.auth.passwords import password_error
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, resolve_user, user_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.logging.logger import logger


def _user_id(body: dict[str, Any]) -> int | None:
    try:
        return int(body.get('id') or 0)
    except (TypeError, ValueError):
        return None


router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(admin_auth_guard), Depends(csrf_guard)])


@router.get('/api/list')
async def list_users() -> JSONResponse:
    return JSONResponse({'users': await run_in('store', user_store.list_users)})


@router.post('/api/create')
async def create_user(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    username = str(body.get('username') or '').strip()
    password = str(body.get('password') or '')
    if len(username) < 3:
        return JSONResponse({'error': gettext('users.username_too_short')}, status_code=400)
    if (problem := password_error(password)) is not None:
        return JSONResponse({'error': gettext(problem)}, status_code=400)
    try:
        user_id = await run_in('store', user_store.create_user, username, password, bool(body.get('isAdmin')))
    except sqlite3.IntegrityError:
        return JSONResponse({'error': gettext('users.username_taken')}, status_code=409)
    logger.info('users', f'created user {username}')
    return JSONResponse({'id': user_id})


@router.post('/api/delete')
async def delete_user(request: Request) -> JSONResponse:
    user_id = _user_id(await read_json_body(request))
    if user_id is None:
        return JSONResponse({'error': gettext('users.bad_id')}, status_code=400)
    target = await run_in('store', user_store.get_by_id, user_id)
    if target is None:
        return JSONResponse({'error': gettext('users.not_found')}, status_code=404)
    if not await run_in('store', user_store.delete_user_keeping_an_admin, user_id):
        return JSONResponse({'error': gettext('users.last_admin_delete')}, status_code=409)
    logger.info('users', f'deleted user {target.username}')
    return JSONResponse({'ok': True})


@router.post('/api/password')
async def reset_password(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    user_id = _user_id(body)
    if user_id is None:
        return JSONResponse({'error': gettext('users.bad_id')}, status_code=400)
    password = str(body.get('password') or '')
    if (problem := password_error(password)) is not None:
        return JSONResponse({'error': gettext(problem)}, status_code=400)
    target = await run_in('store', user_store.get_by_id, user_id)
    if target is None:
        return JSONResponse({'error': gettext('users.not_found')}, status_code=404)
    await run_in('store', user_store.set_password, user_id, password, None)
    logger.info('users', f'reset the password for {target.username}')
    return JSONResponse({'ok': True})


@router.post('/api/admin')
async def set_admin(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    user_id = _user_id(body)
    if user_id is None:
        return JSONResponse({'error': gettext('users.bad_id')}, status_code=400)
    is_admin = bool(body.get('isAdmin'))
    target = await run_in('store', user_store.get_by_id, user_id)
    if target is None:
        return JSONResponse({'error': gettext('users.not_found')}, status_code=404)
    caller = await resolve_user(request)
    assert caller is not None
    if is_admin:
        await run_in('store', user_store.set_admin, user_id, True)
    elif not await run_in('store', user_store.demote_keeping_an_admin, user_id):
        return JSONResponse({'error': gettext('users.last_admin_demote')}, status_code=409)
    logger.info('users', f'{caller.username} set admin={is_admin} on {target.username}')
    return JSONResponse({'ok': True})
