from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Full Porn Network'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Model Name'
PROVIDER_SEARCH_PATH = '/1/search/'


def _site(name: str, host: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='fullpornnetwork',
    )


FULLPORNNETWORK_SITES: list[SiteInfo] = [
    _site('Analized', 'analized.com'),
    _site('James Deen', 'jamesdeen.com'),
    _site('Twisted Visual', 'twistedvisual.com'),
    _site('Only Prince', 'onlyprince.com'),
    _site('Bad Daddy POV', 'baddaddypov.com'),
    _site('POV Perverts', 'povperverts.net'),
    _site('Pervert Gallery', 'pervertgallery.com'),
    _site('DTF Sluts', 'dtfsluts.com'),
    _site('Bad Mommy POV', 'badmommypov.com'),
    _site('Daughter JOI', 'daughterjoi.com'),
]
