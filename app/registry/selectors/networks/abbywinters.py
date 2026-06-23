from __future__ import annotations

import json
from pathlib import Path

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Abby Winters'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Actor only'

_ALIASES: list[str] = json.loads((Path(__file__).parent / '_data' / 'json' / 'abbywinters_aliases.json').read_text(encoding='utf-8'))

ABBYWINTERS_SITES: list[SiteInfo] = [
    SiteInfo(
        name=PROVIDER_NAME,
        provider_name=PROVIDER_NAME,
        base_url='https://www.abbywinters.com',
        search_path='/amateurs/models?filters%5Bkeyword%5D={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        aliases=_ALIASES,
        image_referers=['baseurl'],
        scraper_config=ScraperConfig(type='abbywinters'),
    ),
]
