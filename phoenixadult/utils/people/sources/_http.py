from __future__ import annotations

import re
from urllib.parse import quote

import httpx2

from phoenixadult.utils.http.client import make_http
from phoenixadult.utils.processors.similarity import compare_string


def make_source_http() -> httpx2.AsyncClient:
    return make_http(timeout=12.0)


def encode_name(name: str) -> str:
    cleaned = re.sub(r'(?<=\w)\.\s(?=\w\.)', '', name)
    cleaned = cleaned.replace('.', '')
    return quote(cleaned)


_PERIOD_FIXES: list[tuple[str, str]] = [
    (r'^dr%20', 'Dr%2E%20'),
    (r'%20st%20', '%20St.%20'),
    (r'^j%20', 'J%2E%20'),
    (r'^wc%20', 'W%2EC%2E%20'),
]


def fix_iafd_encoding(enc: str) -> str:
    for pattern, repl in _PERIOD_FIXES:
        enc = re.sub(pattern, repl, enc, flags=re.IGNORECASE)
    return enc


def levenshtein(a: str, b: str, case_insensitive: bool = True) -> int:
    return compare_string(a, b, case_insensitive).levenshtein
