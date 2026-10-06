from __future__ import annotations

import json

import httpx
import respx

from phoenixadult.clients.networks.kink import KinkClient, _kink_tagline, _title_fits
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

SITE = find_site('Kink')
CHANNEL = find_site('Hogtied')
assert SITE is not None and CHANNEL is not None

_MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def _ld(**fields: str) -> str:
    return f'<script type="application/ld+json">{json.dumps({"@type": "VideoObject", **fields})}</script>'


def _card(shoot_id: int, title: str, date: str) -> str:
    year, month, day = date.split('-')
    shown = f'{_MONTHS[int(month) - 1]} {int(day)}, {year}'
    return (
        f'<div class="card shoot-thumbnail"><a href="/shoot/{shoot_id}" title="{title}"><img></a>'
        f'<div class="shoot-thumbnail-footer"><span>Hogtied</span><span>{shown}</span><span>98%</span></div></div>'
    )


def _results_page(cards: list[str], total: int) -> str:
    return f'<html><body><h1>Results</h1> <span class="text-primary">{total:,}</span>{"".join(cards)}</body></html>'


@respx.mock
async def test_a_shoot_id_reads_the_clean_title_and_date_from_json_ld() -> None:
    url = 'https://www.kink.com/shoot/555'
    page = _ld(name='Pass The Pussy', uploadDate='2020-04-30T00:00:00+00:00') + '<h1>Pass The P****</h1>'
    respx.get(url).mock(return_value=httpx.Response(200, text=page))
    results: list[SearchResult] = []
    await KinkClient().search(results, search_context(SITE, 'pass', scene_id='555'))
    assert [(r.title, r.display_date, r.score, r.scene_url) for r in results] == [('Pass The Pussy', '2020-04-30', 100, url)]


@respx.mock
async def test_a_shoot_id_falls_back_to_the_scene_page_html() -> None:
    url = 'https://www.kink.com/shoot/556'
    legend = '<div class="shoot-detail-legend"><span class="text-muted">Hogtied</span><span class="text-muted ms-2">Mar 4, 2021</span></div>'
    page = f'<h1 class="fs-0">Cool Scene</h1>{legend}'
    respx.get(url).mock(return_value=httpx.Response(200, text=page))
    results: list[SearchResult] = []
    await KinkClient().search(results, search_context(SITE, 'cool scene', scene_id='556'))
    assert [(r.title, r.display_date) for r in results] == [('Cool Scene', '2021-03-04')]


@respx.mock
async def test_a_retired_shoot_id_landing_on_a_listing_is_not_offered() -> None:
    respx.get('https://www.kink.com/shoot/15393').mock(return_value=httpx.Response(200, text='<h1>Channels</h1><div class="channel-list"></div>'))
    results: list[SearchResult] = []
    await KinkClient().search(results, search_context(SITE, 'old', scene_id='15393'))
    assert results == []


@respx.mock
async def test_every_request_carries_the_age_gate_cookie() -> None:
    route = respx.get('https://www.kink.com/shoot/557').mock(return_value=httpx.Response(200, text=_ld(name='X')))
    await KinkClient().search([], search_context(SITE, 'x', scene_id='557'))
    cookie = route.calls[0].request.headers['cookie']
    assert 'age_gate_accepted=1' in cookie and 'viewing-preferences=straight%2Cgay' in cookie


@respx.mock
async def test_a_title_search_reads_the_new_cards_and_scores_by_title() -> None:
    page = _results_page([_card(1, 'Cool Scene', '2026-01-02'), _card(2, 'Other Thing', '2026-01-01')], 2)
    route = respx.get('https://www.kink.com/search').mock(return_value=httpx.Response(200, text=page))
    results: list[SearchResult] = []
    await KinkClient().search(results, search_context(SITE, 'cool scene'))
    assert route.calls[0].request.url.params['page'] == '1'
    assert [r.title for r in results] == ['Cool Scene', 'Other Thing']
    assert results[0].scene_url == 'https://www.kink.com/shoot/1' and results[0].display_date == '2026-01-02'
    assert results[0].score > results[1].score


@respx.mock
async def test_a_dated_search_binary_searches_the_newest_first_pages() -> None:
    dates = [f'2026-{12 - i // 28:02d}-{28 - i % 28:02d}' for i in range(24 * 10)]
    pages = {n: [_card(1000 - i, f'Scene {i}', dates[i]) for i in range((n - 1) * 24, n * 24)] for n in range(1, 11)}
    target_index = 24 * 6 + 5

    def page(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params['page'])
        return httpx.Response(200, text=_results_page(pages.get(number, []), 240))

    route = respx.get('https://www.kink.com/search').mock(side_effect=page)
    results: list[SearchResult] = []
    ctx = search_context(CHANNEL, f'Scene {target_index}', search_date=dates[target_index])
    await KinkClient().search(results, ctx)
    best = max(results, key=lambda r: r.score)
    assert best.title == f'Scene {target_index}' and best.score == 100
    assert len(route.calls) <= 5, 'pages are probed by date, not walked one by one'


@respx.mock
async def test_a_channel_falls_back_to_its_full_listing_when_the_text_search_is_empty() -> None:
    queries: list[str] = []

    def page(request: httpx.Request) -> httpx.Response:
        query = request.url.params['q']
        queries.append(query)
        cards = [] if query else [_card(9, 'Is It Love?', '2024-05-06')]
        return httpx.Response(200, text=_results_page(cards, len(cards)))

    respx.get('https://www.kink.com/search').mock(side_effect=page)
    results: list[SearchResult] = []
    await KinkClient().search(results, search_context(CHANNEL, 'Is It Love', search_date='2024-05-06'))
    assert queries == ['Is It Love', '']
    assert [(r.title, r.score) for r in results] == [('Is It Love?', 100)]


@respx.mock
async def test_the_network_wide_site_never_browses_the_full_listing() -> None:
    queries: list[str] = []

    def page(request: httpx.Request) -> httpx.Response:
        queries.append(request.url.params['q'])
        return httpx.Response(200, text=_results_page([], 0))

    respx.get('https://www.kink.com/search').mock(side_effect=page)
    await KinkClient().search([], search_context(SITE, 'Is It Love', search_date='2024-05-06'))
    assert queries == ['Is It Love']


def test_a_card_title_fits_with_censored_words() -> None:
    assert _title_fits('pass the pussy', 'Pass The P****')
    assert _title_fits('', 'anything')
    assert not _title_fits('rope bondage queen', 'Totally Different Scene')


@respx.mock
async def test_detail_prefers_json_ld_and_survives_censoring() -> None:
    url = 'https://www.kink.com/shoot/555'
    description = 'A **bold** take with [a link](https://kink.com/x).\nSecond line.'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text=f"""<html><body>{_ld(name='Pass The Pussy', description=description, uploadDate='2020-04-30T00:00:00+00:00')}
              <nav><a href="/tag/menu-item">Menu Item</a></nav>
              <h1>Pass The P****</h1>
              <div class="shoot-detail-legend">
                <a href="/channel/bound-gang-bangs">B**** G*** B****</a>
                <span class="text-muted ms-2">Apr 30, 2020</span>
              </div>
              <div class="container"><p>Categories</p>
                <a href="/tag/double-anal-bdsm">D***** A***,</a>
                <a href="/tag/rope">Rope</a>
              </div>
              <span class="text-primary"><a href="/model/jane">Jane Doe</a></span>
              <video poster="https://cdn/safe-images/blur.jpg"></video>
              <img class="gallery-img" data-image-file="https://cdn/full/1.jpg">
            </body></html>""",
        )
    )
    respx.get('https://www.kink.com/model/jane').mock(
        return_value=httpx.Response(
            200, text='<div class="kink-slider-images"><img src="https://cdn/safe-images/x.jpg"><img data-src="https://cdn/jane.jpg?sig=1"></div>'
        )
    )
    detail = await KinkClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Pass The Pussy'
    assert detail.summary == 'A bold take with a link. Second line.'
    assert detail.release_date == '2020-04-30'
    assert detail.tagline == 'Bound Gangbangs'
    assert detail.genres[:2] == ['Double Anal', 'Rope'], 'only the Categories box counts, censored tags rebuilt from the slug'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg?sig=1'
    assert detail.art == ['https://cdn/full/1.jpg']


@respx.mock
async def test_detail_falls_back_to_the_html() -> None:
    url = 'https://www.kink.com/shoot/556'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="fs-0">Cool Scene</h1>
              <div class="description"><span class="fw-200">A<br>summary.</span></div>
              <div class="shoot-detail-legend">
                <a href="/channel/hogtied">Hogtied</a>
                <span class="text-muted">Hogtied</span><span class="text-muted ms-2">Mar 4, 2021</span>
              </div>
              <span class="director-name"><a href="/model/dir">Director</a></span>
              <video poster="https://cdn/poster.jpg?token=x"></video>
            </body></html>""",
        )
    )
    respx.get('https://www.kink.com/model/dir').mock(
        return_value=httpx.Response(200, text='<div class="biography-container"><img src="https://cdn/dir.jpg" /></div>')
    )
    detail = await KinkClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert (detail.title, detail.summary, detail.tagline, detail.studio, detail.release_date) == ('Cool Scene', 'A summary.', 'Hogtied', 'Kink', '2021-03-04')
    assert detail.directors is not None and detail.directors[0].photo_url == 'https://cdn/dir.jpg'
    assert detail.art == ['https://cdn/poster.jpg?token=x']


def test_kink_tagline() -> None:
    assert _kink_tagline('whippedass', 'Kink') == 'Whipped Ass'
    assert _kink_tagline('fetishnetworkmale', 'Kink') == 'Fetish Network Male'
    assert _kink_tagline('unknown', 'Kink') == 'Kink'
