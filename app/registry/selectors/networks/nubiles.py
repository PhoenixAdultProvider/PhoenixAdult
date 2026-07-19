from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Nubiles'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
NUBILES_PORN = 'Nubiles Porn'
NUBILES_FILMS = 'Nubiles Films'
MOM_LOVER = 'Mom Lover'


def _site(name: str, base_url: str, search_path_prefix: str, data18: bool = False, sub_group: str | None = None) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=base_url,
        search_path=search_path_prefix,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        sub_group=sub_group,
        scraper_type='nubiles',
        data18_enrichment=data18,
    )


NUBILES_SITES: list[SiteInfo] = [
    _site('Anilos', 'https://anilos.com', '/video/'),
    _site('Bad Teens Punished', 'https://badteenspunished.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Bounty Hunter Porn', 'https://bountyhunterporn.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Bratty MILF', 'https://brattymilf.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Bratty Sis', 'https://brattysis.com', '/video/gallery/', data18=True),
    _site('Caught My Coach', 'https://www.caughtmycoach.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Cheating Mommy', 'https://cheatingmommy.com', '/video/gallery/', data18=True, sub_group=MOM_LOVER),
    _site('Cheating Sis', 'https://www.cheatingsis.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Cum Swapping Sis', 'https://cumswappingsis.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Dating My Stepson', 'https://datingmystepson.com', '/video/gallery/', data18=True, sub_group=MOM_LOVER),
    _site('Deep Lush', 'https://deeplush.com', '/video/', data18=True),
    _site('Detention Girls', 'https://detentiongirls.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Driver XXX', 'https://driverxxx.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Family Swap', 'https://familyswap.xxx', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Girls Only Porn', 'https://girlsonlyporn.com', '/video/watch/', sub_group=NUBILES_FILMS),
    _site('Hot Crazy Mess', 'https://hotcrazymess.com', '/video/', data18=True, sub_group=NUBILES_FILMS),
    _site('MILF Coach', 'https://milfcoach.com', '/video/gallery/', data18=True, sub_group=MOM_LOVER),
    _site('Mom Lover', 'https://momlover.com', '/video/gallery/', data18=True, sub_group=MOM_LOVER),
    _site('Mom Swapped', 'https://momswapped.com', '/video/gallery/', data18=True, sub_group=MOM_LOVER),
    _site('Mom Wants Creampie', 'https://momwantscreampie.com', '/video/gallery/', data18=True, sub_group=MOM_LOVER),
    _site('Mom Wants to Breed', 'https://momwantstobreed.com', '/video/gallery/', data18=True, sub_group=MOM_LOVER),
    _site('Moms Teach Sex', 'https://momsteachsex.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('My Family Pies', 'https://myfamilypies.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('NF Busty', 'https://nfbusty.com', '/video/', data18=True, sub_group=NUBILES_FILMS),
    _site('Nubile Films', 'https://nubilefilms.com', '/video/gallery/', data18=True, sub_group=NUBILES_FILMS),
    _site('Nubiles Casting', 'https://nubiles-casting.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Nubiles ET', 'https://nubileset.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Nubiles Porn', 'https://nubiles-porn.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Nubiles Unscripted', 'https://nubilesunscripted.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Nubiles', 'https://nubiles.net', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Petite Ballerinas Fucked', 'https://petiteballerinasfucked.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Petite HD Porn', 'https://petitehdporn.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Princess Cum', 'https://princesscum.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Reality Sis', 'https://www.realitysis.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Smashed', 'https://smashed.xxx', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Step Siblings Caught', 'https://stepsiblingscaught.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('Teacher Fucks Teens', 'https://teacherfucksteens.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site('That Sitcom Show', 'https://thatsitcomshow.com', '/video/', data18=True, sub_group=NUBILES_FILMS),
    _site('The POV God', 'https://thepovgod.com', '/video/gallery/'),
    _site('Younger Mommy', 'https://youngermommy.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site("Daddy's Lil Angel", 'https://daddyslilangel.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
    _site("I'm Not Your Mommy", 'https://imnotyourmommy.com', '/video/gallery/', data18=True, sub_group=MOM_LOVER),
    _site("Mom's Boy Toy", 'https://momsboytoy.com', '/video/gallery/', data18=True, sub_group=MOM_LOVER),
    _site("Mom's Family Secrets", 'https://momsfamilysecrets.com', '/video/gallery/', data18=True, sub_group=MOM_LOVER),
    _site("Mom's Tight", 'https://momstight.com', '/video/gallery/', data18=True, sub_group=MOM_LOVER),
    _site("She's Breeding Material", 'https://www.shesbreedingmaterial.com', '/video/gallery/', data18=True, sub_group=NUBILES_PORN),
]
