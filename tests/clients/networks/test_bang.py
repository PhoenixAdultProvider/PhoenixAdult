from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.bang as bang_mod
from app.clients.base import SearchContext
from app.clients.networks.bang import BangClient, __testing__
from app.registry import find_site

SITE = find_site('Bang')
assert SITE is not None

_VIDEO_LD = """<script type="application/ld+json">
{"@type":"VideoObject","name":"Cool <b>Scene</b>","description":"A <i>summary</i>.",
 "datePublished":"2021-03-04","productionCompany":{"name":"bang originals"},
 "thumbnailUrl":"https://i.bang.com/shots/123/x.jpg"}
</script>"""


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_grid_only_when_no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bang_mod, 'web_search_available', lambda: False)
    url = 'https://www.bang.com/videos?term=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div class="movie-preview">
              <a class="group" href="/video/77/cool-scene"><span>Cool Scene</span></a>
              <span class="hidden xs:inline-block truncate">HD • Mar 4, 2021</span>
            </div>""",
        )
    )
    results = await BangClient().search(_ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.bang.com/video/77/cool-scene'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_search_web_augmentation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bang_mod, 'web_search_available', lambda: True)

    async def fake_web_search(_opts: object) -> list[str]:
        return ['https://www.bang.com/video/123/slug?utm=x']

    monkeypatch.setattr(bang_mod, 'web_search', fake_web_search)
    respx.get('https://www.bang.com/video/123/slug').mock(return_value=httpx.Response(200, text=f'<html><body>{_VIDEO_LD}</body></html>'))
    respx.get('https://www.bang.com/videos?term=cool+scene').mock(return_value=httpx.Response(200, text='<html></html>'))
    results = await BangClient().search(_ctx())
    assert len(results) == 1
    assert results[0].scene_url == 'https://www.bang.com/video/123/slug'
    assert results[0].title == 'Cool Scene'  # from JSON-LD name, HTML stripped
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail_fields() -> None:
    url = 'https://www.bang.com/video/77'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text=f"""<html><body>
              {_VIDEO_LD}
              <p>Series: <a href="/originals/x">Bang Originals</a></p>
              <div class="actions"><a>Anal</a><a>Gonzo</a></div>
              <div class="name"><a href="/pornstar/jane"><span>Jane Doe</span></a></div>
            </body></html>""",
        )
    )
    detail = await BangClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Bang! originals'  # bangify applied to productionCompany
    assert detail.tagline == 'Bang! Originals'
    assert detail.collections == ['Bang! Originals']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal', 'Gonzo']
    assert [a.name for a in detail.actors] == ['Jane Doe']
    # thumbnailUrl is a /shots/ URL → cover synthesized + original kept.
    assert detail.raw_image_urls == ['https://i.bang.com/covers/123/front.jpg', 'https://i.bang.com/shots/123/x.jpg']


def test_helpers() -> None:
    assert __testing__['bangify']('a bang') == 'a Bang!'
    assert __testing__['bangify']('Bang! already') == 'Bang! already'
    assert __testing__['strip_html']('A <b>bold</b>  word') == 'A bold word'
