from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Dirty Flix'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Title Only and Date Add'


def _site(name: str, host: str, search_path: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='dirtyflix'),
    )


DIRTYFLIX_SITES: list[SiteInfo] = [
    _site('Trick Your GF', 'trickyourgf.com', '/detailedTrailer/'),
    _site('Make Him Cuckold', 'makehimcuckold.com', '/detailed/'),
    _site('She Is Nerdy', 'sheisnerdy.com', '/detailed/'),
    _site('Tricky Agent', 'trickyagent.com', '/detailedTrailer/'),
]
