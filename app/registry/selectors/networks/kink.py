from __future__ import annotations

from app.registry.selectors._factory import make_site
from app.registry.site_info import ContentType, SearchMethod, SiteInfo

PROVIDER_NAME = 'Kink'
PROVIDER_BASE_URL = 'https://www.kink.com'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''


def _site(name: str, channel: str) -> SiteInfo:
    search_path = f'/search?channelIds={channel}&q={{query}}' if channel else '/search?q={query}'
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        base_url=PROVIDER_BASE_URL,
        search_path=search_path,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='kink',
    )


KINK_SITES: list[SiteInfo] = [
    _site('Kink', ''),
    _site('Brutal Sessions', 'brutalsessions'),
    _site('Device Bondage', 'devicebondage'),
    _site('Families Tied', 'familiestied'),
    _site('Hardcore Gangbang', 'hardcoregangbang'),
    _site('Hogtied', 'hogtied'),
    _site('Kink Features', 'kinkfeatures'),
    _site('Kink University', 'kinkuniversity'),
    _site('Public Disgrace', 'publicdisgrace'),
    _site('Sadistic Rope', 'sadisticrope'),
    _site('Sex and Submission', 'sexandsubmission'),
    _site('The Training of O', 'thetrainingofo'),
    _site('The Upper Floor', 'theupperfloor'),
    _site('Water Bondage', 'waterbondage'),
    _site('Everything Butt', 'everythingbutt'),
    _site('Foot Worship', 'footworship'),
    _site('Fucking Machines', 'fuckingmachines'),
    _site('TS Pussy Hunters', 'tspussyhunters'),
    _site('TS Seduction', 'tsseduction'),
    _site('Ultimate Surrender', 'ultimatesurrender'),
    _site('30 Minutes of Torment', '30minutesoftorment'),
    _site('Bound Gods', 'boundgods'),
    _site('Bound in Public', 'boundinpublic'),
    _site('Butt Machine Boys', 'buttmachineboys'),
    _site('Men on Edge', 'menonedge'),
    _site('Naked Kombat', 'nakedkombat'),
    _site('Divine Bitches', 'divinebitches'),
    _site('Electrosluts', 'electrosluts'),
    _site('Men In Pain', 'meninpain'),
    _site('Whipped Ass', 'whippedass'),
    _site('Wired Pussy', 'wiredpussy'),
    _site('Bound Gang Bangs', 'boundgangbangs'),
    _site('Chantas Bitches', 'chantasbitches'),
    _site('Fucked and Bound', 'fuckedandbound'),
    _site('Captive Male', 'captivemale'),
    _site('SubmissiveX', 'submissivex'),
    _site('Filthy Femdom', 'filthyfemdom'),
    _site('Kink Evolved Fights Lesbian Edition', 'evolvedfightslesbianedition'),
    _site('Kink Evolved Fights', 'evolvedfights'),
    _site('StraponSquad', 'straponsquad'),
    _site('SexualDisgrace', 'sexualdisgrace'),
    _site('FetishNetwork', 'fetishnetwork'),
    _site('FetishNetwork Male', 'fetishnetworkmale'),
]
