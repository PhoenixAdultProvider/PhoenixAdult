from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Romero Multimedia'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_IMAGE_REFERERS = ['sceneURL']
PROVIDER_SEARCH_PATH = '/?s={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Defeated XXX', host='defeated.xxx'),
    PROVIDER.site('Defeated Sex Fight', host='defeatedsexfight.com'),
    PROVIDER.site('Goonblins', host='goonblins.com'),
    PROVIDER.site('Hentaied', host='hentaied.com'),
    PROVIDER.site('Parasited', host='parasited.com'),
    PROVIDER.site('Futanari XXX', host='futanari.xxx'),
    PROVIDER.site('Freeze', host='freeze.xxx'),
    PROVIDER.site('Plants vs Cunts', host='plantsvscunts.com'),
    PROVIDER.site('Voodooed', host='voodooed.com'),
    PROVIDER.site('Vored', host='vored.com'),
]
