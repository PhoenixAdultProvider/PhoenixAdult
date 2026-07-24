from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Grooby'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/tour/trailers/'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='grooby',
    )


GROOBY_SITES: list[SiteInfo] = [
    _site('TGirl Japan Hardcore', 'www.tgirljapanhardcore.com'),
    _site('TGirl Japan', 'www.tgirljapan.com'),
    _site('Grooby Girls', 'www.groobygirls.com'),
    _site('Femout', 'www.femout.xxx'),
    _site('TGirls', 'www.tgirls.xxx'),
    _site('TGirls Porn', 'www.tgirls.porn'),
    _site('Brazilian Transsexuals', 'www.brazilian-transsexuals.com'),
    _site('TS Casting Couch', 'www.ts-castingcouch.com'),
    _site('Black TGirls', 'www.black-tgirls.com'),
    _site('Bobs TGirls', 'www.bobstgirls.com'),
    _site('Ladyboy', 'www.ladyboy.xxx'),
    _site('Black TGirls Hardcore', 'www.blacktgirlshardcore.com'),
]
