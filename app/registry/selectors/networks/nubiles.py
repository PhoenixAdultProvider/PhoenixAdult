from __future__ import annotations

from app.models.scraper_config import ScraperConfig
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Nubiles'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, base_url: str, search_path_prefix: str) -> SiteInfo:
    return SiteInfo(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=base_url,
        search_path='',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        sub_group=search_path_prefix,
        scraper_config=ScraperConfig(type='nubiles', data18_enrichment=True),
    )


NUBILES_SITES: list[SiteInfo] = [
    _site('Nubile Films', 'https://nubilefilms.com', '/video/gallery/'),
    _site('Nubiles Porn', 'https://nubiles-porn.com', '/video/gallery/'),
    _site('Step Siblings Caught', 'https://stepsiblingscaught.com', '/video/gallery/'),
    _site('Moms Teach Sex', 'https://momsteachsex.com', '/video/gallery/'),
    _site('Bad Teens Punished', 'https://badteenspunished.com', '/video/gallery/'),
    _site('Princess Cum', 'https://princesscum.com', '/video/gallery/'),
    _site('Nubiles Unscripted', 'https://nubilesunscripted.com', '/video/gallery/'),
    _site('Nubiles Casting', 'https://nubiles-casting.com', '/video/gallery/'),
    _site('Petite HD Porn', 'https://petitehdporn.com', '/video/gallery/'),
    _site('Driver XXX', 'https://driverxxx.com', '/video/gallery/'),
    _site('Petite Ballerinas Fucked', 'https://petiteballerinasfucked.com', '/video/gallery/'),
    _site('Teacher Fucks Teens', 'https://teacherfucksteens.com', '/video/gallery/'),
    _site('Bountyhunter Porn', 'https://bountyhunterporn.com', '/video/gallery/'),
    _site("Daddy's Lil Angel", 'https://daddyslilangel.com', '/video/gallery/'),
    _site('My Family Pies', 'https://myfamilypies.com', '/video/gallery/'),
    _site('Nubiles', 'https://nubiles.net', '/video/gallery/'),
    _site('Bratty Sis', 'https://brattysis.com', '/video/gallery/'),
    _site('Anilos', 'https://anilos.com', '/video/'),
    _site('Hot Crazy Mess', 'https://hotcrazymess.com', '/video/'),
    _site('NF Busty', 'https://nfbusty.com', '/video/'),
    _site('That Sitcom Show', 'https://thatsitcomshow.com', '/video/'),
    _site('Nubiles ET', 'https://nubileset.com', '/video/gallery/'),
    _site('Detention Girls', 'https://detentiongirls.com', '/video/gallery/'),
    _site('Deep Lush', 'https://deeplush.com', '/video/'),
    _site('FamilySwapXXX', 'https://familyswap.xxx', '/video/watch/'),
    _site('GirlsOnlyPorn', 'https://girlsonlyporn.com', '/video/watch/'),
    _site('Reality Sis (Legacy)', 'https://nubiles-porn.com', '/video/website/73/'),
    _site('Family Swap', 'https://familyswap.xxx', '/video/gallery/'),
    _site('Bratty MILF', 'https://brattymilf.com', '/video/gallery/'),
    _site('Younger Mommy', 'https://youngermommy.com', '/video/gallery/'),
    _site('Cum Swapping Sis', 'https://cumswappingsis.com', '/video/gallery/'),
    _site("Mom's Family Secrets", 'https://momsfamilysecrets.com', '/video/gallery/'),
    _site('Mom Lover', 'https://momlover.com', '/video/gallery/'),
    _site("I'm Not Your Mommy", 'https://imnotyourmommy.com', '/video/gallery/'),
    _site('Mom Swapped', 'https://momswapped.com', '/video/gallery/'),
    _site('Mom Wants to Breed', 'https://momwantstobreed.com', '/video/gallery/'),
    _site('Mom Wants Creampie', 'https://momwantscreampie.com', '/video/gallery/'),
    _site("Mom's Boy Toy", 'https://momsboytoy.com', '/video/gallery/'),
    _site("Mom's Tight", 'https://momstight.com', '/video/gallery/'),
    _site('Smashed', 'https://smashed.xxx', '/video/gallery/'),
    _site('Caught My Coach', 'https://www.caughtmycoach.com', '/video/gallery/'),
    _site('Cheating Sis', 'https://www.cheatingsis.com', '/video/gallery/'),
    _site('Reality Sis', 'https://www.realitysis.com', '/video/gallery/'),
    _site("She's Breeding Material", 'https://www.shesbreedingmaterial.com', '/video/gallery/'),
    _site('Dating My Stepson', 'https://datingmystepson.com', '/video/gallery/'),
    _site('Cheating Mommy', 'https://cheatingmommy.com', '/video/gallery/'),
    _site('MILF Coach', 'https://milfcoach.com', '/video/gallery/'),
    _site('The POV God', 'https://thepovgod.com', '/video/gallery/'),
]
