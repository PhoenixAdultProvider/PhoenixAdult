from __future__ import annotations

import ipaddress
import logging
import os
import re
from urllib.parse import urlsplit

from phoenixadult.config.env import env

MASK = '***REDACTED***'

_QUERY_SECRET = re.compile(r'(?i)\b(token|api[_-]?key|apikey|access[_-]?token|auth[_-]?token|secret|password|passwd|pwd)=([^&\s"\'#]+)')

_IPV4 = re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b')

_IPV6 = re.compile(
    r"""(?ix)
    (?<![\w:.])
    (?:
        (?:[A-F0-9]{1,4}:){7}[A-F0-9]{1,4}
      | (?:[A-F0-9]{1,4}:){1,7}:
      | (?:[A-F0-9]{1,4}:){1,6}:[A-F0-9]{1,4}
      | (?:[A-F0-9]{1,4}:){1,5}(?::[A-F0-9]{1,4}){1,2}
      | (?:[A-F0-9]{1,4}:){1,4}(?::[A-F0-9]{1,4}){1,3}
      | (?:[A-F0-9]{1,4}:){1,3}(?::[A-F0-9]{1,4}){1,4}
      | (?:[A-F0-9]{1,4}:){1,2}(?::[A-F0-9]{1,4}){1,5}
      | [A-F0-9]{1,4}:(?::[A-F0-9]{1,4}){1,6}
      | :(?:(?::[A-F0-9]{1,4}){1,7}|:)
    )
    (?![\w:.])
    """
)


_NON_SENSITIVE_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', '::1'}


def _own_host() -> str | None:
    host = urlsplit(os.environ.get('PHOENIX_BASE_URL') or '').hostname
    if not host or host in _NON_SENSITIVE_HOSTS:
        return None
    return host


def _redact_ip(match: re.Match[str]) -> str:
    """Public IPs are ALWAYS masked; private/loopback/link-local ones too
    unless LOG_REDACT_HOSTS is off (so you can see your own LAN address while debugging)."""
    raw = match.group(0)
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return MASK
    if addr.is_private and not env.log_redact_hosts:
        return raw
    return MASK


def redact(text: str) -> str:
    if env.log_redact_token:
        text = _QUERY_SECRET.sub(r'\1=' + MASK, text)
    if env.log_redact_hosts:
        own = _own_host()
        if own:
            text = re.sub(rf'(?i)(?<![\w.-]){re.escape(own)}(?![\w-])', MASK, text)
    text = _IPV6.sub(_redact_ip, text)
    text = _IPV4.sub(_redact_ip, text)
    return text


def redact_client_addr(addr: str) -> str:
    """uvicorn's client_addr is "host:port"; the glued :port defeats the IP boundary
    checks, so split it off, redact the host, and rejoin."""
    host, sep, port = addr.rpartition(':')
    return redact(host) + sep + port if sep else redact(addr)


class RedactionFilter(logging.Filter):
    """Always scrubs public IP literals; private/loopback IPs and the server's own host
    only when LOG_REDACT_HOSTS is on; secret query values only when LOG_REDACT_TOKEN is on."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if record.name.startswith('uvicorn.access') and isinstance(record.args, tuple) and len(record.args) >= 3:
                args = list(record.args)
                args[0] = redact_client_addr(str(args[0]))
                args[2] = redact(str(args[2]))
                record.args = tuple(args)
            else:
                msg = record.getMessage()
                masked = redact(msg)
                if masked != msg:
                    record.msg = masked
                    record.args = None
        except Exception:
            pass
        return True
