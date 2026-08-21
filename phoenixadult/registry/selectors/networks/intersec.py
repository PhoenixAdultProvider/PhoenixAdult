from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Intersec'
PROVIDER_BASE_URL = 'https://www.insexondemand.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Actor Only'


def _site(name: str, domain: str) -> SiteInfo:
    search_path = f'/iod/home.php?d={domain}&s={{query}}' if domain else '/iod/home.php?s={query}'
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='intersec',
    )


INTERSEC_SITES: list[SiteInfo] = [
    _site('Insex', ''),
    _site('Sexually Broken', 'sexuallybroken.com'),
    _site('Infernal Restraints', 'infernalrestraints.com'),
    _site('Real Time Bondage', 'realtimebondage.com'),
    _site('Hardtied', 'hardtied.com'),
    _site('Topgrl', 'topgrl.com'),
    _site('Sensual Pain', 'sensualpain.com'),
    _site('Pain Toy', 'paintoy.com'),
    _site('Renderfiend', 'renderfiend.com'),
    _site('Hotel Hostages', 'hotelhostages.com'),
]
