from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site
from phoenixadult.utils.helpers.helpers import load_data

PROVIDER_NAME = 'Gamma'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = 'https://tsmkfa364q-dsn.algolia.net/1/indexes/*/queries'

_ALIASES: dict[str, list[str]] = load_data(__file__, 'gammaentother_aliases')


def _site(sub_group: str, base_url: str, name: str, aliases: list[str] | None = None) -> SiteInfo:
    return make_site(
        name=name,
        provider_name=PROVIDER_NAME,
        sub_group=sub_group,
        base_url=base_url,
        search_path=PROVIDER_SEARCH_PATH,
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        aliases=aliases or [],
        scraper_type='gammaentother',
    )


SITES: list[SiteInfo] = [
    _site('Girlsway', 'https://www.girlsway.com', 'Girlsway', ["Mommy's Girl", 'Web Young', 'Girls Try Anal', 'Sextape Lesbians', 'Girlsway Originals']),
    _site('21Naturals', 'https://www.21naturals.com', '21Naturals', ['21FootArt', '21EroticAnal']),
    _site('Evil Angel', 'https://www.evilangel.com', 'Evil Angel', ['Blackmailed']),
    _site('XEmpire', 'https://www.xempire.com', 'HardX', ['EroticaX', 'DarkX', 'LesbianX', 'AllBlackX']),
    _site('GloryHoleSecrets', 'http://www.gloryholesecrets.com', 'GloryHoleSecrets'),
    _site('Pure Taboo', 'https://www.puretaboo.com', 'Pure Taboo'),
    _site('Blowpass', 'https://www.blowpass.com', 'Throated', ['Mommy Blows Best', 'Only Teen Blowjobs', '1000 Facials', 'Immoral Live', 'My XXX Pass']),
    _site(
        'Fantasy Massage',
        'https://www.fantasymassage.com',
        'Fantasy Massage',
        ['Nuru Massage', 'All Girl Massage', 'Soapy Massage', 'Milking Table', 'Massage Parlor', 'Tricky Spa', 'POV Massage'],
    ),
    _site('21Sextury', 'http://www.21sextury.com', '21Sextury', _ALIASES['21Sextury']),
    _site('Girlfriends Films', 'http://www.girlfriendsfilms.com', 'Girlfriends Films'),
    _site('Burning Angel', 'http://www.burningangel.com', 'Burning Angel'),
    _site('Pretty Dirty', 'http://www.prettydirty.com', 'Pretty Dirty'),
    _site('Fame Digital', 'http://www.devilsfilm.com', 'Devils Film'),
    _site('Fame Digital', 'http://www.peternorth.com', 'Peter North'),
    _site('Fame Digital', 'http://www.roccosiffredi.com', 'Rocco Siffredi'),
    _site('Dogfart Network', 'https://www.dogfartnetwork.com', 'Dogfart', _ALIASES['Dogfart']),
    _site('21Sextreme', 'http://www.21sextreme.com', '21Sextreme', ['Lusty Grandmas', 'Grandpas Fuck Teens', 'Teach Me Fisting', 'Zoliboy', 'Dominated Girls']),
    _site('Joymii', 'https://www.joymii.com', 'Joymii'),
    _site('Gangbang Creampie', 'https://www.gangbangcreampie.com', 'Gangbang Creampie'),
    _site('Zero Tolerance', 'http://www.zerotolerancefilms.com', 'Zero Tolerance'),
    _site('Wicked', 'https://www.wicked.com', 'Wicked'),
    _site('Adult Time', 'https://adulttime.com', 'Adult Time', _ALIASES['Adult Time']),
    _site('Gender X', 'https://www.genderxfilms.com', 'Gender X'),
    _site('My Pervy Family', 'https://www.mypervyfamily.com', 'My Pervy Family'),
    _site('Filthy Kings', 'https://www.filthykings.com', 'Filthy Kings', _ALIASES['Filthy Kings']),
    _site('Mommys Boy', 'http://www.mommysboy.com', "Mommy's Boy"),
    _site('Model Time', 'http://www.modeltime.com', 'Model Time'),
    _site('Out of the Family', 'http://www.outofthefamily.com', 'Out of the Family'),
    _site('Give Me Teens', 'http://www.givemeteens.com', 'Give Me Teens'),
    _site('White Ghetto', 'http://www.whiteghetto.com', 'White Ghetto'),
    _site('Silvia Saint', 'http://www.silviasaint.com', 'Silvia Saint'),
    _site('Cumshot Oasis', 'http://www.cumshotoasis.com', 'Cumshot Oasis'),
    _site('Lethal Hardcore', 'https://www.lethalhardcore.com', 'Lethal Hardcore'),
    _site('Lethal Hardcore', 'https://www.lethalhardcorevr.com', 'Lethal Hardcore VR'),
    _site('Touch My Wife', 'http://www.touchmywife.com', 'Touch My Wife'),
    _site('Taboo Heat', 'http://www.tabooheat.com', 'Taboo Heat'),
    _site('B Skow', 'http://www.bskow.com', 'B Skow'),
]
