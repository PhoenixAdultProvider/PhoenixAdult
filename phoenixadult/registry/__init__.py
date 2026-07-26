from __future__ import annotations

import dataclasses
import re
import unicodedata

from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.registry.selectors import SITE_DEFINITIONS as _SELECTOR_SITES
from phoenixadult.registry.selectors.aggregators.archive import ARCHIVE_SITES as _ARCHIVE_SITES
from phoenixadult.registry.site_info import ContentType, ResolvedSiteInfo, SiteInfo

__all__ = [
    'ContentType',
    'SiteInfo',
    'ResolvedSiteInfo',
    'PROVIDER_DEFINITIONS',
    'DEFAULT_PROVIDER_ID',
    'SITE_DEFINITIONS',
    'normalize_site_key',
    'canonical_site_display',
    'get_all_providers',
    'get_provider',
    'find_site',
    'get_sites_for_provider',
]

PROVIDER_DEFINITIONS: list[ProviderInfo] = [
    ProviderInfo(
        id='phoenixadult',
        plex_identifier='tv.plex.agents.custom.phoenixadult',
        title='PhoenixAdult',
        version='1.0.0-alpha.171',
        media_type='movie',
    ),
]

DEFAULT_PROVIDER_ID = PROVIDER_DEFINITIONS[0].id


def normalize_site_key(token: str) -> str:
    folded = unicodedata.normalize('NFKD', token).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', folded.lower())


def _with_archive(sites: list[SiteInfo], archived: list[SiteInfo]) -> list[SiteInfo]:
    """Archive entries only fill gaps: a name a real client already claims keeps its scraper, so
    porting a retired site later silently retires its archive stand-in."""
    taken = {normalize_site_key(token) for site in sites for token in [site.name, *site.aliases]}
    return [*sites, *(site for site in archived if normalize_site_key(site.name) not in taken)]


SITE_DEFINITIONS: list[SiteInfo] = _with_archive(list(_SELECTOR_SITES), _ARCHIVE_SITES)


def _build_tables(
    providers: list[ProviderInfo], sites: list[SiteInfo]
) -> tuple[dict[str, ProviderInfo], dict[str, ResolvedSiteInfo], dict[str, list[ResolvedSiteInfo]], dict[str, str]]:
    provider_by_id = {p.id: p for p in providers}

    resolved: list[ResolvedSiteInfo] = []
    for site in sites:
        data = {f.name: getattr(site, f.name) for f in dataclasses.fields(site)}
        data['provider_id'] = site.provider_id or DEFAULT_PROVIDER_ID
        resolved.append(ResolvedSiteInfo(**data))

    for site in resolved:
        if site.provider_id not in provider_by_id:
            raise ValueError(f'Site "{site.name}" references unknown providerId "{site.provider_id}".')

    site_by_token: dict[str, ResolvedSiteInfo] = {}
    display_by_token: dict[str, str] = {}
    for site in resolved:
        for token in [site.name, *site.aliases]:
            key = normalize_site_key(token)
            if key in site_by_token:
                raise ValueError(f'Registry conflict: token "{key}" claimed by both "{site_by_token[key].name}" and "{site.name}".')
            site_by_token[key] = site
            display_by_token[key] = token

    sites_by_provider: dict[str, list[ResolvedSiteInfo]] = {p.id: [] for p in providers}
    for site in resolved:
        sites_by_provider[site.provider_id].append(site)

    return provider_by_id, site_by_token, sites_by_provider, display_by_token


provider_by_id, site_by_token, sites_by_provider, display_by_token = _build_tables(PROVIDER_DEFINITIONS, SITE_DEFINITIONS)


def get_all_providers() -> list[ProviderInfo]:
    return PROVIDER_DEFINITIONS


def get_provider(provider_id: str) -> ProviderInfo | None:
    return provider_by_id.get(provider_id)


def find_site(token: str) -> ResolvedSiteInfo | None:
    return site_by_token.get(normalize_site_key(token))


def canonical_site_display(token: str) -> str | None:
    """The registry-curated display form (site name or alias) for `token`, if known."""
    return display_by_token.get(normalize_site_key(token))


def get_sites_for_provider(provider_id: str) -> list[ResolvedSiteInfo]:
    return sites_by_provider.get(provider_id, [])
