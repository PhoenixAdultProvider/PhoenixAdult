from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Romero Multimedia'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, host: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path='/?s={query}',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        image_referers=['sceneURL'],
        scraper_config=ScraperConfig(type='romero'),
    )


ROMERO_SITES: list[SiteInfo] = [
    _site('Defeated XXX', 'defeated.xxx'),
    _site('Defeated Sex Fight', 'defeatedsexfight.com'),
    _site('Goonblins', 'goonblins.com'),
    _site('Hentaied', 'hentaied.com'),
    _site('Parasited', 'parasited.com'),
    _site('Futanari XXX', 'futanari.xxx'),
    _site('Freeze', 'freeze.xxx'),
    _site('Plants vs Cunts', 'plantsvscunts.com'),
    _site('Voodooed', 'voodooed.com'),
    _site('Vored', 'vored.com'),
]
