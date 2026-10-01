from __future__ import annotations

import re
from pathlib import Path

from phoenixadult.utils.plex import client_hits
from tests.support import plex_client

_HTML = Path(__file__).resolve().parents[2] / 'phoenixadult' / 'routes' / 'html'


def test_client_hits_are_recorded_only_on_the_provider_mount() -> None:
    client = plex_client()
    client.get('/health', headers={'x-plex-client-identifier': 'drive-by'})
    client.get('/phoenixadult/movies', headers={'x-plex-client-identifier': 'real-pms'})
    assert [h['clientId'] for h in client_hits.list_hits()] == ['real-pms']


def test_inline_handlers_never_embed_escaped_values_in_js_strings() -> None:
    for page in _HTML.glob('*.html'):
        for line in page.read_text(encoding='utf-8').splitlines():
            assert not re.search(r"on\w+=\"[^\"]*\\'' \+ esc\(", line), f'{page.name}: {line.strip()}'
