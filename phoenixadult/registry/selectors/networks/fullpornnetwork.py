from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Full Porn Network'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'limited'
PROVIDER_SEARCH_NOTES = 'Model Name'
PROVIDER_SEARCH_PATH = '/1/search/'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('Analized', host='analized.com'),
    PROVIDER.site('James Deen', host='jamesdeen.com'),
    PROVIDER.site('Twisted Visual', host='twistedvisual.com'),
    PROVIDER.site('Only Prince', host='onlyprince.com'),
    PROVIDER.site('Bad Daddy POV', host='baddaddypov.com'),
    PROVIDER.site('POV Perverts', host='povperverts.net'),
    PROVIDER.site('Pervert Gallery', host='pervertgallery.com'),
    PROVIDER.site('DTF Sluts', host='dtfsluts.com'),
    PROVIDER.site('Bad Mommy POV', host='badmommypov.com'),
    PROVIDER.site('Daughter JOI', host='daughterjoi.com'),
]
