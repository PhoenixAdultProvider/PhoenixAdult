from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.networks.nubiles as nub_mod
from phoenixadult.clients.networks.nubiles import NubilesClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.helpers import pack_cur_id

SITE = find_site('Nubile Films')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_pow(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(_base: str, challenge_path: str = '', pace: object = None) -> dict[str, str]:
        return {}

    monkeypatch.setattr(nub_mod, 'get_verified_cookies', _fake)


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.utils.http.rate_limit_helper as rlh

    monkeypatch.setattr(nub_mod, '_PACE_SECONDS', 0.0)
    monkeypatch.setattr(nub_mod, '_PACE_JITTER', 0.0)
    monkeypatch.setattr(nub_mod, '_SCENE_COOLDOWN', 0.0)
    monkeypatch.setattr(rlh, '_GAP_JITTER_MIN', 0.0)
    monkeypatch.setattr(rlh, '_GAP_JITTER_MAX', 0.0)
    monkeypatch.setenv('SCENE_GAP', '0')


@respx.mock
async def test_paced_serializes_and_spaces_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    import time as _t

    monkeypatch.setattr(nub_mod, '_PACE_SECONDS', 0.1)
    respx.get('https://nubilefilms.com/x').mock(return_value=httpx.Response(200, text='<html></html>'))
    cl = NubilesClient()
    start = _t.monotonic()
    for _ in range(3):
        await cl._get('https://nubilefilms.com/x', SITE, None, 'GET x')
    assert _t.monotonic() - start >= 0.2


def test_strip_episode_tag() -> None:
    assert nub_mod.strip_episode_tag('Stepmom Wants to Move In - S2:E1') == 'Stepmom Wants to Move In'
    assert nub_mod.strip_episode_tag('Home - Sweet Home') == 'Home - Sweet Home'


@respx.mock
async def test_search_scene_id() -> None:
    url = 'https://nubilefilms.com/video/watch/555'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<div class="content-pane-title"><h2>Cool Scene - S1:E6</h2><span class="date">March 4, 2021</span></div><video poster="//cdn/p.jpg"></video>',
        )
    )
    results: list[SearchResult] = []
    await NubilesClient().search(results, _ctx(scene_id='555'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100
    assert results[0].thumb_url == '//cdn/p.jpg'


@respx.mock
async def test_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('PEOPLE_SOURCE_ORDER', raising=False)
    url = 'https://nubilefilms.com/video/watch/555'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="content-pane-title"><h2>Cool Scene - Part One</h2></div>
              <div class="col-12 content-pane-column"><div>A summary.Show More extra</div></div>
              <div class="content-pane"><span class="date">March 4, 2021</span></div>
              <div class="categories"><a>Teen</a><a>nubilefilms.com</a></div>
              <div class="content-pane-performer"><a href="/models/jane">Jane Doe</a></div>
              <div class="content-pane-related-links"><a href="/galleries/555/screenshots">Pics</a></div>
              <video poster="//cdn/p.jpg"></video>
            </body></html>""",
        )
    )
    respx.get('https://nubilefilms.com/models/jane').mock(
        return_value=httpx.Response(200, text='<div class="model-profile"><img src="//cdn/jane.jpg" /></div><p class="model-profile-subheading">Figure: 34</p>')
    )
    respx.get('https://nubilefilms.com/galleries/555/screenshots').mock(
        return_value=httpx.Response(200, text='<div class="img-wrapper"><picture><source srcset="//cdn/g1.jpg 800w, //cdn/g1-sm.jpg 400w" /></picture></div>')
    )
    detail = await NubilesClient().fetch_scene_detail('555|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene - Part One'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Nubile Films'
    assert detail.tagline == ''
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.actors[0].gender == 'female'
    assert detail.art == ['https://cdn/p.jpg', 'https://cdn/g1.jpg']


@pytest.mark.parametrize(
    ('order', 'grab'),
    [
        ('Local Storage,Scene,IAFD', True),
        ('Local Storage,IAFD,Scene', False),
        ('Scene,IAFD', True),
        ('IAFD,Scene', False),
    ],
)
async def test_actor_photo_fetch_follows_source_order(monkeypatch: pytest.MonkeyPatch, order: str, grab: bool) -> None:
    monkeypatch.setenv('PEOPLE_SOURCE_ORDER', order)
    with respx.mock(assert_all_called=False) as router:
        router.get('https://nubilefilms.com/video/watch/555').mock(
            return_value=httpx.Response(
                200,
                text='<div class="content-pane-title"><h2>Cool Scene</h2></div><div class="content-pane-performer"><a href="/models/jane">Jane Doe</a></div>',
            )
        )
        model = router.get('https://nubilefilms.com/models/jane').mock(
            return_value=httpx.Response(200, text='<div class="model-profile"><img src="//cdn/jane.jpg" /></div>')
        )
        detail = await NubilesClient().fetch_scene_detail('555', SITE)
    assert detail is not None
    assert model.called == grab
    assert detail.actors[0].photo_url == ('https://cdn/jane.jpg' if grab else '')


@respx.mock
async def test_gallery_url_from_multi_segment_sample_poster(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('PEOPLE_SOURCE_ORDER', raising=False)
    url = 'https://nubilefilms.com/video/watch/777'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="content-pane-title"><h2>Cool</h2></div>
              <video poster="//img.cdn.net/videos/nf/w1e2/sample/large.jpg"></video>
            </body></html>""",
        )
    )
    gallery = respx.get('https://nubilefilms.com/galleries/nf/w1e2/screenshots').mock(
        return_value=httpx.Response(
            200,
            text="""<div class="content-grid masonry photo-grid">
              <figure class="photo-thumb"><div class="img-wrapper"><a href="/join"><picture>
                <img src="https://images.cdn.net/galleries/nf/1.jpg?st=abc&e=99"
                     srcset="https://images.cdn.net/galleries/nf/459/1.jpg?st=x&e=99 200w" class="content-grid-image" />
              </picture></a></div></figure>
              <figure class="photo-thumb"><div class="img-wrapper"><a href="/join"><picture>
                <img src="https://images.cdn.net/galleries/nf/tn/2.jpg?st=def&e=99"
                     srcset="https://images.cdn.net/galleries/nf/459/2.jpg?st=z&e=99 200w" class="content-grid-image" />
              </picture></a></div></figure>
            </div>
            <div class="content-grid-item"><div class="img-wrapper"><picture>
              <img src="data:image/svg+xml,%3Csvg/%3E" data-srcset="https://images.cdn.net/samples/other-scene_127.jpg 127w"
                   class="lazyload content-grid-image" alt="Other Scene" />
            </picture></div></div>""",
        )
    )
    detail = await NubilesClient().fetch_scene_detail('777', SITE)
    assert detail is not None
    assert gallery.called
    assert detail.art == [
        'https://img.cdn.net/videos/nf/w1e2/sample/large.jpg',
        'https://images.cdn.net/galleries/nf/1.jpg?st=abc&e=99',
        'https://images.cdn.net/galleries/nf/459/2.jpg?st=z&e=99',
    ]


@respx.mock
async def test_search_by_date_builds_results() -> None:
    card = (
        '<div class="content-grid-item">'
        '<span class="title"><a href="/video/watch/321/cool-scene">Jane - Cool Scene</a></span>'
        '<a href="https://badteenspunished.com" class="site-link">BadTeensPunished.com</a>'
        '<span class="date">May 7, 2024</span>'
        '</div>'
    )
    respx.get('https://nubilefilms.com/video/gallery/date/2024-05-07/2024-05-07').mock(
        return_value=httpx.Response(200, text=f'<html><body>{card}</body></html>')
    )
    results: list[SearchResult] = []
    await NubilesClient().search(results, _ctx(title='cool scene', search_date='2024-05-07'))
    assert len(results) == 1
    r = results[0]
    assert r.title == 'Jane - Cool Scene'
    assert r.scene_url == 'https://nubilefilms.com/video/watch/321/cool-scene'
    assert r.cur_id == pack_cur_id(['321', '2024-05-07'])
    assert r.subsite == 'Bad Teens Punished'
    assert r.release_date == '2024-05-07'
    assert r.score is not None and r.score >= 90


@respx.mock
async def test_search_by_date_scores_stripped_actor_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    card = (
        '<div class="content-grid-item">'
        '<span class="title"><a href="/video/watch/321/cool-scene">A Cool Scene</a></span>'
        '<a href="https://badteenspunished.com" class="site-link">BadTeensPunished.com</a>'
        '<span class="date">May 7, 2024</span>'
        '</div>'
    )
    respx.get('https://nubilefilms.com/video/gallery/date/2024-05-07/2024-05-07').mock(
        return_value=httpx.Response(200, text=f'<html><body>{card}</body></html>')
    )
    query = 'jane doe and jane smith a cool scene'

    monkeypatch.delenv('SEARCH_STRIP_ACTORS', raising=False)
    plain_results: list[SearchResult] = []
    await NubilesClient().search(plain_results, _ctx(title=query, search_date='2024-05-07'))

    monkeypatch.setenv('SEARCH_STRIP_ACTORS', 'Nubile Films')
    stripped_results: list[SearchResult] = []
    await NubilesClient().search(stripped_results, _ctx(title=query, search_date='2024-05-07'))

    assert plain_results[0].score is not None and stripped_results[0].score == 100
    assert stripped_results[0].score > plain_results[0].score


@respx.mock
async def test_summary_actor_injection() -> None:
    url = 'https://nubilefilms.com/video/watch/9'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="content-pane-title"><h2>Cool</h2></div>
              <div class="col-12 content-pane-column"><div>Jane meets Johnny Castle and Van Wylde today.</div></div>
            </body></html>""",
        )
    )
    detail = await NubilesClient().fetch_scene_detail('9', SITE)
    assert detail is not None
    names = [a.name for a in detail.actors or []]
    assert names == ['Van Wylde', 'Johnny Castle']
    assert all(a.gender == 'male' for a in detail.actors or [])
