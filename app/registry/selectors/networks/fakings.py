from __future__ import annotations

import json
from pathlib import Path

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'FAKings'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''

_ALIASES: list[str] = json.loads((Path(__file__).parent / '_data' / 'json' / 'fakings_aliases.json').read_text(encoding='utf-8'))

FAKINGS_SITES: list[SiteInfo] = [
    make_site(
        name=PROVIDER_NAME,
        provider_name=PROVIDER_NAME,
        base_url='https://www.fakings.com',
        search_path='/en/buscar/{query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        aliases=_ALIASES,
        scraper_type='fakings',
    ),
]
