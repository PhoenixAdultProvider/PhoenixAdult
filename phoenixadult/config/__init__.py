from __future__ import annotations

import os
import re
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from dotenv import find_dotenv, load_dotenv

from phoenixadult.config.env_overrides import load_overrides

load_dotenv(find_dotenv(usecwd=True))
load_overrides()

_SCHEME_RE = re.compile(r'^[a-z][a-z0-9+.\-]*://', re.IGNORECASE)


@dataclass(frozen=True)
class _Config:
    port: int
    base_url: str
    log_level: str


def _normalize_base_url(raw: str | None, port: int) -> str:
    if not raw or not raw.strip():
        return f'http://localhost:{port}'
    value = raw.strip()
    return value if _SCHEME_RE.match(value) else f'http://{value}'


_RAW_BASE_URL = os.environ.get('PHOENIX_BASE_URL')
_PORT = int(os.environ.get('PORT') or '3000')

config = _Config(
    port=_PORT,
    base_url=_normalize_base_url(_RAW_BASE_URL, _PORT),
    log_level=os.environ.get('LOG_LEVEL') or 'info',
)


def base_url_config_warning() -> str | None:
    raw = (_RAW_BASE_URL or '').strip()
    if not raw or _SCHEME_RE.match(raw):
        return None
    return (
        f'PHOENIX_BASE_URL={raw!r} has no scheme; assuming {config.base_url!r}. '
        'Set a full URL (e.g. http://host:port or https://name.example) so image/link URLs resolve — '
        'the listen PORT is not injected into it.'
    )


_LOCAL_IP_TTL = 60.0
_local_ip_cache: dict[tuple[socket.AddressFamily, str], tuple[float, str]] = {}


def _local_ip(family: socket.AddressFamily, probe: str) -> str:
    hit = _local_ip_cache.get((family, probe))
    if hit and time.monotonic() - hit[0] < _LOCAL_IP_TTL:
        return hit[1]
    fallback = '127.0.0.1' if family == socket.AF_INET else '::1'
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as s:
            s.connect((probe, 80))
            ip = str(s.getsockname()[0])
    except OSError:
        ip = fallback
    _local_ip_cache[(family, probe)] = (time.monotonic(), ip)
    return ip


def image_base_url() -> str:
    from phoenixadult.config.env import env

    opt = env.image_base_url_raw
    if opt == 'localhost':
        return f'http://localhost:{config.port}'
    if opt == 'localipv4':
        return f'http://{_local_ip(socket.AF_INET, "8.8.8.8")}:{config.port}'
    if opt == 'localipv6':
        return f'http://[{_local_ip(socket.AF_INET6, "2001:4860:4860::8888")}]:{config.port}'
    if not opt or opt == 'baseurl':
        return config.base_url
    base = (opt if opt.startswith(('http://', 'https://')) else f'http://{opt}').rstrip('/')
    parts = urlsplit(base)
    if parts.port is None and not parts.path:
        return f'{base}:{config.port}'
    return base
