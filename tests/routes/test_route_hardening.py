from __future__ import annotations

import re
from pathlib import Path

_HTML = Path(__file__).resolve().parents[2] / 'phoenixadult' / 'routes' / 'html'


def test_inline_handlers_never_embed_escaped_values_in_js_strings() -> None:
    for page in _HTML.glob('*.html'):
        for line in page.read_text(encoding='utf-8').splitlines():
            assert not re.search(r"on\w+=\"[^\"]*\\'' \+ esc\(", line), f'{page.name}: {line.strip()}'
