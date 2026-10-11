from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Adult Empire Cash'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'DVDs not supported'
PROVIDER_SEARCH_PATH = '/MemberSceneSearch?q={query}'

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site('18 Lust', host='18lust.com'),
    PROVIDER.site('Black Massive Cocks', host='blackmassivecocks.com'),
    PROVIDER.site("Brutha's Inc", host='bruthasinc.com'),
    PROVIDER.site('Concoxxxion', host='concoxxxion.com'),
    PROVIDER.site('Darkside Entertainment', host='darksideentertainment.com'),
    PROVIDER.site('Digital Video Vision', host='digitalvideovision.com'),
    PROVIDER.site('Elegant Angel', host='elegantangel.com'),
    PROVIDER.site('Evasive Angles', host='evasiveangles.com'),
    PROVIDER.site('Forbidden Fruits Films', host='forbiddenfruitsfilms.com'),
    PROVIDER.site('Horny Household', host='hornyhousehold.com'),
    PROVIDER.site('Hot Wife Fun', host='hotwifefun.com'),
    PROVIDER.site('Jays POV', host='jayspov.net'),
    PROVIDER.site('Joanna Angel', host='joannaangel.com'),
    PROVIDER.site('Jodi West', host='jodiwest.com'),
    PROVIDER.site('Jonathan Jordan XXX', host='jonathanjordanxxx.com'),
    PROVIDER.site('Kaiia Eve', host='kaiiaeve.com'),
    PROVIDER.site('Kings of Fetish', host='kingsoffetish.com'),
    PROVIDER.site('Le Wood', host='lewood.com'),
    PROVIDER.site('Only 3x', host='only3x.com'),
    PROVIDER.site('Porn Video Database', host='www.thepornvideodatabase.com'),
    PROVIDER.site('Reagan Foxx', host='www.reaganfoxx.com'),
    PROVIDER.site('Real Girls Fuck', host='realgirlsfuck.com'),
    PROVIDER.site('Severe Sex Films', host='severesexfilms.com'),
    PROVIDER.site('SINematica', host='sinematica.com'),
    PROVIDER.site('SpankMonster', host='spankmonster.com'),
    PROVIDER.site('Star Strokers', host='starstroker.com'),
    PROVIDER.site('Step House XXX', host='stephousexxx.com'),
    PROVIDER.site('Vouyer Media', host='vouyermedia.com'),
    PROVIDER.site('West Coast Productions', host='westcoastproductions.com'),
]
