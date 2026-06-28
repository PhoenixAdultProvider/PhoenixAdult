from __future__ import annotations

from urllib.parse import parse_qs, quote, unquote, urlsplit


def proxy_url(
    url: str | None,
    base_url: str,
    referers: list[str] | None = None,
    cookies: list[str] | None = None,
    *,
    passthrough_local: bool = False,
) -> str | None:
    """Wrap an upstream image URL in our /images/proxy endpoint, carrying optional
    Referer/Cookie hints. Already-proxied URLs (and, when ``passthrough_local``,
    already-cached /images/local/ URLs) are returned unchanged."""
    if not url:
        return url
    base = base_url.rstrip('/')
    if url.startswith(f'{base}/images/proxy'):
        return url
    if passthrough_local and url.startswith(f'{base}/images/local/'):
        return url
    out = f'{base}/images/proxy?url={quote(url, safe="")}'
    for r in referers or []:
        out += f'&referer={quote(r, safe="")}'
    for c in cookies or []:
        out += f'&cookie={quote(c, safe="")}'
    return out


def proxy_target(url: str) -> str:
    """Pull the real upstream URL back out of an /images/proxy?url=… wrapper."""
    if '/images/proxy' in url:
        qs = parse_qs(urlsplit(url).query)
        if qs.get('url'):
            return unquote(qs['url'][0])
    return url
