from __future__ import annotations

import asyncio
import ipaddress
from urllib.parse import urlsplit


def _ipv4_is_private(ip: str) -> bool:
    parts = ip.split('.')
    if len(parts) != 4:
        return True
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return True
    if any(n < 0 or n > 255 for n in nums):
        return True
    a, b = nums[0], nums[1]
    if a in (0, 127):
        return True
    if a == 10:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    if a == 169 and b == 254:
        return True
    if a == 100 and 64 <= b <= 127:
        return True
    if a >= 224:
        return True
    return False


def _ipv6_is_private(ip: str) -> bool:
    try:
        addr = ipaddress.IPv6Address(ip.strip('[]'))
    except ValueError:
        return True
    if addr.is_loopback or addr.is_unspecified or addr.is_link_local or addr.is_private or addr.is_multicast:
        return True
    if addr.ipv4_mapped is not None:
        return _ipv4_is_private(str(addr.ipv4_mapped))
    return False


def is_private_address(ip: str) -> bool:
    try:
        kind = ipaddress.ip_address(ip).version
    except ValueError:
        return True  # not an IP literal → caller resolves first
    return _ipv4_is_private(ip) if kind == 4 else _ipv6_is_private(ip)


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def is_blocked_hostname(host: str) -> bool:
    h = host.lower().rstrip('.')
    if not h or h == 'localhost' or h.endswith(('.localhost', '.local', '.internal')):
        return True
    if _is_ip_literal(h):
        return is_private_address(h)
    return False


async def _resolve(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None)
    return [str(info[4][0]) for info in infos]


async def resolve_public_ip(host: str) -> str:
    """Resolve `host`, require every address to be public, and return the address to
    pin the connection to (IPv4 preferred). Raises ValueError on blocked/private."""
    h = host.strip('[]')
    if is_blocked_hostname(h):
        raise ValueError(f'blocked host "{h}"')
    if _is_ip_literal(h):
        return h
    try:
        resolved = await _resolve(h)
    except OSError as err:
        raise ValueError(f'cannot resolve host "{h}"') from err
    if not resolved:
        raise ValueError(f'cannot resolve host "{h}"')
    for address in resolved:
        if is_private_address(address):
            raise ValueError(f'host "{h}" resolves to private address {address}')
    return next((a for a in resolved if ipaddress.ip_address(a).version == 4), resolved[0])


async def assert_fetchable_url(raw_url: str) -> str:
    """Validate a user-supplied URL for proxying; returns the URL or raises."""
    parts = urlsplit(raw_url)
    if not parts.scheme or not parts.netloc:
        raise ValueError('invalid url')
    if parts.scheme not in ('http', 'https'):
        raise ValueError(f'blocked scheme "{parts.scheme}:"')
    host = (parts.hostname or '').strip('[]')
    if is_blocked_hostname(host):
        raise ValueError(f'blocked host "{host}"')
    if _is_ip_literal(host):
        return raw_url
    try:
        resolved = await _resolve(host)
    except OSError as err:
        raise ValueError(f'cannot resolve host "{host}"') from err
    for address in resolved:
        if is_private_address(address):
            raise ValueError(f'host "{host}" resolves to private address {address}')
    return raw_url


async def ensure_fetchable_url(target: str) -> None:
    """No-op when `target` is not an http(s) URL (opaque ids/slugs pass through)."""
    parts = urlsplit(target)
    if parts.scheme in ('http', 'https') and parts.netloc:
        await assert_fetchable_url(target)
