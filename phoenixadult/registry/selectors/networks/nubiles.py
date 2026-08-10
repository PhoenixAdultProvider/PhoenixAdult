from __future__ import annotations

from dataclasses import replace

from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Nubiles'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
NUBILES_PORN = 'Nubiles Porn'
NUBILES_FILMS = 'Nubile Films'
MOM_LOVER = 'Mom Lover'


def _site(name: str, base_url: str, *, search_path: str = '/video/gallery/', data18: bool = True) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=base_url,
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='nubiles',
        data18_enrichment=data18,
        direct_url_template='{base}/video/watch/{head}',
    )


def _group(sub_group: str, sites: list[SiteInfo]) -> list[SiteInfo]:
    return [replace(site, sub_group=sub_group) for site in sites]


NUBILES_PORN_SITES = [
    _site('Bad Teens Punished', 'https://badteenspunished.com'),
    _site('Bounty Hunter Porn', 'https://bountyhunterporn.com'),
    _site('Caught My Coach', 'https://caughtmycoach.com'),
    _site('Cheating Sis', 'https://cheatingsis.com'),
    _site('Cum Swapping Sis', 'https://cumswappingsis.com'),
    _site("Daddy's Lil Angel", 'https://daddyslilangel.com'),
    _site('Detention Girls', 'https://detentiongirls.com'),
    _site('Driver XXX', 'https://driverxxx.com'),
    _site('Family Swap', 'https://familyswap.xxx'),
    _site('Moms Teach Sex', 'https://momsteachsex.com'),
    _site('My Family Pies', 'https://myfamilypies.com'),
    _site('Nubiles.net', 'https://nubiles.net'),
    _site('Nubiles Casting', 'https://nubiles-casting.com'),
    _site('Nubiles ET', 'https://nubileset.com'),
    _site('Nubiles Porn', 'https://nubiles-porn.com'),
    _site('Nubiles Unscripted', 'https://nubilesunscripted.com'),
    _site('Petite Ballerinas Fucked', 'https://petiteballerinasfucked.com'),
    _site('Petite HD Porn', 'https://petitehdporn.com'),
    _site('Princess Cum', 'https://princesscum.com'),
    _site('Reality Sis', 'https://realitysis.com'),
    _site("She's Breeding Material", 'https://shesbreedingmaterial.com'),
    _site('Smashed', 'https://smashed.xxx'),
    _site('Step Siblings Caught', 'https://stepsiblingscaught.com'),
    _site('Teacher Fucks Teens', 'https://teacherfucksteens.com'),
    _site('Younger Mommy', 'https://youngermommy.com'),
]

MOM_LOVER_SITES = [
    _site('Bratty MILF', 'https://brattymilf.com'),
    _site('Cheating Mommy', 'https://cheatingmommy.com'),
    _site('Dating My Stepson', 'https://datingmystepson.com'),
    _site('Double Pies', 'https://doublepies.com'),
    _site("I'm Not Your Mommy", 'https://imnotyourmommy.com'),
    _site('MILF Coach', 'https://milfcoach.com'),
    _site('Mom Lover', 'https://momlover.com'),
    _site('Mom Swapped', 'https://momswapped.com'),
    _site('Mom Wants Creampie', 'https://momwantscreampie.com'),
    _site('Mom Wants to Breed', 'https://momwantstobreed.com'),
    _site("Mom's Boy Toy", 'https://momsboytoy.com'),
    _site("Mom's Family Secrets", 'https://momsfamilysecrets.com'),
    _site("Mom's Tight", 'https://momstight.com'),
]

NUBILES_FILMS_SITES = [
    _site('Girls Only Porn', 'https://girlsonlyporn.com', search_path='/video/watch/', data18=False),
    _site('Hot Crazy Mess', 'https://hotcrazymess.com', search_path='/video/'),
    _site('NF Busty', 'https://nfbusty.com', search_path='/video/'),
    _site('Nubile Films', 'https://nubilefilms.com'),
    _site('That Sitcom Show', 'https://thatsitcomshow.com', search_path='/video/'),
]

STANDALONE_SITES = [
    _site('Anilos', 'https://anilos.com', search_path='/video/', data18=False),
    _site('Bratty Sis', 'https://brattysis.com'),
    _site('Deep Lush', 'https://deeplush.com', search_path='/video/'),
    _site('The POV God', 'https://thepovgod.com', data18=False),
]

NUBILES_SITES: list[SiteInfo] = [
    *_group(NUBILES_PORN, NUBILES_PORN_SITES),
    *_group(MOM_LOVER, MOM_LOVER_SITES),
    *_group(NUBILES_FILMS, NUBILES_FILMS_SITES),
    *STANDALONE_SITES,
]
