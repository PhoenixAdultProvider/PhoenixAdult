from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import Provider
from phoenixadult.utils.helpers.data_files import load_data

PROVIDER_NAME = 'Gamma'
PROVIDER_CONTENT_TYPE: ContentType = 'sceneName'
PROVIDER_SEARCH_METHOD: SearchMethod = 'enhanced'
PROVIDER_SEARCH_NOTES = ''
PROVIDER_SEARCH_PATH = 'https://tsmkfa364q-dsn.algolia.net/1/indexes/*/queries'

_ALIASES: dict[str, list[str]] = load_data(__file__, 'gammaentother_aliases')

PROVIDER = Provider.from_headers(__name__)

SITES: list[SiteInfo] = [
    PROVIDER.site(
        'Girlsway',
        sub_group='Girlsway',
        base_url='https://www.girlsway.com',
        aliases=["Mommy's Girl", 'Web Young', 'Girls Try Anal', 'Sextape Lesbians', 'Girlsway Originals'],
    ),
    PROVIDER.site('21Naturals', sub_group='21Naturals', base_url='https://www.21naturals.com', aliases=['21FootArt', '21EroticAnal']),
    PROVIDER.site('Evil Angel', sub_group='Evil Angel', base_url='https://www.evilangel.com', aliases=['Blackmailed']),
    PROVIDER.site('HardX', sub_group='XEmpire', base_url='https://www.xempire.com', aliases=['EroticaX', 'DarkX', 'LesbianX', 'AllBlackX']),
    PROVIDER.site('GloryHoleSecrets', sub_group='GloryHoleSecrets', base_url='http://www.gloryholesecrets.com'),
    PROVIDER.site('Pure Taboo', sub_group='Pure Taboo', base_url='https://www.puretaboo.com'),
    PROVIDER.site(
        'Throated',
        sub_group='Blowpass',
        base_url='https://www.blowpass.com',
        aliases=['Mommy Blows Best', 'Only Teen Blowjobs', '1000 Facials', 'Immoral Live', 'My XXX Pass'],
    ),
    PROVIDER.site(
        'Fantasy Massage',
        sub_group='Fantasy Massage',
        base_url='https://www.fantasymassage.com',
        aliases=['Nuru Massage', 'All Girl Massage', 'Soapy Massage', 'Milking Table', 'Massage Parlor', 'Tricky Spa', 'POV Massage'],
    ),
    PROVIDER.site('21Sextury', sub_group='21Sextury', base_url='http://www.21sextury.com', aliases=_ALIASES['21Sextury']),
    PROVIDER.site('Girlfriends Films', sub_group='Girlfriends Films', base_url='http://www.girlfriendsfilms.com'),
    PROVIDER.site('Burning Angel', sub_group='Burning Angel', base_url='http://www.burningangel.com'),
    PROVIDER.site('Pretty Dirty', sub_group='Pretty Dirty', base_url='http://www.prettydirty.com'),
    PROVIDER.site('Devils Film', sub_group='Fame Digital', base_url='http://www.devilsfilm.com'),
    PROVIDER.site('Peter North', sub_group='Fame Digital', base_url='http://www.peternorth.com'),
    PROVIDER.site('Rocco Siffredi', sub_group='Fame Digital', base_url='http://www.roccosiffredi.com'),
    PROVIDER.site('Dogfart', sub_group='Dogfart Network', base_url='https://www.dogfartnetwork.com', aliases=_ALIASES['Dogfart']),
    PROVIDER.site(
        '21Sextreme',
        sub_group='21Sextreme',
        base_url='http://www.21sextreme.com',
        aliases=['Lusty Grandmas', 'Grandpas Fuck Teens', 'Teach Me Fisting', 'Zoliboy', 'Dominated Girls'],
    ),
    PROVIDER.site('Joymii', sub_group='Joymii', base_url='https://www.joymii.com'),
    PROVIDER.site('Gangbang Creampie', sub_group='Gangbang Creampie', base_url='https://www.gangbangcreampie.com'),
    PROVIDER.site('Zero Tolerance', sub_group='Zero Tolerance', base_url='http://www.zerotolerancefilms.com'),
    PROVIDER.site('Wicked', sub_group='Wicked', base_url='https://www.wicked.com'),
    PROVIDER.site('Adult Time', sub_group='Adult Time', base_url='https://adulttime.com', aliases=_ALIASES['Adult Time']),
    PROVIDER.site('Gender X', sub_group='Gender X', base_url='https://www.genderxfilms.com'),
    PROVIDER.site('My Pervy Family', sub_group='My Pervy Family', base_url='https://www.mypervyfamily.com'),
    PROVIDER.site('Filthy Kings', sub_group='Filthy Kings', base_url='https://www.filthykings.com', aliases=_ALIASES['Filthy Kings']),
    PROVIDER.site("Mommy's Boy", sub_group='Mommys Boy', base_url='http://www.mommysboy.com'),
    PROVIDER.site('Model Time', sub_group='Model Time', base_url='http://www.modeltime.com'),
    PROVIDER.site('Out of the Family', sub_group='Out of the Family', base_url='http://www.outofthefamily.com'),
    PROVIDER.site('Give Me Teens', sub_group='Give Me Teens', base_url='http://www.givemeteens.com'),
    PROVIDER.site('White Ghetto', sub_group='White Ghetto', base_url='http://www.whiteghetto.com'),
    PROVIDER.site('Silvia Saint', sub_group='Silvia Saint', base_url='http://www.silviasaint.com'),
    PROVIDER.site('Cumshot Oasis', sub_group='Cumshot Oasis', base_url='http://www.cumshotoasis.com'),
    PROVIDER.site('Lethal Hardcore', sub_group='Lethal Hardcore', base_url='https://www.lethalhardcore.com'),
    PROVIDER.site('Lethal Hardcore VR', sub_group='Lethal Hardcore', base_url='https://www.lethalhardcorevr.com'),
    PROVIDER.site('Touch My Wife', sub_group='Touch My Wife', base_url='http://www.touchmywife.com'),
    PROVIDER.site('Taboo Heat', sub_group='Taboo Heat', base_url='http://www.tabooheat.com'),
    PROVIDER.site('B Skow', sub_group='B Skow', base_url='http://www.bskow.com'),
]
