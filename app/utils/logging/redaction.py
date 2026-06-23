from __future__ import annotations

import logging
import re

from app.config.env import env

MASK = '***REDACTED***'

# Host (+ optional port) of any http(s) URL — scheme and path/query are kept so
# log lines stay debuggable (e.g. http://***REDACTED***/config?token=…).
_URL_HOST = re.compile(r'(?i)(https?://)([^/\s?#]+)')

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


def redact(text: str) -> str:
    text = _QUERY_SECRET.sub(r'\1=' + MASK, text)
    text = _URL_HOST.sub(r'\1' + MASK, text)
    text = _IPV6.sub(MASK, text)
    text = _IPV4.sub(MASK, text)
    return text


class RedactionFilter(logging.Filter):
    """Scrubs URL hosts, IP literals and secret query values from log records when LOG_REDACT_HOSTS is on."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not env.log_redact_hosts:
            return True
        try:
            # uvicorn.access formats from a fixed args tuple: (client_addr, method, path, http_ver, status).
            if record.name.startswith('uvicorn.access') and isinstance(record.args, tuple) and len(record.args) >= 3:
                args = list(record.args)
                args[0] = redact(str(args[0]))  # client IP
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


def install_uvicorn_redaction() -> None:
    for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
        lg = logging.getLogger(name)
        if not any(isinstance(f, RedactionFilter) for f in lg.filters):
            lg.addFilter(RedactionFilter())
