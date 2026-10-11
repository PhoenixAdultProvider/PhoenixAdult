from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Intersec'
PROVIDER_BASE_URL = 'https://www.insexondemand.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Actor Only'
PROVIDER_SEARCH_PATH = '/iod/home.php?s={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Insex'),
    PROVIDER.site('Sexually Broken', search_path='/iod/home.php?d=sexuallybroken.com&s={query}'),
    PROVIDER.site('Infernal Restraints', search_path='/iod/home.php?d=infernalrestraints.com&s={query}'),
    PROVIDER.site('Real Time Bondage', search_path='/iod/home.php?d=realtimebondage.com&s={query}'),
    PROVIDER.site('Hardtied', search_path='/iod/home.php?d=hardtied.com&s={query}'),
    PROVIDER.site('Topgrl', search_path='/iod/home.php?d=topgrl.com&s={query}'),
    PROVIDER.site('Sensual Pain', search_path='/iod/home.php?d=sensualpain.com&s={query}'),
    PROVIDER.site('Pain Toy', search_path='/iod/home.php?d=paintoy.com&s={query}'),
    PROVIDER.site('Renderfiend', search_path='/iod/home.php?d=renderfiend.com&s={query}'),
    PROVIDER.site('Hotel Hostages', search_path='/iod/home.php?d=hotelhostages.com&s={query}'),
]
