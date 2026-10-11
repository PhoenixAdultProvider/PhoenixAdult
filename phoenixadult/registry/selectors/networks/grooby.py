from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Grooby'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/tour/trailers/'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('TGirl Japan Hardcore', host='www.tgirljapanhardcore.com'),
    PROVIDER.site('TGirl Japan', host='www.tgirljapan.com'),
    PROVIDER.site('Grooby Girls', host='www.groobygirls.com'),
    PROVIDER.site('Femout', host='www.femout.xxx'),
    PROVIDER.site('TGirls', host='www.tgirls.xxx'),
    PROVIDER.site('TGirls Porn', host='www.tgirls.porn'),
    PROVIDER.site('Brazilian Transsexuals', host='www.brazilian-transsexuals.com'),
    PROVIDER.site('TS Casting Couch', host='www.ts-castingcouch.com'),
    PROVIDER.site('Black TGirls', host='www.black-tgirls.com'),
    PROVIDER.site('Bobs TGirls', host='www.bobstgirls.com'),
    PROVIDER.site('Ladyboy', host='www.ladyboy.xxx'),
    PROVIDER.site('Black TGirls Hardcore', host='www.blacktgirlshardcore.com'),
]
