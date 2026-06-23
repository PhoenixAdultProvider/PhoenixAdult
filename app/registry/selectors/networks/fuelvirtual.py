from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'FuelVirtual'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str, search_path: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='fuelvirtual'),
    )


FUELVIRTUAL_SITES: list[SiteInfo] = [
    _site('FuckedHard18', 'fuckedhard18.com', '/membersarea/search.php?st=advanced&site[]=5&qall='),
    _site('MassageGirls18', 'massagegirls18.com', '/membersarea/search.php?st=advanced&site[]=4&qall='),
    _site('NewGirlPOV', 'pornmastermind.com', '/tour/newgirlpov/search.php?qall='),
]
