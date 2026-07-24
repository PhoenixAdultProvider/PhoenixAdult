from __future__ import annotations


def sanitize_header(value: str) -> str:
    """Strip CR/LF/NUL from a header value (header-injection guard)."""
    return value.replace('\r', '').replace('\n', '').replace('\0', '')


def image_request_headers(referers: list[str], cookies: list[str]) -> dict[str, str]:
    """Referer (first) + Cookie (joined) headers for an image fetch, CR/LF-sanitized."""
    headers: dict[str, str] = {}
    if referers:
        headers['Referer'] = sanitize_header(referers[0])
    if cookies:
        headers['Cookie'] = sanitize_header('; '.join(cookies))
    return headers
