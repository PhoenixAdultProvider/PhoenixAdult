from __future__ import annotations

import re
import sys
from pathlib import Path

INIT = Path(__file__).resolve().parents[1] / 'phoenixadult' / '__init__.py'
_VERSION_RE = re.compile(r"^__version__ = '(?P<base>\d+\.\d+\.\d+)a(?P<alpha>\d+)'$", re.MULTILINE)


def _parse() -> tuple[str, re.Match[str]]:
    source = INIT.read_text(encoding='utf-8')
    found = _VERSION_RE.search(source)
    if not found:
        raise SystemExit(f'{INIT} does not carry a "X.Y.Za<n>" __version__ line')
    return source, found


def read() -> str:
    _source, found = _parse()
    return f'{found.group("base")}a{found.group("alpha")}'


def bump() -> str:
    source, found = _parse()
    nxt = f'{found.group("base")}a{int(found.group("alpha")) + 1}'
    INIT.write_text(_VERSION_RE.sub(f"__version__ = '{nxt}'", source, count=1), encoding='utf-8')
    return nxt


if __name__ == '__main__':
    print(read() if '--read' in sys.argv else bump())
