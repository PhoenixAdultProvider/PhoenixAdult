from __future__ import annotations

import httpx2

from phoenixadult.config.env import env
from phoenixadult.utils.http.bypass_types import BypassRequest, BypassResponse
from phoenixadult.utils.logging.logger import logger


class _FlareSolverrBackend:
    name = 'FlareSolverr'

    def is_available(self) -> bool:
        return bool(env.flaresolverr_url)

    async def request(self, req: BypassRequest) -> BypassResponse | None:
        endpoint = env.flaresolverr_url.rstrip('/')
        if not endpoint:
            return None

        timeout_ms = req.timeout_ms or env.bypass_timeout_ms
        cmd = 'request.post' if req.method == 'POST' else 'request.get'
        payload: dict[str, object] = {
            'cmd': cmd,
            'url': req.url,
            'maxTimeout': timeout_ms,
            'headers': req.headers or {},
        }
        if req.cookies:
            payload['cookies'] = [{'name': name, 'value': value} for name, value in req.cookies.items()]
        if cmd == 'request.post' and req.body is not None:
            payload['postData'] = req.body

        from phoenixadult.utils.http.ssrf_guard import guard_target

        try:
            await guard_target(req.url)
        except ValueError as err:
            logger.warn('bypass:FlareSolverr', f'refusing {req.url}: {err}')
            return None
        try:
            async with httpx2.AsyncClient(timeout=timeout_ms / 1000 + 10, verify=False) as client:
                resp = await client.post(f'{endpoint}/v1', json=payload, headers={'Content-Type': 'application/json'})
            envelope = resp.json()
        except (httpx2.HTTPError, ValueError) as err:
            logger.warn('bypass:FlareSolverr', f'{endpoint}/v1 unreachable ({type(err).__name__}: {err}) — check FLARESOLVERR_URL resolves from this host')
            return None

        if envelope.get('status') != 'ok' or not envelope.get('solution'):
            logger.warn('bypass:FlareSolverr', f'solver error: {envelope.get("message") or "(no message)"}')
            return None
        sol = envelope['solution']
        cookies = {c['name']: c['value'] for c in (sol.get('cookies') or [])}
        return BypassResponse(
            status=sol['status'],
            body=sol.get('response', ''),
            headers=sol.get('headers') or {},
            cookies=cookies,
            final_url=sol.get('url') or req.url,
            user_agent=sol.get('userAgent') or '',
        )


flare_solverr_backend = _FlareSolverrBackend()
