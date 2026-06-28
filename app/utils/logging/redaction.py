from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlsplit

from app.config.env import env

MASK = '***REDACTED***'

# Sensitive query-string values (e.g. ?token=…&apikey=…) — value masked, name kept.
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


def redact(text: str) -> str:
    if env.log_redact_token:
        text = _QUERY_SECRET.sub(r'\1=' + MASK, text)
    if env.log_redact_hosts:
        own = _own_host()
        if own:
            text = re.sub(rf'(?i)(?<![\w.-]){re.escape(own)}(?![\w-])', MASK, text)
    text = _IPV6.sub(MASK, text)
    text = _IPV4.sub(MASK, text)
    return text


def redact_client_addr(addr: str) -> str:
    # uvicorn's client_addr is "host:port"; a glued :port defeats the IP boundary
    # checks, so split it off, redact the host, and rejoin.
    host, sep, port = addr.rpartition(':')
    return redact(host) + sep + port if sep else redact(addr)


class RedactionFilter(logging.Filter):
    """Always scrubs IP literals; secret query values only when LOG_REDACT_TOKEN is on; the server's own host only when LOG_REDACT_HOSTS is on."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # uvicorn.access formats from a fixed args tuple: (client_addr, method, path, http_ver, status).
            if record.name.startswith('uvicorn.access') and isinstance(record.args, tuple) and len(record.args) >= 3:
                args = list(record.args)
                args[0] = redact_client_addr(str(args[0]))  # client host:port
                args[2] = redact(str(args[2]))  # request path (?token=…)
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
