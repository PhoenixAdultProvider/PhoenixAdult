from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.tonightsgirlfriend import TonightsGirlfriendClient
from app.registry import find_site

SITE = find_site('Tonights Girlfriend')
assert SITE is not None


def _row(href: str, actors: str, date: str) -> str:
    anchors = ''.join(f'<a href="/pornstar/{n.strip().lower().replace(" ", "-")}/">{n.strip()}</a>' for n in actors.split(','))
    return f'<div class="panel-body"><a href="{href}">Scene</a><span class="scene-actors">{anchors}</span><span class="scene-date">{date}</span></div>'


@respx.mock
async def test_search_paginates_stops_short() -> None:
    slug = 'jane-doe'
    p1 = '\n'.join(_row(f'/scene/wild-{i}?token=x', 'Jane Doe', '2024-01-01') for i in range(9))
    p2 = _row('/scene/wild-9', 'Jane Doe', '2024-01-10')
    respx.get(f'https://www.tonightsgirlfriend.com/pornstar/{slug}/?p=1').mock(return_value=httpx.Response(200, text=f'<html><body>{p1}</body></html>'))
    respx.get(f'https://www.tonightsgirlfriend.com/pornstar/{slug}/?p=2').mock(return_value=httpx.Response(200, text=f'<html><body>{p2}</body></html>'))
    p3 = respx.get(f'https://www.tonightsgirlfriend.com/pornstar/{slug}/?p=3').mock(return_value=httpx.Response(200, text='<html></html>'))
    results = await TonightsGirlfriendClient().search(SearchContext(title='jane doe and john smith', encoded='x', search_site=SITE.name, site_info=SITE))
    assert len(results) == 10
    assert results[0].scene_url == 'https://www.tonightsgirlfriend.com/scene/wild-0'
    assert results[0].title == 'Jane Doe'
    assert results[0].release_date == '2024-01-01'
    assert not p3.called  # short page 2 halts pagination


@respx.mock
async def test_search_multi_actor_title() -> None:
    respx.get('https://www.tonightsgirlfriend.com/pornstar/jane-doe/?p=1').mock(
        return_value=httpx.Response(200, text=f'<html><body>{_row("/scene/threesome", "Jane Doe, Mary Roe", "2024-03-05")}</body></html>')
    )
    results = await TonightsGirlfriendClient().search(SearchContext(title='jane doe', encoded='x', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Jane Doe, Mary Roe'


@respx.mock
async def test_detail_linked_plus_residue() -> None:
    url = 'https://www.tonightsgirlfriend.com/scene/wild-night'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <p class="grey-performers"><a href="/pornstar/jane-doe/">Jane Doe</a>, Mike Jones</p>
              <p class="scene-description">A wild evening.</p>
              <img class="playcard" src="//cdn.tg.com/scenes/abc/scene/image/360x200cdynamic.jpg" />
            </body></html>""",
        )
    )
    respx.get('https://www.tonightsgirlfriend.com/pornstar/jane-doe/').mock(
        return_value=httpx.Response(200, text='<html><body><div class="performer-details"><img src="//cdn.tg.com/jane.jpg" /></div></body></html>')
    )
    detail = await TonightsGirlfriendClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Jane Doe'
    assert detail.summary == 'A wild evening.'
    assert detail.studio == 'Naughty America'
    assert detail.tagline == "Tonight's Girlfriend"
    assert detail.collections == ["Tonight's Girlfriend"]
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.tg.com/jane.jpg'), ('Mike Jones', '')]
    assert detail.genres == ['Girlfriend Experience', 'Hotel', 'Pornstar', 'Pornstar Experience']
    assert detail.raw_image_urls == [
        'https://cdn.tg.com/scenes/abc/scene/image/360x200cdynamic.jpg',
        'https://cdn.tg.com/scenes/abc/scene/vertical/390x590cdynamic.jpg',
    ]


@respx.mock
async def test_detail_threesome_bgg() -> None:
    url = 'https://www.tonightsgirlfriend.com/scene/bgg'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <p class="grey-performers"><a href="/pornstar/jane-doe/">Jane Doe</a>, <a href="/pornstar/mary-roe/">Mary Roe</a>, Mike Jones</p>
              <img class="playcard" src="//cdn.tg.com/p.jpg" />
            </body></html>""",
        )
    )
    respx.get('https://www.tonightsgirlfriend.com/pornstar/jane-doe/').mock(
        return_value=httpx.Response(200, text='<html><body><div class="performer-details"><img src="//cdn.tg.com/jane.jpg" /></div></body></html>')
    )
    respx.get('https://www.tonightsgirlfriend.com/pornstar/mary-roe/').mock(
        return_value=httpx.Response(200, text='<html><body><div class="performer-details"><img src="//cdn.tg.com/mary.jpg" /></div></body></html>')
    )
    detail = await TonightsGirlfriendClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.genres == ['Girlfriend Experience', 'Hotel', 'Pornstar', 'Pornstar Experience', 'Threesome', 'BGG']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'Mary Roe', 'Mike Jones']


@respx.mock
async def test_detail_threesome_bbg() -> None:
    url = 'https://www.tonightsgirlfriend.com/scene/bbg'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <p class="grey-performers"><a href="/pornstar/jane-doe/">Jane Doe</a>, Mike Jones, Steve Black</p>
              <img class="playcard" src="//cdn.tg.com/p.jpg" />
            </body></html>""",
        )
    )
    respx.get('https://www.tonightsgirlfriend.com/pornstar/jane-doe/').mock(
        return_value=httpx.Response(200, text='<html><body><div class="performer-details"><img src="//cdn.tg.com/jane.jpg" /></div></body></html>')
    )
    detail = await TonightsGirlfriendClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.genres[-2:] == ['Threesome', 'BBG']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'Mike Jones', 'Steve Black']
