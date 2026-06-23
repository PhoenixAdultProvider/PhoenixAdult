from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_DATA = Path(__file__).parent / '_data' / 'json' / 'abbreviations.json'
_raw: list[list[str]] = json.loads(_DATA.read_text(encoding='utf-8'))


@dataclass(frozen=True)
class _CompiledRule:
    primary: re.Pattern[str]
    primary_replacement: str
    bare: re.Pattern[str] | None = None
    bare_replacement: str | None = None


def _compile(pat: str, rep: str) -> _CompiledRule:
    if pat.endswith(' ') and rep.endswith(' '):
        return _CompiledRule(
            primary=re.compile(pat[:-1] + r'[\s.]'),
            primary_replacement=rep,
            bare=re.compile(pat[:-1] + r'$'),
            bare_replacement=rep[:-1],
        )
    return _CompiledRule(primary=re.compile(pat), primary_replacement=rep)


COMPILED: list[_CompiledRule] = [_compile(pat, rep) for pat, rep in _raw]


def _const(value: str) -> Callable[[re.Match[str]], str]:
    return lambda _m: value


def expand_abbreviations(s: str) -> str:
    for rule in COMPILED:
        if rule.primary.search(s):
            return rule.primary.sub(_const(rule.primary_replacement), s, count=1)
        if rule.bare is not None and rule.bare_replacement is not None and rule.bare.search(s):
            return rule.bare.sub(_const(rule.bare_replacement), s, count=1)
    return s
