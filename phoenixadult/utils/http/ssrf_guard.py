from __future__ import annotations

import asyncio
import ipaddress
from urllib.parse import urlsplit

_DOC_NETS = tuple(ipaddress.ip_network(n) for n in ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24'))


def _ipv4_is_private(ip: str) -> bool:
    try:
        addr = ipaddress.IPv4Address(ip)
    except ValueError:
        return True
    if any(addr in net for net in _DOC_NETS):
        return False
    return not addr.is_global or addr.is_multicast


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
        return True
    return _ipv4_is_private(ip) if kind == 4 else _ipv6_is_private(ip)


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _proxied() -> bool:
    from phoenixadult.config.env import env

    return bool(env.https_proxy)


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


async def guard_target(raw_url: str) -> None:
    parts = urlsplit(raw_url)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        raise ValueError('invalid url')
    host = (parts.hostname or '').strip('[]')
    if is_blocked_hostname(host):
        raise ValueError(f'blocked host "{host}"')
    if _is_ip_literal(host) or _proxied():
        return
    try:
        resolved = await _resolve(host)
    except Exception:  # noqa: BLE001 - the name check already ran; an unresolvable host cannot be proven private
        return
    for address in resolved:
        if is_private_address(address):
            raise ValueError(f'host "{host}" resolves to private address {address}')


async def assert_fetchable_url(raw_url: str) -> str:
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
    parts = urlsplit(target)
    if parts.scheme in ('http', 'https') and parts.netloc:
        await assert_fetchable_url(target)
