from __future__ import annotations

from dataclasses import replace

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider

PROVIDER_NAME = 'Nubiles'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = '/video/gallery/'
PROVIDER_SCENE_TEMPLATE = '{base}/video/watch/{head}'
PROVIDER_DATA18_ENRICHMENT = True

PROVIDER = Provider.from_headers(__name__)

NUBILES_PORN = 'Nubiles Porn'
NUBILES_FILMS = 'Nubile Films'
MOM_LOVER = 'Mom Lover'


def _group(sub_group: str, sites: list[SiteInfo]) -> list[SiteInfo]:
    return [replace(site, sub_group=sub_group) for site in sites]


NUBILES_PORN_SITES = [
    PROVIDER.site('Bad Teens Punished', host='badteenspunished.com'),
    PROVIDER.site('Bounty Hunter Porn', host='bountyhunterporn.com'),
    PROVIDER.site('Caught My Coach', host='caughtmycoach.com'),
    PROVIDER.site('Cheating Sis', host='cheatingsis.com'),
    PROVIDER.site('Cum Swapping Sis', host='cumswappingsis.com'),
    PROVIDER.site("Daddy's Lil Angel", host='daddyslilangel.com'),
    PROVIDER.site('Detention Girls', host='detentiongirls.com'),
    PROVIDER.site('Driver XXX', host='driverxxx.com'),
    PROVIDER.site('Family Swap', host='familyswap.xxx'),
    PROVIDER.site('Moms Teach Sex', host='momsteachsex.com'),
    PROVIDER.site('My Family Pies', host='myfamilypies.com'),
    PROVIDER.site('Nubiles.net', host='nubiles.net'),
    PROVIDER.site('Nubiles Casting', host='nubiles-casting.com'),
    PROVIDER.site('Nubiles ET', host='nubileset.com'),
    PROVIDER.site('Nubiles Porn', host='nubiles-porn.com'),
    PROVIDER.site('Nubiles Unscripted', host='nubilesunscripted.com'),
    PROVIDER.site('Petite Ballerinas Fucked', host='petiteballerinasfucked.com'),
    PROVIDER.site('Petite HD Porn', host='petitehdporn.com'),
    PROVIDER.site('Princess Cum', host='princesscum.com'),
    PROVIDER.site('Reality Sis', host='realitysis.com'),
    PROVIDER.site("She's Breeding Material", host='shesbreedingmaterial.com'),
    PROVIDER.site('Smashed', host='smashed.xxx'),
    PROVIDER.site('Step Siblings Caught', host='stepsiblingscaught.com'),
    PROVIDER.site('Teacher Fucks Teens', host='teacherfucksteens.com'),
    PROVIDER.site('Younger Mommy', host='youngermommy.com'),
]

MOM_LOVER_SITES = [
    PROVIDER.site('Bratty MILF', host='brattymilf.com'),
    PROVIDER.site('Cheating Mommy', host='cheatingmommy.com'),
    PROVIDER.site('Dating My Stepson', host='datingmystepson.com'),
    PROVIDER.site('Double Pies', host='doublepies.com'),
    PROVIDER.site("I'm Not Your Mommy", host='imnotyourmommy.com'),
    PROVIDER.site('MILF Coach', host='milfcoach.com'),
    PROVIDER.site('Mom Lover', host='momlover.com'),
    PROVIDER.site('Mom Swapped', host='momswapped.com'),
    PROVIDER.site('Mom Wants Creampie', host='momwantscreampie.com'),
    PROVIDER.site('Mom Wants to Breed', host='momwantstobreed.com'),
    PROVIDER.site("Mom's Boy Toy", host='momsboytoy.com'),
    PROVIDER.site("Mom's Family Secrets", host='momsfamilysecrets.com'),
    PROVIDER.site("Mom's Tight", host='momstight.com'),
]

NUBILES_FILMS_SITES = [
    PROVIDER.site('Girls Only Porn', host='girlsonlyporn.com', search_path='/video/watch/', data18_enrichment=False),
    PROVIDER.site('Hot Crazy Mess', host='hotcrazymess.com', search_path='/video/'),
    PROVIDER.site('NF Busty', host='nfbusty.com', search_path='/video/'),
    PROVIDER.site('Nubile Films', host='nubilefilms.com'),
    PROVIDER.site('That Sitcom Show', host='thatsitcomshow.com', search_path='/video/'),
]

STANDALONE_SITES = [
    PROVIDER.site('Anilos', host='anilos.com', search_path='/video/', data18_enrichment=False),
    PROVIDER.site('Bratty Sis', host='brattysis.com'),
    PROVIDER.site('Deep Lush', host='deeplush.com', search_path='/video/'),
    PROVIDER.site('The POV God', host='thepovgod.com', data18_enrichment=False),
]

SITES: list[SiteInfo] = [
    *_group(NUBILES_PORN, NUBILES_PORN_SITES),
    *_group(MOM_LOVER, MOM_LOVER_SITES),
    *_group(NUBILES_FILMS, NUBILES_FILMS_SITES),
    *STANDALONE_SITES,
]
