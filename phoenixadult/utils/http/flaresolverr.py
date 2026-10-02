from __future__ import annotations

from typing import Any

import httpx2

from phoenixadult.config.env import env
from phoenixadult.utils.http.bypass_types import BypassRequest, BypassResponse
from phoenixadult.utils.http.ssrf_guard import guard_target
from phoenixadult.utils.logging.logger import logger


class _FlareSolverrBackend:
    name = 'FlareSolverr'

    def is_available(self) -> bool:
        return bool(env.flaresolverr_url)

    async def request(self, req: BypassRequest) -> BypassResponse | None:
        endpoint = env.flaresolverr_url.rstrip('/')
        if not endpoint:
            return None
        try:
            await guard_target(req.url)
        except ValueError as err:
            logger.warn('bypass:FlareSolverr', f'refusing {req.url}: {err}')
            return None
        timeout_ms = req.timeout_ms or env.bypass_timeout_ms
        envelope = await _solve(endpoint, _payload(req, timeout_ms), timeout_ms)
        if envelope is None:
            return None
        if envelope.get('status') != 'ok' or not envelope.get('solution'):
            logger.warn('bypass:FlareSolverr', f'solver error: {envelope.get("message") or "(no message)"}')
            return None
        return _to_response(envelope['solution'], req)


def _payload(req: BypassRequest, timeout_ms: int) -> dict[str, object]:
    cmd = 'request.post' if req.method == 'POST' else 'request.get'
    payload: dict[str, object] = {'cmd': cmd, 'url': req.url, 'maxTimeout': timeout_ms, 'headers': req.headers or {}}
    if req.cookies:
        payload['cookies'] = [{'name': name, 'value': value} for name, value in req.cookies.items()]
    if cmd == 'request.post' and req.body is not None:
        payload['postData'] = req.body
    return payload


async def _solve(endpoint: str, payload: dict[str, object], timeout_ms: int) -> dict[str, Any] | None:
    try:
        async with httpx2.AsyncClient(timeout=timeout_ms / 1000 + 10, verify=False) as client:
            resp = await client.post(f'{endpoint}/v1', json=payload, headers={'Content-Type': 'application/json'})
        envelope: dict[str, Any] = resp.json()
    except (httpx2.HTTPError, ValueError) as err:
        logger.warn('bypass:FlareSolverr', f'{endpoint}/v1 unreachable ({type(err).__name__}: {err}) — check FLARESOLVERR_URL resolves from this host')
        return None
    return envelope


def _to_response(sol: dict[str, Any], req: BypassRequest) -> BypassResponse:
    return BypassResponse(
        status=sol['status'],
        body=sol.get('response', ''),
        headers=sol.get('headers') or {},
        cookies={c['name']: c['value'] for c in (sol.get('cookies') or [])},
        final_url=sol.get('url') or req.url,
        user_agent=sol.get('userAgent') or '',
    )


flare_solverr_backend = _FlareSolverrBackend()
