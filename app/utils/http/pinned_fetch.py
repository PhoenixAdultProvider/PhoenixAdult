from __future__ import annotations

from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx2

from app.config.env import env
from app.utils.http.client import make_http
from app.utils.http.ssrf_guard import resolve_public_ip

_MAX_HOPS = 3
_REDIRECT_CODES = {301, 302, 303, 307, 308}


def _ip_netloc(ip: str, port: int | None) -> str:
    host = f'[{ip}]' if ':' in ip else ip
    return f'{host}:{port}' if port else host


async def fetch_pinned(url: str, headers: dict[str, str] | None = None, timeout: float = 10.0) -> httpx2.Response:
    """GET with SSRF pinning: each hop's host is resolved once, validated public, and the
    connection made to that IP — the hostname rides in the Host header and TLS SNI, so a
    DNS-rebind between check and fetch cannot retarget the request. Redirects are walked
    manually and every hop re-validated. With HTTPS_PROXY set the proxy does the resolving,
    so hops are validated but the connection is not IP-pinned."""
    proxied = bool(env.https_proxy and env.https_proxy.strip())
    current = url
    overrides = {} if proxied else {'proxy': None}
    async with make_http(timeout=timeout, follow_redirects=False, **overrides) as client:
        for _ in range(_MAX_HOPS + 1):
            parts = urlsplit(current)
            if parts.scheme not in ('http', 'https') or not parts.hostname:
                raise ValueError(f'blocked scheme/host in "{current}"')
            host = parts.hostname
            ip = await resolve_public_ip(host)
            hop_headers = dict(headers or {})
            if proxied:
                request = client.build_request('GET', current, headers=hop_headers)
            else:
                pinned_url = urlunsplit((parts.scheme, _ip_netloc(ip, parts.port), parts.path, parts.query, ''))
                hop_headers['Host'] = parts.netloc.rsplit('@', 1)[-1]
                extensions = {'sni_hostname': host} if parts.scheme == 'https' else {}
                request = client.build_request('GET', pinned_url, headers=hop_headers, extensions=extensions)
            resp = await client.send(request)
            location = resp.headers.get('location', '')
            if resp.status_code in _REDIRECT_CODES and location:
                await resp.aclose()
                current = urljoin(current, location)
                continue
            return resp
    raise ValueError(f'too many redirects for {url}')
