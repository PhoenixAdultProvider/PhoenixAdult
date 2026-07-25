from __future__ import annotations

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Porn Pros'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = 'Title only — must match the slug in the scene URL'


def _site(name: str, host: str, data18: bool = True) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=f'https://{host}',
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='pornpros',
        data18_enrichment=data18,
    )


PORNPROS_SITES: list[SiteInfo] = [
    _site('18 Years Old', 'pornpros.com'),
    _site('40oz Bounce', 'pornpros.com'),
    _site('Anal4K', 'anal4k.com'),
    _site('Asians Exploited', 'pornplus.com'),
    _site('BAEB', 'baeb.com'),
    _site('BBC POVD', 'pornplus.com'),
    _site('BBC Pie', 'bbcpie.com'),
    _site('Bikini Smash', 'pornplus.com', data18=False),
    _site('Caged Sex', 'pornplus.com'),
    _site('Casting Couch-X', 'castingcouch-x.com'),
    _site('Cock Competition', 'pornpros.com'),
    _site('Creepy Pa', 'creepypa.com', data18=False),
    _site('Cruelty Party', 'pornpros.com'),
    _site('Cum Disgrace', 'pornpros.com'),
    _site('Cum4K', 'cum4k.com'),
    _site('Cumshot Surprise', 'pornpros.com'),
    _site('Deep Throat Love', 'pornpros.com'),
    _site('Disgraced 18', 'pornpros.com'),
    _site('Double Trouble', 'doubletrouble.com'),
    _site('Euro Humpers', 'pornpros.com'),
    _site('Exotic4K', 'exotic4k.com'),
    _site('Exploited Cheerleaders', 'pornplus.com', data18=False),
    _site('Facials Galore', 'pornplus.com'),
    _site('Facials4K', 'facials4k.com'),
    _site('FantasyHD', 'fantasyhd.com'),
    _site('Freaks of Boobs', 'pornpros.com'),
    _site('Freaks of Cock', 'pornpros.com'),
    _site('Game On', 'pornplus.com'),
    _site('Girl Scout Sex', 'pornplus.com', data18=False),
    _site('Girl Cum', 'girlcum.com'),
    _site('Glory Hole 4K', 'pornplus.com'),
    _site('Holed', 'holed.com'),
    _site('Jurassic Cock', 'pornpros.com'),
    _site('Kinky Sluts 4K', 'pornplus.com'),
    _site('Lubed', 'lubed.com'),
    _site('Massage Creep', 'pornpros.com'),
    _site('MILF Humiliation', 'pornpros.com', data18=False),
    _site('Mom4K', 'mom4k.com'),
    _site('MomCum', 'momcum.com'),
    _site('My Very First Time', 'myveryfirsttime.com'),
    _site('Nanny Spy', 'nannyspy.com'),
    _site('Passion-HD', 'passion-hd.com'),
    _site('Pimp Parade', 'pornpros.com'),
    _site('Porn Pros', 'pornpros.com'),
    _site('PornPlus', 'pornplus.com'),
    _site('POVD', 'povd.com'),
    _site('Property Exploits', 'pornplus.com'),
    _site('Pure Mature', 'puremature.com'),
    _site('Real ExGirlfriends', 'pornpros.com'),
    _site('RV Adventures', 'rvadventures.com'),
    _site('School of Cock', 'pornplus.com'),
    _site('Sexercise', 'pornplus.com'),
    _site('Shady Pi', 'pornpros.com'),
    _site('Shower 4K', 'pornplus.com'),
    _site('Spy Fam', 'spyfam.com'),
    _site('Squirt Bomb', 'pornplus.com'),
    _site('Squirt Disgrace', 'pornpros.com'),
    _site('Strip Club Tryouts', 'pornplus.com'),
    _site('Strippers 4K', 'strippers4k.com'),
    _site('TeenBFF', 'pornpros.com'),
    _site('Throat Creampies', 'pornplus.com'),
    _site('Tiny4K', 'tiny4k.com'),
    _site('Waxxxed', 'pornplus.com'),
    _site('WetVR', 'wetvr.com'),
    _site('Zoom POV', 'pornplus.com'),
]
