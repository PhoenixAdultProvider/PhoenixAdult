from __future__ import annotations

import sys
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest

from phoenixadult.registry.selectors._factory import Provider

_MODULE = 'tests.registry.probe_selector'
_BASE = {'PROVIDER_NAME': 'Probe', 'PROVIDER_CONTENT_TYPE': 'sceneName', 'PROVIDER_SEARCH_METHOD': 'enhanced'}


@pytest.fixture
def headers() -> Iterator[Any]:
    def make(**values: object) -> Provider:
        module = ModuleType(_MODULE)
        vars(module).update({**_BASE, **values})
        sys.modules[_MODULE] = module
        return Provider.from_headers(_MODULE)

    yield make
    sys.modules.pop(_MODULE, None)


def test_headers_become_site_defaults(headers: Any) -> None:
    provider = headers(PROVIDER_SEARCH_PATH='/s?q={query}', PROVIDER_BYPASS=['Impersonate'], PROVIDER_DATA18_ENRICHMENT=True)
    site = provider.site('Alpha', host='alpha.test')
    assert site.base_url == 'https://alpha.test'
    assert site.provider_name == 'Probe'
    assert site.search_path == '/s?q={query}'
    assert site.bypass == ('Impersonate',)
    assert site.scraper_config.type == 'probe_selector'
    assert site.scraper_config.data18_enrichment is True


def test_site_fields_override_headers(headers: Any) -> None:
    site = headers(PROVIDER_SEARCH_PATH='/s').site('Alpha', host='alpha.test', search_path='/other', data18_enrichment=True)
    assert site.search_path == '/other'
    assert site.scraper_config.data18_enrichment is True


def test_host_fills_the_base_url_template(headers: Any) -> None:
    assert headers(PROVIDER_BASE_URL='https://www.{host}').site('Alpha', host='alpha.test').base_url == 'https://www.alpha.test'


def test_shared_base_url_needs_no_host(headers: Any) -> None:
    assert headers(PROVIDER_BASE_URL='https://shared.test').site('Alpha').base_url == 'https://shared.test'


def test_scraper_type_header_overrides_the_file_name(headers: Any) -> None:
    assert headers(PROVIDER_SCRAPER_TYPE='other').site('Alpha', host='alpha.test').scraper_config.type == 'other'


@pytest.mark.parametrize(
    ('values', 'message'),
    [
        ({'PROVIDER_SEARCH_PAHT': '/'}, 'unknown provider header'),
        ({'PROVIDER_CONTENT_TYPE': 'scene'}, 'PROVIDER_CONTENT_TYPE'),
        ({'PROVIDER_SEARCH_METHOD': 'fuzzy'}, 'PROVIDER_SEARCH_METHOD'),
        ({'PROVIDER_BYPASS': ['Flaresolverr']}, 'unknown backend'),
    ],
)
def test_bad_headers_fail_at_import(headers: Any, values: dict[str, object], message: str) -> None:
    with pytest.raises(RuntimeError, match=message):
        headers(**values)


def test_missing_required_header_fails(headers: Any) -> None:
    module = ModuleType(_MODULE)
    module.PROVIDER_NAME = 'Probe'  # type: ignore[attr-defined]
    sys.modules[_MODULE] = module
    with pytest.raises(RuntimeError, match='missing provider header'):
        Provider.from_headers(_MODULE)


@pytest.mark.parametrize(
    ('values', 'kwargs', 'message'),
    [
        ({}, {}, 'needs a host or a base_url'),
        ({'PROVIDER_BASE_URL': 'https://www.{host}'}, {}, 'needs a host or a base_url'),
        ({'PROVIDER_BASE_URL': 'https://shared.test'}, {'host': 'alpha.test'}, 'no {host} placeholder'),
        ({}, {'host': 'alpha.test', 'base_url': 'https://alpha.test'}, 'both host and base_url'),
    ],
)
def test_base_url_rules(headers: Any, values: dict[str, object], kwargs: dict[str, str], message: str) -> None:
    provider = headers(**values)
    with pytest.raises(RuntimeError, match=message):
        provider.site('Alpha', **kwargs)
