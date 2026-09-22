from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_KINDS = ('sites', 'networks', 'aggregators')

_SELECTOR = """from __future__ import annotations

from phoenixadult.models.site_info import ContentType, SearchMethod, SiteInfo
from phoenixadult.registry.selectors._factory import make_site

PROVIDER_NAME = '@NAME@'
PROVIDER_CONTENT_TYPE: ContentType = '@CONTENT_TYPE@'
PROVIDER_SEARCH_METHOD: SearchMethod = '@SEARCH_METHOD@'
PROVIDER_SEARCH_NOTES = '@SEARCH_NOTES@'

SITES: list[SiteInfo] = [
    make_site(
        name=PROVIDER_NAME,
        provider_name=PROVIDER_NAME,
        base_url='@BASE_URL@',
        search_path='@SEARCH_PATH@',
        content_type=PROVIDER_CONTENT_TYPE,
        search_method=PROVIDER_SEARCH_METHOD,
        search_notes=PROVIDER_SEARCH_NOTES,
        scraper_type='@SCRAPER_TYPE@',
    ),
]
"""

_CLIENT = """from __future__ import annotations

from typing import Any
@CLASSVAR_IMPORT@
from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.urls import absolute_url
from phoenixadult.utils.helpers.html_helpers import first_text


class @CLASS@(Client):
@SCRAPER_TYPE_LINE@    search_url_xpath = '(.//a/@href)[1]'
    search_rows_xpath = '//div[contains(@class,"scene")]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h2')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '(//h1)[1]')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"description")]')

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if not scene.scene_date:
            return

        metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for row in details_page_elements.xpath('//img'):
            images.push(row.xpath('@src').get() or '')

        metadata.art = images.items
"""

_TEST = '''from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.@KIND@.@MODULE@ import @CLASS@
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from tests.support import served_collections

SITE = find_site('@NAME@')
assert SITE is not None


@respx.mock
async def test_search_parses_result_rows() -> None:
    context = SearchContext(title='wild scene', encoded='wild%20scene', search_site=SITE.name, site_info=SITE)
    html = """<html><body>
      <div class="scene"><a href="/scene/wild">x</a><h2>Wild Scene</h2></div>
    </body></html>"""
    respx.get(context.search_url()).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await @CLASS@().search(results, context)
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == '@BASE_URL@/scene/wild'


@respx.mock
async def test_detail_parses_the_scene_page() -> None:
    url = '@BASE_URL@/scene/wild'
    html = """<html><body>
      <h1>Wild Scene</h1>
      <div class="description">A blurb.</div>
      <img src="@BASE_URL@/img/t1.jpg">
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    detail = await @CLASS@().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert served_collections(detail) == ['@NAME@']
    assert detail.art == ['@BASE_URL@/img/t1.jpg']
'''


def _slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower())


def _class_name(name: str) -> str:
    return ''.join(part[:1].upper() + part[1:] for part in re.split(r'[^A-Za-z0-9]+', name) if part) + 'Client'


def _render(template: str, values: dict[str, str]) -> str:
    for token, value in values.items():
        template = template.replace(f'@{token}@', value)
    return template


def _write(path: Path, body: str) -> Path:
    if path.exists():
        raise SystemExit(f'{path.relative_to(_ROOT).as_posix()} already exists')

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8', newline='\n')
    print(f'wrote {path.relative_to(_ROOT).as_posix()}')
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description='Scaffold the selector, client and test for one new scraper.')
    parser.add_argument('--name', required=True, help='registry display name, e.g. "Foo Bar"')
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--kind', default='sites', choices=_KINDS)
    parser.add_argument('--scraper-type', default='', help='defaults to the slugified name')
    parser.add_argument('--module', default='', help='module basename; defaults to the scraper type')
    parser.add_argument('--search-path', default='/search/?q={query}')
    parser.add_argument('--content-type', default='sceneName')
    parser.add_argument('--search-method', default='enhanced', choices=('enhanced', 'limited', 'exact'))
    parser.add_argument('--search-notes', default='')
    args = parser.parse_args()

    scraper_type = args.scraper_type or _slug(args.name)
    module = args.module or scraper_type
    if not module.isidentifier():
        raise SystemExit(f'module name {module!r} is not importable - pass --module with a name that is')

    from phoenixadult.clients import CLIENT_REGISTRY
    from phoenixadult.registry import find_site

    if find_site(args.name) is not None:
        raise SystemExit(f'{args.name!r} is already in the registry')
    if scraper_type in CLIENT_REGISTRY:
        raise SystemExit(f'scraper_type {scraper_type!r} is already claimed')

    values = {
        'NAME': args.name,
        'BASE_URL': args.base_url.rstrip('/'),
        'SEARCH_PATH': args.search_path,
        'CONTENT_TYPE': args.content_type,
        'SEARCH_METHOD': args.search_method,
        'SEARCH_NOTES': args.search_notes,
        'SCRAPER_TYPE': scraper_type,
        'CLASS': _class_name(args.name),
        'KIND': args.kind,
        'MODULE': module,
        'CLASSVAR_IMPORT': 'from typing import ClassVar\n' if module != scraper_type else '',
        'SCRAPER_TYPE_LINE': f"    scraper_type: ClassVar[str] = '{scraper_type}'\n\n" if module != scraper_type else '',
    }

    written = [
        _write(_ROOT / 'phoenixadult' / 'registry' / 'selectors' / args.kind / f'{module}.py', _render(_SELECTOR, values)),
        _write(_ROOT / 'phoenixadult' / 'clients' / args.kind / f'{module}.py', _render(_CLIENT, values)),
        _write(_ROOT / 'tests' / 'clients' / args.kind / f'test_{module}.py', _render(_TEST, values)),
    ]

    paths = [str(path) for path in written]
    subprocess.run([sys.executable, '-m', 'ruff', 'check', '--fix', '--select', 'I', '--quiet', *paths], cwd=_ROOT, check=False)
    subprocess.run([sys.executable, '-m', 'ruff', 'format', '--quiet', *paths], cwd=_ROOT, check=False)
    subprocess.run([sys.executable, '-m', 'scripts.generate_sitelist'], cwd=_ROOT, check=True)

    print(f'\nnext: replace the placeholder xpaths in {written[1].relative_to(_ROOT).as_posix()}')
    print(f'      and the fixtures in {written[2].relative_to(_ROOT).as_posix()} with the real page')


if __name__ == '__main__':
    main()
