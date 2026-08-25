from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest
import respx

import phoenixadult.clients.networks.scoregroup as sg_mod
from phoenixadult.clients.base import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.clients.networks.scoregroup import ScoreGroupClient
from phoenixadult.registry import find_site


async def _no_web_search(*_a: object, **_k: object) -> list[str]:
    return []


SITE = find_site('Scoreland')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_web(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sg_mod, 'web_search_urls', _no_web_search)


@respx.mock
async def test_search_posts_the_query_as_form_data() -> None:
    html = (
        '<div class="compact video">'
        '<a class="title" href="https://scoreland.com/big-boob-videos/jane/777/">Cool Scene</a>'
        '<small class="i-model">Jane Doe</small><img src="https://cdn/t.jpg" /></div>'
    )
    route = respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(scene_id='777'))

    request = route.calls.last.request
    assert request.headers['content-type'] == 'application/x-www-form-urlencoded'
    assert parse_qs(request.content.decode()) == {'keywords': ['cool scene'], 's_filters[type]': ['videos'], 's_filters[site]': ['current']}
    assert not request.url.query

    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100


@respx.mock
async def test_detail() -> None:
    import json

    packed = json.dumps({'url': 'https://scoreland.com/big-boob-videos/jane/777/', 'date': '2021-03-04', 'title': 'Cool Scene'})
    respx.get('https://scoreland.com/big-boob-videos/jane/777/').mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Cool Scene</h1>
              <div class="p-desc">A summary.</div>
              <div><span class="value">x</span><span class="value">March 4, 2021</span></div>
              <div class="mb-3"><a>Big Tits</a></div>
              <div><span class="value"><a href="/model/jane">Jane Doe</a></span></div>
              <div class="thumb"><img src="https://cdn/p.jpg" /></div>
            </body></html>""",
        )
    )
    respx.get('https://www.scoreland.com/model/jane').mock(
        return_value=httpx.Response(200, text='<div class="item-img"><img src="https://cdn/jane.jpg" /></div>')
    )
    detail = await ScoreGroupClient().fetch_scene_detail(packed, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Score Group'
    assert detail.tagline == 'Scoreland'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Big Tits']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.art == ['https://cdn/p.jpg']


@respx.mock
async def test_a_join_promo_row_is_not_a_scene() -> None:
    html = (
        '<div class="compact video">'
        '<a class="i-title" href="https://join.scoreland.com/track/abc/join">Join Now</a>'
        '<small class="i-model">Jane Doe</small><img src="https://cdn/t.jpg" /></div>'
    )
    respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx())

    assert results == [], 'anonymous search rows link to /join, which is not a scene url'


@respx.mock
async def test_the_same_scene_in_two_letter_cases_is_one_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _two_urls(*_a: object, **_k: object) -> list[str]:
        return ['https://www.scoreland.com/big-boob-videos/Jane/777/']

    monkeypatch.setattr(sg_mod, 'web_search_urls', _two_urls)
    respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text='<html></html>'))
    page = '<html><body><h1>Cool Scene</h1></body></html>'
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(return_value=httpx.Response(200, text=page))
    respx.get('https://www.scoreland.com/big-boob-videos/Jane/777/').mock(return_value=httpx.Response(200, text=page))

    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(title='jane 777', full_title='jane 777'))

    assert len(results) == 1, f'the guessed url and the search-engine url are the same scene: {[r.scene_url for r in results]}'


@respx.mock
async def test_the_summary_stops_before_read_more_and_the_tags() -> None:
    import json

    packed = json.dumps({'url': 'https://www.scoreland.com/big-boob-videos/jane/777/', 'title': 'Cool Scene'})
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Cool Scene</h1>
              <div class="p-desc p-3">
                <h2>Bombshell Returns</h2>
                She bends in ways that should not be legal.
                <a class="accent-text">Read More &#187;</a>
                <hr class="my-1" />
                <div class="my-3">Share X/Twitter Reddit Copy Link</div>
                <h3 class="mt-3">Related Tags</h3>
                <a class="btn">Big Tits</a><a class="btn">Blonde</a>
              </div>
            </body></html>""",
        )
    )
    detail = await ScoreGroupClient().fetch_scene_detail(packed, SITE)

    assert detail is not None
    assert detail.summary == 'She bends in ways that should not be legal.'
    for junk in ('Bombshell Returns', 'Read More', 'Share', 'Related Tags', 'Big Tits', 'Blonde'):
        assert junk not in detail.summary, f'{junk!r} leaked into the summary'


_VIEWS_PAGE = """<html><body>
  <h1>Cool Scene</h1>
  <div><span>Views:</span><span class="value">15K+</span></div>
  <div><span>Featuring:</span><span class="value">Jane Doe</span></div>
  <div><span>Date:</span><span class="value">September 7th, 2024</span></div>
  <div><span>Duration:</span><span class="value">29:27</span></div>
</body></html>"""


@respx.mock
async def test_the_date_comes_from_its_own_label_not_a_position() -> None:
    import json

    packed = json.dumps({'url': 'https://www.scoreland.com/big-boob-videos/jane/777/', 'date': '2001-01-01'})
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(return_value=httpx.Response(200, text=_VIEWS_PAGE))
    detail = await ScoreGroupClient().fetch_scene_detail(packed, SITE)

    assert detail is not None
    assert detail.release_date == '2024-09-07', 'a Views: row shifts the value index; the Date: label does not move'


@respx.mock
async def test_a_candidate_carries_its_own_date_and_an_id_hit_scores_100(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _one(*_a: object, **_k: object) -> list[str]:
        return ['https://www.scoreland.com/big-boob-videos/jane/777/']

    monkeypatch.setattr(sg_mod, 'web_search_urls', _one)
    respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(return_value=httpx.Response(200, text=_VIEWS_PAGE))

    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(title='jane 777', scene_id='777', search_date='2001-01-01'))

    assert len(results) == 1
    assert results[0].display_date == '2024-09-07', "the scene's own date, never the filename's"
    assert results[0].score == 100, 'the url carries the scene id, so it is the scene'


@respx.mock
async def test_the_form_drops_the_scene_id_but_the_web_search_keeps_it(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    async def _record(query: str, *_a: object, **_k: object) -> list[str]:
        asked.append(query)
        return []

    monkeypatch.setattr(sg_mod, 'web_search_urls', _record)
    route = respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text='<html></html>'))

    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(title='jane 777', full_title='jane 777'))

    assert parse_qs(route.calls.last.request.content.decode())['keywords'] == ['jane'], 'the bundle strips the id before searching'
    assert asked == ['jane 777'], 'the id is what makes the search engine find the exact scene'


@respx.mock
async def test_a_poster_inside_a_script_is_still_picked_up() -> None:
    import json

    packed = json.dumps({'url': 'https://www.scoreland.com/big-boob-videos/jane/777/'})
    page = (
        '<html><body><h1>Cool Scene</h1>'
        '<script type="text/javascript">var p = {poster: \'https://cdn/from-script.jpg\'};</script>'
        '<div class="dl-opts"><a><img src="https://cdn/from-dl-opts.jpg" /></a></div>'
        '</body></html>'
    )
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(return_value=httpx.Response(200, text=page))
    detail = await ScoreGroupClient().fetch_scene_detail(packed, SITE)

    assert detail is not None
    assert detail.art == ['https://cdn/from-script.jpg', 'https://cdn/from-dl-opts.jpg']


def _shot_page(site: str, scene: str) -> str:
    shots = ''.join(f'<div class="thumb"><img src="//cdn77.x.com/{site}/scenes/{scene}/Screenshots/{scene}_{n:02d}.jpg" /></div>' for n in (1, 2, 3, 4))
    return f'<html><body><h1>Cool Scene</h1>{shots}</body></html>'


@respx.mock
async def test_screenshots_expand_into_the_gallery_until_it_runs_out() -> None:
    import json

    base = 'https://cdn77.x.com/18eighteen/scenes/AdrianMaya_30805/Gallys/18eighteen'
    for n in range(1, 17):
        respx.head(f'{base}/{n:02d}.jpg').mock(return_value=httpx.Response(200))
    respx.head(url__startswith=base).mock(return_value=httpx.Response(404))

    packed = json.dumps({'url': 'https://www.scoreland.com/big-boob-videos/jane/777/'})
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(return_value=httpx.Response(200, text=_shot_page('18eighteen', 'AdrianMaya_30805')))
    detail = await ScoreGroupClient().fetch_scene_detail(packed, SITE)

    assert detail is not None
    assert detail.art == [f'{base}/{n:02d}.jpg' for n in range(1, 17)], 'stops at the first missing number, keeps everything before it'
    assert f'{base}/17.jpg' not in detail.art
    assert not [u for u in detail.art if '/Screenshots/' in u], 'the screenshots are thumbnails; the gallery replaces them'


@respx.mock
async def test_the_gallery_folder_is_named_after_the_cdn_site_segment() -> None:
    import json

    base = 'https://cdn77.x.com/scoreland/scenes/BarbieNicole_41170/Gallys/scoreland'
    respx.head(f'{base}/01.jpg').mock(return_value=httpx.Response(200))
    respx.head(url__startswith=base).mock(return_value=httpx.Response(404))

    packed = json.dumps({'url': 'https://www.scoreland.com/big-boob-videos/jane/777/'})
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(return_value=httpx.Response(200, text=_shot_page('scoreland', 'BarbieNicole_41170')))
    detail = await ScoreGroupClient().fetch_scene_detail(packed, SITE)

    assert detail is not None
    assert f'{base}/01.jpg' in detail.art, 'the folder follows the /<site>/ segment of the cdn url, not the plex site name'


@respx.mock
async def test_a_page_without_screenshots_is_never_probed() -> None:
    import json

    probes = respx.head(url__regex=r'.*').mock(return_value=httpx.Response(200))
    packed = json.dumps({'url': 'https://www.scoreland.com/big-boob-videos/jane/777/'})
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(
        return_value=httpx.Response(200, text='<html><body><h1>Cool Scene</h1><div class="thumb"><img src="https://cdn/plain.jpg" /></div></body></html>')
    )
    detail = await ScoreGroupClient().fetch_scene_detail(packed, SITE)

    assert detail is not None
    assert detail.art == ['https://cdn/plain.jpg']
    assert not probes.called, 'no Screenshots url means there is nothing to derive a gallery from'


@respx.mock
async def test_the_screenshots_stay_when_no_gallery_can_be_derived() -> None:
    import json

    respx.head(url__regex=r'.*').mock(return_value=httpx.Response(404))
    packed = json.dumps({'url': 'https://www.scoreland.com/big-boob-videos/jane/777/'})
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(return_value=httpx.Response(200, text=_shot_page('18eighteen', 'AdrianMaya_30805')))
    detail = await ScoreGroupClient().fetch_scene_detail(packed, SITE)

    assert detail is not None
    assert len([u for u in detail.art if '/Screenshots/' in u]) == 4, 'a low-res screenshot beats no image at all'


@respx.mock
async def test_the_id_in_the_filename_scores_100_without_a_parsed_scene_id(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _both(*_a: object, **_k: object) -> list[str]:
        return ['https://www.scoreland.com/big-boob-videos/Alex-Blake/53203/']

    monkeypatch.setattr(sg_mod, 'web_search_urls', _both)
    respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text='<html></html>'))
    for slug, num in (('alex-blake', '53212'), ('Alex-Blake', '53203')):
        respx.get(f'https://www.scoreland.com/big-boob-videos/{slug}/{num}/').mock(
            return_value=httpx.Response(200, text=f'<html><body><h1>Scene {num}</h1></body></html>')
        )

    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(title='alex blake 53212', full_title='alex blake 53212'))

    by_url = {r.scene_url: r.score for r in results}
    assert by_url['https://www.scoreland.com/big-boob-videos/alex-blake/53212/'] == 100, (
        'the filename carries 53212 even though nothing parsed it as a leading scene id'
    )
    assert by_url['https://www.scoreland.com/big-boob-videos/Alex-Blake/53203/'] != 100, 'a different scene must not claim a perfect match'


@respx.mock
@pytest.mark.parametrize(
    'promo',
    [
        'Watch Our Amateur Videos Anywhere, Anytime &amp; on Any Device',
        'Watch Our Teen Videos Anywhere, Anytime &amp; on Any Device',
        'Watch Our Videos Anywhere, Anytime &amp; on Any Device',
        'Watch Our Foot Fetish Videos Anywhere, Anytime &amp; on Any Device',
    ],
)
async def test_the_sites_soft_404_never_becomes_a_result(promo: str, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _none(*_a: object, **_k: object) -> list[str]:
        return []

    monkeypatch.setattr(sg_mod, 'web_search_urls', _none)
    respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(return_value=httpx.Response(200, text=f'<html><body><h1>{promo}</h1></body></html>'))

    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(title='jane 777', full_title='jane 777'))

    assert results == [], 'a missing scene answers 200 with this banner as its only h1'


@respx.mock
async def test_a_real_scene_is_untouched_by_the_soft_404_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _none(*_a: object, **_k: object) -> list[str]:
        return []

    monkeypatch.setattr(sg_mod, 'web_search_urls', _none)
    respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(
        return_value=httpx.Response(200, text='<html><body><h1>Watch Our Videos</h1></body></html>')
    )

    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(title='jane 777', full_title='jane 777'))

    assert [r.title for r in results] == ['Watch Our Videos'], 'only the full banner is the marker, not any title that starts like it'


@pytest.mark.parametrize(
    ('raw', 'cleaned'),
    [
        ('Coming Soon: Teens In Need', 'Teens In Need'),
        ('coming soon: teens in need', 'teens in need'),
        ('COMING SOON: Teens In Need', 'Teens In Need'),
        ('Coming  Soon : Teens In Need', 'Teens In Need'),
        ('  Coming Soon:Teens In Need', 'Teens In Need'),
        ('Teens In Need', 'Teens In Need'),
        ('The Coming Soon: Sequel', 'The Coming Soon: Sequel'),
    ],
)
def test_the_coming_soon_prefix_is_stripped_only_from_the_front(raw: str, cleaned: str) -> None:
    assert sg_mod._clean_title(raw) == cleaned


@respx.mock
async def test_searches_strip_coming_soon_from_both_kinds_of_row(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _one(*_a: object, **_k: object) -> list[str]:
        return ['https://www.scoreland.com/big-boob-videos/jane/777/']

    monkeypatch.setattr(sg_mod, 'web_search_urls', _one)
    row = (
        '<div class="compact video">'
        '<a class="i-title" href="https://www.scoreland.com/big-boob-videos/mary/888/">coming soon: Mary Scene</a>'
        '<small class="i-model">Mary</small><img src="https://cdn/t.jpg" /></div>'
    )
    respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text=row))
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(
        return_value=httpx.Response(200, text='<html><body><h1>COMING SOON: Jane Scene</h1></body></html>')
    )

    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(title='jane 777', full_title='jane 777'))

    assert sorted(r.title for r in results) == ['Jane Scene', 'Mary Scene']


@respx.mock
async def test_updates_strip_coming_soon_from_the_heading_and_the_packed_title() -> None:
    import json

    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(
        return_value=httpx.Response(200, text='<html><body><h1>Coming Soon: Jane Scene</h1></body></html>')
    )
    detail = await ScoreGroupClient().fetch_scene_detail(json.dumps({'url': 'https://www.scoreland.com/big-boob-videos/jane/777/'}), SITE)
    assert detail is not None
    assert detail.title == 'Jane Scene'

    respx.get('https://www.scoreland.com/big-boob-videos/jane/778/').mock(
        return_value=httpx.Response(200, text='<html><body><h1>Latest Big Boob Videos</h1></body></html>')
    )
    packed = json.dumps({'url': 'https://www.scoreland.com/big-boob-videos/jane/778/', 'title': 'coming soon: Packed Scene', 'actors': 'Jane'})
    latest = await ScoreGroupClient().fetch_scene_detail(packed, SITE)
    assert latest is not None
    assert latest.title == 'Packed Scene', 'the Latest-Videos path takes its title from the packed payload'


_CANON = 'https://www.scoreland.com/big-boob-videos/Alice-Green/45560/'


def _scene_page(canonical: str, title: str = 'Butt Student') -> str:
    return f'<html><head><link rel="canonical" href="{canonical}" /></head><body><h1>{title}</h1></body></html>'


@respx.mock
async def test_two_slugs_for_one_scene_collapse_to_the_published_url(monkeypatch: pytest.MonkeyPatch) -> None:
    guessed = 'https://www.scoreland.com/big-boob-videos/alice-green-sasha-sean/45560/'

    async def _published(*_a: object, **_k: object) -> list[str]:
        return [_CANON]

    monkeypatch.setattr(sg_mod, 'web_search_urls', _published)
    respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text='<html></html>'))
    fetched = {url: respx.get(url).mock(return_value=httpx.Response(200, text=_scene_page(_CANON))) for url in (guessed, _CANON)}

    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(title='alice green sasha sean 45560', full_title='alice green sasha sean 45560'))

    assert [r.scene_url for r in results] == [_CANON], 'the guess and the published url are one scene, named by the site'
    assert fetched[guessed].called and not fetched[_CANON].called, 'the same scene id is not worth a second round trip'


@respx.mock
async def test_a_canonical_that_is_not_a_scene_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _none(*_a: object, **_k: object) -> list[str]:
        return []

    monkeypatch.setattr(sg_mod, 'web_search_urls', _none)
    respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://www.scoreland.com/big-boob-videos/jane/777/').mock(return_value=httpx.Response(200, text=_scene_page('https://www.scoreland.com/home/')))

    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(title='jane 777', full_title='jane 777'))

    assert [r.scene_url for r in results] == ['https://www.scoreland.com/big-boob-videos/jane/777/'], (
        'the soft-404 points its canonical at /home/, which carries no scene id'
    )


@pytest.mark.parametrize(
    ('left', 'right', 'same'),
    [
        ('https://s.test/v/alice-green-sasha-sean/45560/', 'https://s.test/v/Alice-Green/45560/', True),
        ('https://s.test/v/Alice-Green/45560/', 'https://s.test/v/Alice-Green/45561/', False),
        ('https://s.test/v/no-digits/', 'https://s.test/v/NO-DIGITS/', True),
        ('https://s.test/v/no-digits/', 'https://s.test/v/other/', False),
    ],
)
def test_candidates_are_keyed_on_the_scene_id(left: str, right: str, same: bool) -> None:
    assert (sg_mod._scene_key(left) == sg_mod._scene_key(right)) is same


@respx.mock
async def test_a_different_scene_id_is_still_its_own_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    other = 'https://www.scoreland.com/big-boob-videos/Alice-Green/45561/'

    async def _other(*_a: object, **_k: object) -> list[str]:
        return [other]

    monkeypatch.setattr(sg_mod, 'web_search_urls', _other)
    respx.post('https://www.scoreland.com/search-es').mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://www.scoreland.com/big-boob-videos/alice-green/45560/').mock(return_value=httpx.Response(200, text=_scene_page(_CANON, 'Butt Student')))
    respx.get(other).mock(return_value=httpx.Response(200, text=_scene_page(other, 'A Different Scene')))

    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(title='alice green 45560', full_title='alice green 45560'))

    assert sorted(r.title for r in results) == ['A Different Scene', 'Butt Student']


def _series(title: str, actors: list[tuple[str, str]]) -> SceneDetail:
    return SceneDetail(title=title, actors=[ActorResult(name=name, gender=gender) for name, gender in actors])


@pytest.mark.parametrize(
    ('skip_male', 'actors', 'expected'),
    [
        (True, [('Shyla Stylez', ''), ('J.T.', 'male')], 'Funbag Fuckers - Shyla Stylez'),
        (False, [('Shyla Stylez', ''), ('J.T.', 'male')], 'Funbag Fuckers - Shyla Stylez and J.T.'),
        (False, [('Shyla Stylez', ''), ('Danielle Derek', ''), ('Mikey Butders', 'male')], 'Funbag Fuckers - Shyla Stylez, Danielle Derek and Mikey Butders'),
        (True, [('Danielle Derek', '')], 'Funbag Fuckers - Danielle Derek'),
        (True, [('J.T.', 'male')], 'Funbag Fuckers'),
        (True, [], 'Funbag Fuckers'),
    ],
)
def test_a_series_title_carries_the_cast_that_survives_the_male_filter(
    monkeypatch: pytest.MonkeyPatch, skip_male: bool, actors: list[tuple[str, str]], expected: str
) -> None:
    monkeypatch.setattr(sg_mod, 'gender_skip_male_enabled', lambda: skip_male)
    metadata = _series('Funbag Fuckers', actors)
    ScoreGroupClient(SITE)._name_the_series_entry(metadata)
    assert metadata.title == expected


def test_a_one_off_title_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sg_mod, 'gender_skip_male_enabled', lambda: False)
    metadata = _series('Cool Scene', [('Jane Doe', '')])
    ScoreGroupClient(SITE)._name_the_series_entry(metadata)
    assert metadata.title == 'Cool Scene'


def test_every_series_title_is_stored_casefolded() -> None:
    assert sorted(sg_mod._SERIES_TITLES) == sorted(t.casefold() for t in sg_mod._SERIES_TITLES)


def test_a_later_addition_to_the_series_list_is_matched_case_insensitively(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sg_mod, 'gender_skip_male_enabled', lambda: True)
    metadata = _series('HardSCORE 2', [('Angela White', ''), ('Kayla Kleevage', '')])
    ScoreGroupClient(SITE)._name_the_series_entry(metadata)
    assert metadata.title == 'HardSCORE 2 - Angela White and Kayla Kleevage'


def test_the_summary_ignores_the_video_player_descriptions_button() -> None:
    from parsel import Selector

    page = Selector(
        text="""<html><body>
          <div class="vjs-descriptions-button vjs-menu-button vjs-control vjs-button vjs-hidden">
            <div class="vjs-menu"><li class="vjs-menu-item">descriptions off, selected</li></div>
          </div>
          <div class="p-desc p-3" itemprop="articleBody">
            <h2>Alexya Was Born To Play</h2>
            Relaxing on a hammock, gorgeous Alexya soaks in the paradise.
            <a class="accent-text">Read More &#187;</a>
          </div>
        </body></html>"""
    )
    assert sg_mod._summary_text(page) == 'Relaxing on a hammock, gorgeous Alexya soaks in the paradise.'


def test_the_older_bare_desc_template_still_reads() -> None:
    from parsel import Selector

    page = Selector(text='<html><body><div class="desc">Sapphire is unique. She had an amazing rack.</div></body></html>')
    assert sg_mod._summary_text(page) == 'Sapphire is unique. She had an amazing rack.'


def test_a_body_wrapped_in_a_child_element_drops_the_heading_and_the_tail() -> None:
    from parsel import Selector

    page = Selector(
        text="""<html><body><div class="p-desc">
          <h2>Bombshell Returns</h2><p>She bends in ways that should not be legal.</p>
          <a class="accent-text">Read More &#187;</a><h3>Related Tags</h3><a class="btn">Big Tits</a>
        </div></body></html>"""
    )
    assert sg_mod._summary_text(page) == 'She bends in ways that should not be legal.'


def test_a_page_with_no_description_yields_an_empty_summary() -> None:
    from parsel import Selector

    assert sg_mod._summary_text(Selector(text='<html><body><h1>Cool Scene</h1></body></html>')) == ''
