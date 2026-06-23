from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'PureCFNM'
PROVIDER_CONTENT_TYPE: ContentType = 'actors'
PROVIDER_SEARCH_METHOD: SearchMethod = 'exact'
PROVIDER_SEARCH_NOTES = 'ActressID with Title Search'


def _site(name: str, host: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path='/models/{query}.html',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_config=ScraperConfig(type='purecfnm'),
    )


PURECFNM_SITES: list[SiteInfo] = [
    _site('Amateur CFNM', 'amateurcfnm.com'),
    _site('PureCFNM', 'purecfnm.com'),
    _site('CFNMGames', 'cfnmgames.com'),
    _site('Girls Abuse Guys', 'girlsabuseguys.com'),
    _site('Hey Little Dick', 'heylittledick.com'),
    _site('Lady Voyeurs', 'ladyvoyeurs.com'),
]
