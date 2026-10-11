from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'MetArt Network'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/api'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('MetArt', host='www.metart.com'),
    PROVIDER.site('MetArtX', host='www.metartx.com'),
    PROVIDER.site('SexArt', host='www.sexart.com'),
    PROVIDER.site('The Life Erotic', host='www.thelifeerotic.com'),
    PROVIDER.site('VivThomas', host='www.vivthomas.com'),
    PROVIDER.site('Straplezz', host='straplezz.com'),
    PROVIDER.site('Hustler', host='hustler.com'),
    PROVIDER.site('Errotica Archives', host='www.errotica-archives.com'),
    PROVIDER.site('ALS Scan', host='www.alsscan.com'),
    PROVIDER.site('Rylsky Art', host='www.rylskyart.com'),
    PROVIDER.site('Eternal Desire', host='www.eternaldesire.com'),
    PROVIDER.site('Stunning18', host='www.stunning18.com'),
    PROVIDER.site('Love Hairy', host='www.lovehairy.com'),
]
