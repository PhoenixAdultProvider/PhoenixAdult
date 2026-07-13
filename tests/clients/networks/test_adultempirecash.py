from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.adultempirecash import AdultEmpireCashClient, __testing__
from app.registry import find_site

STANDARD = find_site('Conor Coxxx')
IMGFLUID = find_site('Jays POV')
SCENEP = find_site('Bizarre Entertainment')
ELEGANT = find_site('Elegant Angel')
assert STANDARD is not None and IMGFLUID is not None and SCENEP is not None and ELEGANT is not None


def _ctx(site: object, title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=site.name, site_info=site, **kw)  # type: ignore[union-attr,arg-type]


@respx.mock
async def test_search_standard_variant() -> None:
    url = 'https://conorcoxxx.com/MemberSceneSearch?q=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div class="item-grid"><div class="grid-item">
              <a class="scene-title" href="/123/cool-scene.html"><h6>Cool Scene</h6></a>
              <span class="date">Aug 27, 2020</span>
            </div></div>""",
        )
    )
    results: list[SearchResult] = []
    await AdultEmpireCashClient().search(results, _ctx(STANDARD, search_date='2020-08-27'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://conorcoxxx.com/123/cool-scene.html'
    assert results[0].display_date == '2020-08-27'


@respx.mock
async def test_search_imgfullfluid_variant() -> None:
    url = 'https://jayspov.net/MemberSceneSearch?q=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div class="item-grid"><div class="grid-item">
              <article class="scene-update"><a href="/9/x.html"></a></article>
              <img class="img-full-fluid" title="Cool Scene" />
            </div></div>""",
        )
    )
    results: list[SearchResult] = []
    await AdultEmpireCashClient().search(results, _ctx(IMGFLUID))
    assert [r.title for r in results] == ['Cool Scene']
    assert results[0].scene_url == 'https://jayspov.net/9/x.html'


@respx.mock
async def test_search_scenetitlep_variant() -> None:
    url = 'https://www.bizarrevideo.com/MemberSceneSearch?q=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div class="item-grid"><div class="grid-item">
              <a class="scene-title" href="/7/y.html"><p>Cool Scene | Bizarre</p></a>
            </div></div>""",
        )
    )
    results: list[SearchResult] = []
    await AdultEmpireCashClient().search(results, _ctx(SCENEP))
    assert [r.title for r in results] == ['Cool Scene']
    assert results[0].scene_url == 'https://www.bizarrevideo.com/7/y.html'


@respx.mock
async def test_search_direct_scene_id() -> None:
    direct = 'https://conorcoxxx.com/555/cool-scene.html'
    respx.get(direct).mock(return_value=httpx.Response(200, text='<h1 class="description">Cool Scene</h1>'))
    respx.get('https://conorcoxxx.com/MemberSceneSearch?q=cool+scene').mock(return_value=httpx.Response(200, text='<div></div>'))
    results: list[SearchResult] = []
    await AdultEmpireCashClient().search(results, _ctx(STANDARD, scene_id='555'))
    assert results[0].scene_url == direct
    assert results[0].score == 100


@respx.mock
async def test_detail_fields() -> None:
    url = 'https://conorcoxxx.com/123/cool-scene.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="description">Cool Scene</h1>
              <div class="synopsis"><p>A summary.</p></div>
              <div class="studio"><span>Umbrella</span><span>Sub Site</span></div>
              <div class="release-date">Aug 27, 2020</div>
              <div class="tags"><a>Tag1</a><a>Tag2 / Tag3</a></div>
              <div class="video-performer"><img title="Jane Doe" data-bgsrc="https://cdn/x.jpg" /></div>
              <div class="video-performer-container"></div>
              <div class="video-performer-container"><a>John Smith</a></div>
              <div class="director">Director: Some Name</div>
              <div id="dv_frames"><img src="https://cdn/img/320/pic_320c.jpg" /></div>
            </body></html>""",
        )
    )
    detail = await AdultEmpireCashClient().fetch_scene_detail(url, STANDARD)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Adult Empire Cash'
    assert detail.tagline == 'Sub Site'
    assert detail.collections == ['Sub Site']
    assert detail.release_date == '2020-08-27'
    assert detail.genres == ['Tag1', 'Tag2', 'Tag3']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'John Smith']
    assert detail.actors[0].photo_url == 'https://cdn/x.jpg'
    assert detail.directors is not None and detail.directors[0].name == 'Some Name'
    assert detail.art == ['https://cdn/img/3840/pic_10.jpg']


@respx.mock
async def test_detail_studio_override_and_elegant_genres() -> None:
    url = 'https://elegantangel.com/1/s.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="description">S</h1>
              <div><strong>Attributes</strong><a>Gonzo</a><a>Anal</a></div>
            </body></html>""",
        )
    )
    detail = await AdultEmpireCashClient().fetch_scene_detail(url, ELEGANT)
    assert detail is not None
    assert detail.genres == ['Gonzo', 'Anal']


def test_upgrade_image() -> None:
    up = __testing__['upgrade_image']
    assert up('https://cdn/320/a_320c.jpg') == 'https://cdn/3840/a_10.jpg'
    assert up('https://cdn/10/b.jpg') == 'https://cdn/3840/b.jpg'


def test_name_keyed_lookups() -> None:
    variant_for = __testing__['variant_for']
    studio_for = __testing__['studio_for']
    assert variant_for('Jays POV') == 'imgFullFluid'
    assert variant_for('Bizarre Entertainment') == 'sceneTitleP'
    assert variant_for('Conor Coxxx') == 'standard'
    assert studio_for('Horny Household') == 'Horny Household'
    assert studio_for('Conor Coxxx') == 'Adult Empire Cash'
