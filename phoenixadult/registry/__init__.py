from __future__ import annotations

import dataclasses
import re

from text_unidecode import unidecode

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
    'provider_name_for',
    'provider_name_tokens',
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
        version='1.0.0-alpha.350',
        media_type='movie',
    ),
]

DEFAULT_PROVIDER_ID = PROVIDER_DEFINITIONS[0].id


def normalize_site_key(token: str) -> str:
    return re.sub(r'[^a-z0-9]', '', unidecode(token).lower())


def _with_archive(sites: list[SiteInfo], archived: list[SiteInfo]) -> list[SiteInfo]:
    taken = {normalize_site_key(token) for site in sites for token in [site.name, *site.aliases]}
    return [*sites, *(site for site in archived if normalize_site_key(site.name) not in taken)]


SITE_DEFINITIONS: list[SiteInfo] = _with_archive(list(_SELECTOR_SITES), _ARCHIVE_SITES)


def _build_tables(
    providers: list[ProviderInfo], sites: list[SiteInfo]
) -> tuple[
    dict[str, ProviderInfo],
    dict[str, ResolvedSiteInfo],
    dict[str, list[ResolvedSiteInfo]],
    dict[str, str],
    dict[str, list[str]],
    list[tuple[str, ResolvedSiteInfo]],
]:
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

    tokens_by_provider_name: dict[str, list[str]] = {}
    for site in resolved:
        tokens_by_provider_name.setdefault(site.provider_name or site.name, []).extend([site.name, *site.aliases])

    prefix_table: list[tuple[str, ResolvedSiteInfo]] = []
    for site in resolved:
        for prefix in site.token_prefixes:
            key = normalize_site_key(prefix)
            if not key:
                raise ValueError(f'Site "{site.name}" declares an empty token prefix.')
            if any(key == existing for existing, _ in prefix_table):
                raise ValueError(f'Registry conflict: token prefix "{key}" declared twice.')
            prefix_table.append((key, site))
    prefix_table.sort(key=lambda entry: -len(entry[0]))

    return provider_by_id, site_by_token, sites_by_provider, display_by_token, tokens_by_provider_name, prefix_table


provider_by_id, site_by_token, sites_by_provider, display_by_token, tokens_by_provider_name, site_by_token_prefix = _build_tables(
    PROVIDER_DEFINITIONS, SITE_DEFINITIONS
)


def get_all_providers() -> list[ProviderInfo]:
    return PROVIDER_DEFINITIONS


def get_provider(provider_id: str) -> ProviderInfo | None:
    return provider_by_id.get(provider_id)


def _prefix_site(token: str) -> ResolvedSiteInfo | None:
    if any(ch.isspace() for ch in token.strip()):
        return None
    key = normalize_site_key(token)
    return next((site for prefix, site in site_by_token_prefix if key.startswith(prefix)), None)


def find_site(token: str) -> ResolvedSiteInfo | None:
    exact = site_by_token.get(normalize_site_key(token))
    return exact if exact is not None else _prefix_site(token)


def canonical_site_display(token: str) -> str | None:
    exact = display_by_token.get(normalize_site_key(token))
    if exact is not None:
        return exact
    site = _prefix_site(token)
    return site.name if site is not None else None


def provider_name_for(token: str) -> str:
    site = find_site(token)
    return (site.provider_name or site.name) if site else ''


def provider_name_tokens(provider_name: str) -> list[str]:
    return tokens_by_provider_name.get(provider_name, [])


def get_sites_for_provider(provider_id: str) -> list[ResolvedSiteInfo]:
    return sites_by_provider.get(provider_id, [])
