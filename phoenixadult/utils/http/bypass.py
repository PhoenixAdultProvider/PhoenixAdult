from __future__ import annotations

from collections.abc import Callable

from phoenixadult.config.env import env
from phoenixadult.utils.http.bypass_types import BypassBackend, BypassRequest, BypassResponse
from phoenixadult.utils.http.flaresolverr import flare_solverr_backend
from phoenixadult.utils.http.impersonate import impersonate_backend
from phoenixadult.utils.http.playwright import playwright_backend
from phoenixadult.utils.http.reqbin import req_bin_backend
from phoenixadult.utils.logging.logger import logger

ALL_BACKENDS: list[BypassBackend] = [impersonate_backend, flare_solverr_backend, playwright_backend, req_bin_backend]

_BY_NAME = {b.name.lower(): b for b in ALL_BACKENDS}

_CHALLENGE_MARKERS = (
    'awswafcookiedomainlist',
    'challenge-container',
    'just a moment',
    'cf-chl-',
    'turnstile',
    'verifying browser',
)


def is_challenge(body: str | None) -> bool:
    if not body:
        return False
    low = body.lower()
    return any(m in low for m in _CHALLENGE_MARKERS)


def _no_site_backends(url: str) -> tuple[str, ...]:
    return ()


_site_backends: Callable[[str], tuple[str, ...]] = _no_site_backends


def set_site_backends(resolver: Callable[[str], tuple[str, ...]]) -> None:
    global _site_backends
    _site_backends = resolver


def site_backends(url: str) -> tuple[str, ...]:
    return _site_backends(url)


def _configured_order() -> list[BypassBackend]:
    raw = env.bypass_order_raw
    if not raw:
        return ALL_BACKENDS
    out = [_BY_NAME[t.strip().lower()] for t in raw.split(',') if t.strip().lower() in _BY_NAME]
    return out or ALL_BACKENDS


def _order_for(url: str) -> list[BypassBackend]:
    named = site_backends(url)
    if named:
        return [_BY_NAME[n.lower()] for n in named if n.lower() in _BY_NAME]
    return _configured_order()


async def http_bypass(req: BypassRequest) -> BypassResponse | None:
    for backend in _order_for(req.url):
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
            if is_challenge(resp.body):
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
