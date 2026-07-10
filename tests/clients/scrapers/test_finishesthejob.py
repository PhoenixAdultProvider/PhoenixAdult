from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.finishesthejob import FinishesTheJobClient
from app.registry import find_site

SITE = find_site('Mano Job')
assert SITE is not None


@respx.mock
async def test_search_parses_scene_cards() -> None:
    url = 'https://www.finishesthejob.com/search?search=hand%20job'
    html = """<html><body>
      <div class="scene">
        <a href="/scene/manojob/hand-job/">x</a>
        <h3 itemprop="name">Hand Job</h3>
        <div class="card-footer"><a href="/scene/manojob/hand-job/">ManoJob</a></div>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results = await FinishesTheJobClient().search(SearchContext(title='hand job', encoded='hand%20job', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Hand Job'
    assert results[0].scene_url == 'https://www.finishesthejob.com/scene/manojob/hand-job/'
    assert results[0].subsite == 'ManoJob'


@respx.mock
async def test_detail_fields_actors_genres_images() -> None:
    url = 'https://www.finishesthejob.com/scene/manojob/hand-job/'
    html = """<html><body>
      <span itemprop="name">Hand Job</span>
      <p itemprop="description">A blurb.</p>
      <h2>Starring <a>Alice</a> <a>Bob</a></h2>
      <p>Categories <a>Handjob</a><a>POV</a></p>
      <video poster="/poster.jpg"></video>
      <div class="first-set"><img alt="Hand Job" src="https://cdn.ftj.com/g1.jpg"><img alt="Other" src="/skip.jpg"></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    detail = await FinishesTheJobClient().fetch_scene_detail(f'{url}|2021-04-04', SITE)
    assert detail is not None
    assert detail.title == 'Hand Job'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Finishes The Job'
    assert detail.tagline == 'Mano Job'
    assert detail.collections == ['Mano Job']
    assert detail.release_date == '2021-04-04'
    assert [a.name for a in detail.actors] == ['Alice', 'Bob']
    assert detail.genres == ['Handjob', 'POV']
    assert detail.raw_image_urls == ['https://www.finishesthejob.com/poster.jpg', 'https://cdn.ftj.com/g1.jpg']
