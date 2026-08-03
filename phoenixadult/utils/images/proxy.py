from __future__ import annotations

from urllib.parse import parse_qs, quote, unquote, urlsplit

from phoenixadult.utils.auth.url_signing import sign_url


def proxy_url(
    url: str | None,
    base_url: str,
    referers: list[str] | None = None,
    cookies: list[str] | None = None,
    *,
    passthrough_local: bool = False,
) -> str | None:
    if not url:
        return url
    base = base_url.rstrip('/')
    if url.startswith(f'{base}/images/proxy'):
        return sign_url(url)
    if passthrough_local and url.startswith(f'{base}/images/local/'):
        return sign_url(url)
    out = f'{base}/images/proxy?url={quote(url, safe="")}'
    for r in referers or []:
        out += f'&referer={quote(r, safe="")}'
    for c in cookies or []:
        out += f'&cookie={quote(c, safe="")}'
    return sign_url(out)


def proxy_target(url: str) -> str:
    if '/images/proxy' in url:
        qs = parse_qs(urlsplit(url).query)
        if qs.get('url'):
            return unquote(qs['url'][0])
    return url


def proxy_params(url: str) -> tuple[str, list[str], list[str]]:
    if '/images/proxy' in url:
        qs = parse_qs(urlsplit(url).query)
        if qs.get('url'):
            return unquote(qs['url'][0]), qs.get('referer', []), qs.get('cookie', [])
    return url, [], []
