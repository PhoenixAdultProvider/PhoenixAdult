from __future__ import annotations

from urllib.parse import quote

import httpx
import pytest
import respx

import app.clients.aggregators.data18scenes as d18s_module
from app.clients.aggregators.data18scenes import Data18ScenesClient
from app.clients.base import SearchContext
from app.registry import find_site

SITE = find_site('Data18 Scenes')
assert SITE is not None

SEARCH_PAGE = """<html><body>
  pages: 1
  <a href="https://www.data18.com/scenes/9999-fun-scene">
    <p class="gen12 bold">Fun Scene</p>
    <span class="gen11"><b>#1</b> January 5, 2024&nbsp;<i>Teens Like it Big</i></span>
  </a>
</body></html>"""

_HEAD = '<h1 style="display: inline"><a href="/scenes/9999">Scene 3: Fun Scene</a></h1>'
_TAIL = """
  <span class="gen12"><b>Release date</b>: <a href="/scenes#date"><b>Jan 5, 2024</b>
    <span class="gen11">, more updates...</span></a></span>
  <div style="margin-top: 3px;"><b>Categories:</b>
    <a href="/tags/teen">Teen</a>, <span class="gensmall">Hair:</span><a href="/tags/blondes">Hardcore</a></div>
  <h3>Cast</h3>
  <div><a href="/name/jane"><img alt="Jane Doe" /></a></div>
</body></html>"""

# Sub-site is a bold anchor after the "|" (Brazzers -> Teens Like It Big).
SCENE_PAGE = f"""<html><body>{_HEAD}
  <p><b>Network</b>: <b><a href="/studios/brazzers">Brazzers</a></b>
     <span class="gen11">- 14,021 Scenes</span> |
     <a href="/studios/brazzers/teens-like-it-big" class="bold">Teens Like It Big</a>
     <span class="gen11">- 666 Scenes</span></p>{_TAIL}"""

# Sub-site is bare text after the "|", with no anchor at all (Brazzers Exxtra).
SCENE_PAGE_BARE_SUBSITE = f"""<html><body>{_HEAD}
  <p><b>Network</b>: <b><a href="/studios/brazzers">Brazzers</a></b>
     <span class="gen11">- 14,021 Scenes</span> | Brazzers Exxtra
     <span class="gen11">- 12 Scenes</span></p>{_TAIL}"""

# No Network row: a standalone studio, whose value is an anchor, not a <b>.
# The nav widget's <b>R</b> sits after the label and must not be picked up.
SCENE_PAGE_STUDIO_ONLY = f"""<html><body>{_HEAD}
  <p><b>Studio</b>: <a href="/studios/hussie-pass" class="bold">Hussie Pass</a>
     <span class="gen11">- 640 Scenes <span><b>R</b> Nav</span></span></p>{_TAIL}"""

# Webserie lives in the site <p>, not the network <p>. "| Webserie:" is a tail text
# node of the gen11 span, so the name is that span's following sibling, not a descendant.
SCENE_PAGE_WEBSERIE = f"""<html><body>{_HEAD}
  <p><b>Network</b>: <b><a href="/studios/teamskeet">TeamSkeet - Reptyle</a></b>
     <span class="gen11">- 12,260 Scenes</span></p>
  <p><a href="/studios/teamskeet" class="bold">TeamSkeet</a>
     <span class="gen11">- 6,177 Scenes</span> | Webserie:
     <a href="/studios/teamskeet/her-freshman-year" class="bold">Her Freshman Year</a>
     <span class="gen11">- 20 Scenes</span></p>{_TAIL}"""

# Miniserie name is a <u> inside span.listminiserie, with no anchor. The icon span
# of the same class comes first and must be skipped.
SCENE_PAGE_MINISERIE = f"""<html><body>{_HEAD}
  <p><b>Network</b>: <b><a href="/studios/brazzers">Brazzers</a></b>
     <span class="gen11">- 14,021 Scenes</span></p>
  <p><span class="listminiserie"><img src="/mini.jpg" alt="miniserie"></span>
     <b>Miniserie:</b> <span class="listminiserie gen12"><u>Yoga Freaks</u></span></p>{_TAIL}"""


async def _no_web_search(*_args: object, **_kwargs: object) -> list[str]:
    return []


@respx.mock
async def test_search_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d18s_module, 'web_search', _no_web_search)
    q = quote('Fun Scene')
    respx.get(f'https://www.data18.com/sys/live.php?index=&key={q}&key2={q}&next=1&page=0').mock(return_value=httpx.Response(200, text=SEARCH_PAGE))
    results = await Data18ScenesClient().search(SearchContext(title='Fun Scene', encoded=q, search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Fun Scene'
    assert results[0].scene_url == 'https://www.data18.com/scenes/9999'
    assert results[0].subsite == 'Teens Like it Big'


@respx.mock
async def test_search_direct_scene_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d18s_module, 'web_search', _no_web_search)
    respx.get(url__regex=r'https://www\.data18\.com/sys/live\.php.*').mock(return_value=httpx.Response(200, text='<html>pages: 1</html>'))
    respx.get('https://data18.com/scenes/9999').mock(return_value=httpx.Response(200, text=SCENE_PAGE))
    results = await Data18ScenesClient().search(SearchContext(title='', encoded='', search_site=SITE.name, site_info=SITE, scene_id='9999', full_title='9999'))
    direct = [r for r in results if r.scene_url == 'https://data18.com/scenes/9999']
    assert direct and direct[0].score == 100
    assert direct[0].subsite == 'Teens Like It Big'


@respx.mock
async def test_search_direct_scene_id_falls_back_to_studio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d18s_module, 'web_search', _no_web_search)
    respx.get(url__regex=r'https://www\.data18\.com/sys/live\.php.*').mock(return_value=httpx.Response(200, text='<html>pages: 1</html>'))
    respx.get('https://data18.com/scenes/9999').mock(return_value=httpx.Response(200, text=SCENE_PAGE_STUDIO_ONLY))
    results = await Data18ScenesClient().search(SearchContext(title='', encoded='', search_site=SITE.name, site_info=SITE, scene_id='9999', full_title='9999'))
    assert results[0].subsite == 'Hussie Pass'


@respx.mock
async def test_detail() -> None:
    url = 'https://data18.com/scenes/9999'
    respx.get(url).mock(return_value=httpx.Response(200, text=SCENE_PAGE))
    detail = await Data18ScenesClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Fun Scene - Scene 3'
    assert detail.studio == 'Brazzers'
    assert detail.tagline == 'Teens Like It Big'
    assert detail.collections == ['Teens Like It Big']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Teen', 'Hardcore']
    assert [a.name for a in detail.actors] == ['Jane Doe']


@respx.mock
@pytest.mark.parametrize(
    ('page', 'studio', 'tagline'),
    [
        (SCENE_PAGE, 'Brazzers', 'Teens Like It Big'),
        (SCENE_PAGE_BARE_SUBSITE, 'Brazzers', 'Brazzers Exxtra'),
        (SCENE_PAGE_STUDIO_ONLY, 'Hussie Pass', None),
        (SCENE_PAGE_WEBSERIE, 'TeamSkeet', 'Her Freshman Year'),
        (SCENE_PAGE_MINISERIE, 'Brazzers', 'Yoga Freaks'),
    ],
)
async def test_detail_studio_and_tagline_per_network_shape(page: str, studio: str, tagline: str | None) -> None:
    url = 'https://data18.com/scenes/9999'
    respx.get(url).mock(return_value=httpx.Response(200, text=page))
    detail = await Data18ScenesClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.studio == studio
    assert detail.tagline == tagline
    assert detail.collections == [tagline or studio]
