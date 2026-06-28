from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo
from app.utils.helpers.helpers import load_site_json

PROVIDER_NAME = 'Reptyle'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/movies/{query}'

_ALIASES: dict[str, list[str]] = load_site_json(__file__, 'reptyle_aliases')


def _site(name: str, base_url: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=base_url,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        aliases=_ALIASES.get(name, []),
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='reptyle',
        data18_enrichment=True,
    )


REPTYLE_SITES: list[SiteInfo] = [
    _site('MYLF', 'https://www.mylf.com'),
    _site('TeamSkeet', 'https://www.teamskeet.com'),
    _site('Swappz', 'https://www.swappz.com'),
    _site('FreeUse', 'https://www.freeuse.com'),
    _site('Pervz', 'https://www.pervz.com'),
    _site('Family Strokes', 'https://www.familystrokes.com'),
]
