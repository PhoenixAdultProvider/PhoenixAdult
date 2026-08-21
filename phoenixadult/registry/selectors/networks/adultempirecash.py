from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = 'Adult Empire Cash'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'DVDs not supported'
PROVIDER_SEARCH_PATH = '/MemberSceneSearch?q={query}'


def _site(name: str, base_url: str) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=base_url,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='adultempirecash',
    )


ADULTEMPIRECASH_SITES: list[SiteInfo] = [
    _site('18 Lust', 'https://18lust.com'),
    _site('Black Massive Cocks', 'https://blackmassivecocks.com'),
    _site("Brutha's Inc", 'https://bruthasinc.com'),
    _site('Concoxxxion', 'https://concoxxxion.com'),
    _site('Darkside Entertainment', 'https://darksideentertainment.com'),
    _site('Digital Video Vision', 'https://digitalvideovision.com'),
    _site('Elegant Angel', 'https://elegantangel.com'),
    _site('Evasive Angles', 'https://evasiveangles.com'),
    _site('Forbidden Fruits Films', 'https://forbiddenfruitsfilms.com'),
    _site('Horny Household', 'https://hornyhousehold.com'),
    _site('Hot Wife Fun', 'https://hotwifefun.com'),
    _site('Jays POV', 'https://jayspov.net'),
    _site('Joanna Angel', 'https://joannaangel.com'),
    _site('Jodi West', 'https://jodiwest.com'),
    _site('Jonathan Jordan XXX', 'https://jonathanjordanxxx.com'),
    _site('Kaiia Eve', 'https://kaiiaeve.com'),
    _site('Kings of Fetish', 'https://kingsoffetish.com'),
    _site('Le Wood', 'https://lewood.com'),
    _site('Only 3x', 'https://only3x.com'),
    _site('Porn Video Database', 'https://www.thepornvideodatabase.com'),
    _site('Reagan Foxx', 'https://www.reaganfoxx.com'),
    _site('Real Girls Fuck', 'https://realgirlsfuck.com'),
    _site('Severe Sex Films', 'https://severesexfilms.com'),
    _site('SINematica', 'https://sinematica.com'),
    _site('SpankMonster', 'https://spankmonster.com'),
    _site('Star Strokers', 'https://starstroker.com'),
    _site('Step House XXX', 'https://stephousexxx.com'),
    _site('Vouyer Media', 'https://vouyermedia.com'),
    _site('West Coast Productions', 'https://westcoastproductions.com'),
]
