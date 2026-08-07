from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlsplit

from phoenixadult.config.env import env

MASK = '***REDACTED***'

_HOOK_PATH = re.compile(r'(/api/hook/)[^/\s"\'#?]+')

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
        text = _HOOK_PATH.sub(r'\1' + MASK, text)
        text = _QUERY_SECRET.sub(r'\1=' + MASK, text)
    if env.log_redact_hosts:
        own = _own_host()
        if own:
            text = re.sub(rf'(?i)(?<![\w.-]){re.escape(own)}(?![\w-])', MASK, text)
        text = _IPV6.sub(MASK, text)
        text = _IPV4.sub(MASK, text)
    return text


def redact_client_addr(addr: str) -> str:
    host, sep, port = addr.rpartition(':')
    return redact(host) + sep + port if sep else redact(addr)


class RedactionFilter(logging.Filter):
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
