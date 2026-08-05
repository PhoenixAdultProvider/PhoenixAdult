from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.routes import nav_username, read_json_body, render_page
from phoenixadult.utils.auth import rate_limit, user_store
from phoenixadult.utils.auth.passwords import hash_token, password_error, password_strength
from phoenixadult.utils.auth.user_auth import SESSION_COOKIE, csrf_guard, resolve_user, user_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.logging.logger import logger

public_router = APIRouter()
router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else 'unknown'


def _is_secure(request: Request) -> bool:
    return request.headers.get('x-forwarded-proto', request.url.scheme) == 'https'


def _set_session_cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite='lax', secure=_is_secure(request), path='/', max_age=user_store.SESSION_TTL_SECONDS)


def _safe_next(raw: str) -> str:
    if raw.startswith('/') and not raw.startswith('//'):
        return raw
    return '/config'


async def _seeded() -> bool:
    return await run_in('store', user_store.user_count) > 0


@public_router.get('/login', response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if not await _seeded():
        return HTMLResponse(status_code=302, headers={'Location': '/setup'})
    return HTMLResponse(_login_html(request.query_params.get('next', '')))


def _login_html(next_path: str, error: str = '') -> str:
    return render_page('login', subtitle='Enter your credentials to continue.', next=_safe_next(next_path), error=error)


async def _credentials(request: Request) -> tuple[dict[str, str], bool]:
    if 'application/x-www-form-urlencoded' in (request.headers.get('content-type') or ''):
        posted = parse_qs((await request.body()).decode('utf-8', 'replace'), keep_blank_values=True)
        return {k: (posted.get(k) or [''])[0] for k in ('username', 'password', 'next')}, True
    body = await read_json_body(request)
    return {k: str(body.get(k) or '') for k in ('username', 'password', 'next')}, False


@public_router.post('/login')
async def login(request: Request) -> Response:
    fields, from_form = await _credentials(request)
    username, password = fields['username'].strip(), fields['password']

    def fail(message: str, status: int, headers: dict[str, str] | None = None) -> Response:
        if from_form:
            return HTMLResponse(_login_html(fields['next'], message), status_code=status, headers=headers)
        return JSONResponse({'error': message}, status_code=status, headers=headers)

    scope, key = 'login', f'{_client_ip(request)}|{username.casefold()}'
    wait = rate_limit.retry_after(scope, key)
    if wait > 0:
        return fail(f'Too many attempts — wait {int(wait) + 1}s.', 429, {'Retry-After': str(int(wait) + 1)})
    if not username or not password:
        return fail('Username and password are required.', 400)
    user = await run_in('store', user_store.verify_login, username, password)
    if user is None:
        rate_limit.record_failure(scope, key)
        return fail('Invalid username or password.', 401)
    rate_limit.record_success(scope, key)
    token = await run_in('store', user_store.create_session, user.id, request.headers.get('user-agent', ''))
    target = _safe_next(fields['next'])
    response: Response = Response(status_code=303, headers={'Location': target}) if from_form else JSONResponse({'redirect': target})
    _set_session_cookie(response, token, request)
    logger.info('auth', f'login: {user.username}')
    return response


@public_router.post('/api/password-strength')
async def password_strength_api(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    return JSONResponse(password_strength(str(body.get('password') or '')))


@public_router.get('/setup', response_class=HTMLResponse)
async def setup_page(request: Request) -> HTMLResponse:
    if await _seeded():
        return HTMLResponse('Setup already complete.', status_code=404)
    return HTMLResponse(render_page('setup', error=''))


@public_router.post('/setup')
async def setup(request: Request) -> Response:
    fields, from_form = await _credentials(request)
    username, password = fields['username'].strip(), fields['password']

    def fail(message: str, status: int, headers: dict[str, str] | None = None) -> Response:
        if from_form:
            return HTMLResponse(render_page('setup', error=message), status_code=status, headers=headers)
        return JSONResponse({'error': message}, status_code=status, headers=headers)

    wait = rate_limit.retry_after('setup', _client_ip(request))
    if wait > 0:
        return fail(f'Too many attempts — wait {int(wait) + 1}s.', 429, {'Retry-After': str(int(wait) + 1)})
    if len(username) < 3:
        return fail('Username must be at least 3 characters.', 400)
    if (problem := password_error(password)) is not None:
        return fail(problem, 400)

    def _create() -> int | None:
        if user_store.user_count() > 0:
            return None
        return user_store.create_user(username, password, is_admin=True)

    user_id = await run_in('store', _create)
    if user_id is None:
        rate_limit.record_failure('setup', _client_ip(request))
        return fail('An account already exists.', 409)
    token = await run_in('store', user_store.create_session, user_id, request.headers.get('user-agent', ''))
    response: Response = Response(status_code=303, headers={'Location': '/config'}) if from_form else JSONResponse({'redirect': '/config'})
    _set_session_cookie(response, token, request)
    logger.info('auth', f'setup: created admin {username}')
    return response


@router.post('/logout')
async def logout(request: Request) -> Response:
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        await run_in('store', user_store.delete_session, hash_token(cookie))
    response = JSONResponse({'ok': True})
    response.delete_cookie(SESSION_COOKIE, path='/')
    return response


@router.get('/account', response_class=HTMLResponse)
async def account_page(request: Request) -> HTMLResponse:
    user = await resolve_user(request)
    assert user is not None
    row = await run_in('store', user_store.get_by_id, user.id)
    hint = (row.api_key_hint if row else '') or 'No key generated yet.'
    return HTMLResponse(render_page('account', active='', username=nav_username(request), api_key_hint=hint))


@router.post('/account/api/password')
async def change_password(request: Request) -> JSONResponse:
    user = await resolve_user(request)
    assert user is not None
    body = await read_json_body(request)
    current = str(body.get('current') or '')
    new = str(body.get('new') or '')
    if (problem := password_error(new)) is not None:
        return JSONResponse({'error': problem}, status_code=400)
    verified = await run_in('store', user_store.verify_login, user.username, current)
    if verified is None:
        return JSONResponse({'error': 'Current password is incorrect.'}, status_code=403)
    keep_hash = hash_token(request.cookies.get(SESSION_COOKIE, '')) if user.via == 'session' else None
    await run_in('store', user_store.set_password, user.id, new, keep_hash)
    logger.info('auth', f'password changed: {user.username}')
    return JSONResponse({'ok': True})


@router.post('/account/api/key/regenerate')
async def regenerate_key(request: Request) -> JSONResponse:
    user = await resolve_user(request)
    assert user is not None
    plain = await run_in('store', user_store.regenerate_api_key, user.id)
    return JSONResponse({'key': plain, 'hint': f'{plain[:6]}…{plain[-4:]}'})


@router.get('/account/api/sessions')
async def list_sessions(request: Request) -> JSONResponse:
    user = await resolve_user(request)
    assert user is not None
    current = hash_token(request.cookies.get(SESSION_COOKIE, '')) if user.via == 'session' else ''
    sessions = await run_in('store', user_store.sessions_for_user, user.id, current)
    return JSONResponse({'sessions': sessions})


@router.post('/account/api/sessions/revoke')
async def revoke_session(request: Request) -> JSONResponse:
    user = await resolve_user(request)
    assert user is not None
    body = await read_json_body(request)
    token_hash = str(body.get('tokenHash') or '')
    await run_in('store', user_store.revoke_session, user.id, token_hash)
    return JSONResponse({'ok': True})
