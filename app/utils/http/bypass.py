from __future__ import annotations

from app.config.env import env
from app.utils.http.bypass_types import BypassBackend, BypassRequest, BypassResponse
from app.utils.http.flaresolverr import flare_solverr_backend
from app.utils.http.impersonate import impersonate_backend
from app.utils.http.playwright import playwright_backend
from app.utils.http.reqbin import req_bin_backend
from app.utils.logging.logger import logger

# Impersonate (curl_cffi) is cheapest and forwards headers/Referer — try it first.
ALL_BACKENDS: list[BypassBackend] = [impersonate_backend, flare_solverr_backend, playwright_backend, req_bin_backend]

_BY_NAME = {b.name.lower(): b for b in ALL_BACKENDS}

# Markers of an unsolved anti-bot interstitial returned WITH a 2xx — a backend that
# can't solve the challenge (e.g. FlareSolverr vs AWS WAF) hands back the challenge
# page as 200; treat it as failure so the chain falls through to the next backend.
_CHALLENGE_MARKERS = (
    'awswafcookiedomainlist',  # AWS WAF
    'challenge-container',  # AWS WAF
    'just a moment',  # Cloudflare interstitial
    'cf-chl-',  # Cloudflare challenge
    'turnstile',  # Cloudflare Turnstile
)


def _is_challenge(body: str | None) -> bool:
    if not body:
        return False
    low = body.lower()
    return any(m in low for m in _CHALLENGE_MARKERS)


def _configured_order() -> list[BypassBackend]:
    raw = env.bypass_order_raw
    if not raw:
        return ALL_BACKENDS
    out = [_BY_NAME[t.strip().lower()] for t in raw.split(',') if t.strip().lower() in _BY_NAME]
    return out or ALL_BACKENDS


async def http_bypass(req: BypassRequest) -> BypassResponse | None:
    for backend in _configured_order():
        try:
            available = backend.is_available()
        except Exception as err:  # noqa: BLE001 - a probe failure shouldn't abort the chain
            logger.warn('bypass', f'{backend.name} availability probe threw: {err}')
            available = False
        if not available:
            logger.debug('bypass', f'{backend.name} not available - skipping')
            continue
        logger.info('bypass', f'trying {backend.name} for {req.method} {req.url}')
        try:
            resp = await backend.request(req)
        except Exception as err:  # noqa: BLE001 - try the next backend
            logger.warn('bypass', f'{backend.name} threw: {err}')
            continue
        if resp and 200 <= resp.status < 300:
            if _is_challenge(resp.body):
                logger.info('bypass', f'{backend.name} returned an unsolved challenge for {req.url} ({len(resp.body)}B); trying next')
                continue
            logger.info('bypass', f'{backend.name} served {req.method} {req.url} ({resp.status}, {len(resp.body)}B)')
            return resp
        if resp:
            logger.info('bypass', f'{backend.name} returned {resp.status} for {req.url}; trying next')
    logger.warn('bypass', f'all backends exhausted for {req.url}')
    return None


async def bypass_get(url: str, headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None) -> BypassResponse | None:
    return await http_bypass(BypassRequest(url=url, method='GET', headers=headers or {}, cookies=cookies or {}))


async def bypass_post(url: str, body: str, headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None) -> BypassResponse | None:
    return await http_bypass(BypassRequest(url=url, method='POST', headers=headers or {}, cookies=cookies or {}, body=body))
