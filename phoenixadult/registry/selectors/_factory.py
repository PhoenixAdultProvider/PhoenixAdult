from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, TypedDict, Unpack, get_args

from phoenixadult.models.scraper_config import ScraperConfig
from phoenixadult.models.site_info import BypassName, ContentType, SearchMethod, SiteInfo


def make_site(
    name: str,
    *,
    scraper_type: str,
    base_url: str,
    fallback_url: str = '',
    search_path: str = '/',
    content_type: ContentType = 'sceneName',
    data18_enrichment: bool = False,
    provider_id: str | None = None,
    provider_name: str | None = None,
    direct_url_template: str | None = None,
    aliases: list[str] | None = None,
    sub_group: str | None = None,
    image_referers: list[str] | None = None,
    image_cookies: list[str] | None = None,
    search_method: SearchMethod | None = None,
    search_notes: str | None = None,
    bypass: list[BypassName] | None = None,
    token_prefixes: tuple[str, ...] = (),
) -> SiteInfo:
    return SiteInfo(
        name=name,
        base_url=base_url,
        fallback_url=fallback_url,
        search_path=search_path,
        content_type=content_type,
        scraper_config=ScraperConfig(type=scraper_type, data18_enrichment=data18_enrichment),
        provider_id=provider_id,
        provider_name=provider_name,
        direct_url_template=direct_url_template,
        aliases=tuple(aliases or ()),
        sub_group=sub_group,
        image_referers=tuple(image_referers or ()),
        image_cookies=tuple(image_cookies or ()),
        search_method=search_method,
        search_notes=search_notes,
        bypass=tuple(bypass or ()),
        token_prefixes=token_prefixes,
    )


class SiteFields(TypedDict, total=False):
    base_url: str
    fallback_url: str
    search_path: str
    content_type: ContentType
    data18_enrichment: bool
    direct_url_template: str
    aliases: list[str]
    sub_group: str
    image_referers: list[str]
    image_cookies: list[str]
    search_method: SearchMethod
    search_notes: str
    bypass: list[BypassName]
    token_prefixes: tuple[str, ...]


HEADER_FIELDS: dict[str, str] = {
    'PROVIDER_NAME': 'provider_name',
    'PROVIDER_CONTENT_TYPE': 'content_type',
    'PROVIDER_SEARCH_METHOD': 'search_method',
    'PROVIDER_SEARCH_NOTES': 'search_notes',
    'PROVIDER_SEARCH_PATH': 'search_path',
    'PROVIDER_BASE_URL': 'base_url',
    'PROVIDER_BYPASS': 'bypass',
    'PROVIDER_SCENE_TEMPLATE': 'direct_url_template',
    'PROVIDER_SCRAPER_TYPE': 'scraper_type',
    'PROVIDER_DATA18_ENRICHMENT': 'data18_enrichment',
    'PROVIDER_IMAGE_REFERERS': 'image_referers',
    'PROVIDER_IMAGE_COOKIES': 'image_cookies',
}
_REQUIRED = ('PROVIDER_NAME', 'PROVIDER_CONTENT_TYPE', 'PROVIDER_SEARCH_METHOD')
_ALLOWED: dict[str, tuple[Any, ...]] = {
    'PROVIDER_CONTENT_TYPE': get_args(ContentType),
    'PROVIDER_SEARCH_METHOD': get_args(SearchMethod),
}
_HOST = '{host}'


@dataclass(frozen=True)
class Provider:
    module: str
    defaults: dict[str, Any]

    @classmethod
    def from_headers(cls, module_name: str) -> Provider:
        headers = {name: value for name, value in vars(sys.modules[module_name]).items() if name.startswith('PROVIDER_')}
        if unknown := sorted(set(headers) - set(HEADER_FIELDS)):
            raise RuntimeError(f'{module_name}: unknown provider header(s) {unknown}; known: {sorted(HEADER_FIELDS)}')
        if missing := [name for name in _REQUIRED if name not in headers]:
            raise RuntimeError(f'{module_name}: missing provider header(s) {missing}')
        for name, allowed in _ALLOWED.items():
            if headers[name] not in allowed:
                raise RuntimeError(f'{module_name}: {name} = {headers[name]!r} is not one of {allowed}')
        if bad := [b for b in headers.get('PROVIDER_BYPASS', ()) if b not in get_args(BypassName)]:
            raise RuntimeError(f'{module_name}: PROVIDER_BYPASS names unknown backend(s) {bad}; known: {get_args(BypassName)}')
        defaults = {HEADER_FIELDS[name]: value for name, value in headers.items()}
        defaults.setdefault('scraper_type', module_name.rsplit('.', 1)[-1])
        return cls(module_name, defaults)

    def site(self, name: str, *, host: str | None = None, **fields: Unpack[SiteFields]) -> SiteInfo:
        values: dict[str, Any] = {**self.defaults, **fields}
        if 'base_url' not in fields:
            values['base_url'] = self._base_url(name, host)
        elif host is not None:
            raise RuntimeError(f'{self.module}: {name} sets both host and base_url')
        return make_site(name, **values)

    def _base_url(self, name: str, host: str | None) -> str:
        template = self.defaults.get('base_url')
        if host is None:
            if template is None or _HOST in template:
                raise RuntimeError(f'{self.module}: {name} needs a host or a base_url')
            return str(template)
        if template is None:
            return f'https://{host}'
        if _HOST not in template:
            raise RuntimeError(f'{self.module}: {name} sets host, but PROVIDER_BASE_URL has no {_HOST} placeholder')
        return str(template).replace(_HOST, host)
