from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from phoenixadult.routes import read_json_body
from phoenixadult.utils.auth import user_store
from phoenixadult.utils.auth.passwords import password_error
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, resolve_user, user_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.logging.logger import logger

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
        return JSONResponse({'error': 'Username must be at least 3 characters.'}, status_code=400)
    if (problem := password_error(password)) is not None:
        return JSONResponse({'error': problem}, status_code=400)
    try:
        user_id = await run_in('store', user_store.create_user, username, password, bool(body.get('isAdmin')))
    except Exception:  # noqa: BLE001 - unique username collision
        return JSONResponse({'error': 'That username is taken.'}, status_code=409)
    logger.info('users', f'created user {username}')
    return JSONResponse({'id': user_id})


@router.post('/api/delete')
async def delete_user(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    user_id = int(body.get('id') or 0)
    target = await run_in('store', user_store.get_by_id, user_id)
    if target is None:
        return JSONResponse({'error': 'No such user'}, status_code=404)
    if target.is_admin and await run_in('store', user_store.admin_count) <= 1:
        return JSONResponse({'error': 'The last admin cannot be deleted.'}, status_code=409)
    await run_in('store', user_store.delete_user, user_id)
    logger.info('users', f'deleted user {target.username}')
    return JSONResponse({'ok': True})


@router.post('/api/password')
async def reset_password(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    user_id = int(body.get('id') or 0)
    password = str(body.get('password') or '')
    if (problem := password_error(password)) is not None:
        return JSONResponse({'error': problem}, status_code=400)
    target = await run_in('store', user_store.get_by_id, user_id)
    if target is None:
        return JSONResponse({'error': 'No such user'}, status_code=404)
    await run_in('store', user_store.set_password, user_id, password, None)
    logger.info('users', f'reset the password for {target.username}')
    return JSONResponse({'ok': True})


@router.post('/api/admin')
async def set_admin(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    user_id = int(body.get('id') or 0)
    is_admin = bool(body.get('isAdmin'))
    target = await run_in('store', user_store.get_by_id, user_id)
    if target is None:
        return JSONResponse({'error': 'No such user'}, status_code=404)
    if not is_admin and target.is_admin and await run_in('store', user_store.admin_count) <= 1:
        return JSONResponse({'error': 'The last admin cannot be demoted.'}, status_code=409)
    caller = await resolve_user(request)
    assert caller is not None
    await run_in('store', user_store.set_admin, user_id, is_admin)
    logger.info('users', f'{caller.username} set admin={is_admin} on {target.username}')
    return JSONResponse({'ok': True})
