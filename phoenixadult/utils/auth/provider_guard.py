from __future__ import annotations

from fastapi import HTTPException, Request

from phoenixadult.config.env import env
from phoenixadult.services.plex_connections import allowed_client_union
from phoenixadult.utils.auth import user_store
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.logging.request_trace import trace_request
from phoenixadult.utils.plex import daily_quota

PLEX_SERVER_UA = 'plexmediaserver'
_TOKEN_PARAMS = ('apikey', 'token')


def presented_url_token(request: Request) -> str:
    for name in _TOKEN_PARAMS:
        value = (request.query_params.get(name) or '').strip()
        if value:
            return value
    return ''


def _refuse(request: Request, status: int, note: str) -> HTTPException:
    origin = request.client.host if request.client else 'an unknown address'
    logger.warn('auth', f'refused {request.method} {request.url.path} from {origin} - {note}.')
    if status == 429:
        wait = daily_quota.seconds_until_midnight()
        return HTTPException(status_code=429, detail='Daily request limit reached', headers={'Retry-After': str(wait)})
    return HTTPException(status_code=404, detail='Not found')


async def _over_quota(scope: str, key: str, cap: int) -> bool:
    return await run_in('store', daily_quota.bump, scope, key) > cap


async def provider_guard(request: Request) -> None:
    trace_request('provider', request)

    agent = request.headers.get('user-agent') or ''
    if PLEX_SERVER_UA not in agent.lower():
        raise _refuse(request, 404, f'user-agent "{agent or "(none)"}" is not a Plex Media Server, and only Plex may reach the provider mount')

    token = presented_url_token(request)
    user = await run_in('store', user_store.user_for_api_key, token) if token else None
    if env.token_based_auth:
        if not token:
            raise _refuse(request, 404, 'the URL carried no ?apikey=, and TOKEN_BASED_AUTH requires one')
        if user is None:
            raise _refuse(request, 404, 'the ?apikey= on the URL does not match any user API key')

    client_id = (request.headers.get('x-plex-client-identifier') or '').strip()
    if env.client_token_required and '/library/' in request.url.path:
        allowed = await run_in('store', allowed_client_union)
        if not client_id:
            raise _refuse(request, 404, 'the request sent no X-Plex-Client-Identifier, and CLIENT_TOKEN_REQUIRED demands a registered one')
        if client_id not in allowed:
            raise _refuse(request, 404, f'client "{client_id}" is not registered under any Plex connection (see Config > Clients)')

    cap = env.api_requests_per_day
    if cap:
        if client_id and await _over_quota('client', client_id, cap):
            raise _refuse(request, 429, f'client "{client_id}" has passed its {cap}-request daily limit')
        if user is not None and await _over_quota('user', str(user.id), cap):
            raise _refuse(request, 429, f'the API key for "{user.username}" has passed its {cap}-request daily limit')
