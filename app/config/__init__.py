from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

from app.config.env_overrides import load_overrides

load_dotenv()
load_overrides()


@dataclass(frozen=True)
class _Config:
    port: int
    base_url: str
    log_level: str


config = _Config(
    port=int(os.environ.get('PORT') or '3000'),
    base_url=os.environ.get('PHOENIX_BASE_URL') or 'http://localhost:3000',
    log_level=os.environ.get('LOG_LEVEL') or 'info',
)


@lru_cache(maxsize=1)
def _local_ip(family: socket.AddressFamily, probe: str) -> str:
    # No packets are sent — connect() on a UDP socket just picks the local address
    # the OS would route through to reach `probe`.
    fallback = '127.0.0.1' if family == socket.AF_INET else '::1'
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as s:
            s.connect((probe, 80))
            return str(s.getsockname()[0])
    except OSError:
        return fallback


def people_image_base() -> str:
    """Base URL for actor/director/producer image links. Plex re-requests these
    periodically (it doesn't keep them), so a stable local address outlives an
    ephemeral tunnel FQDN. PEOPLE_IMAGE_URL selects it; metadata (poster/art) images
    keep using base_url. 'localhost' = loopback (same machine); 'localipv4'/'localipv6'
    = this machine's LAN address (reachable by a Plex box elsewhere on the network)."""
    from app.config.env import env

    opt = env.people_image_url_raw
    if opt == 'localhost':
        return f'http://localhost:{config.port}'
    if opt == 'localipv4':
        return f'http://{_local_ip(socket.AF_INET, "8.8.8.8")}:{config.port}'
    if opt == 'localipv6':
        return f'http://[{_local_ip(socket.AF_INET6, "2001:4860:4860::8888")}]:{config.port}'
    return config.base_url
