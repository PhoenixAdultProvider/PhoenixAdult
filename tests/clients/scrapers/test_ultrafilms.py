from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.ultrafilms import UltrafilmsClient
from app.registry import find_site

SITE = find_site('Ultrafilms')
assert SITE is not None


def _row(uid: str, title: str, href: str, thumb: str) -> str:
    return f'<main><article data-video-uid="{uid}"><a title="{title}" href="{href}">x</a><img data-src="{thumb}" /></article></main>'


@respx.mock
async def test_search_quoted_hit_skips_fallback() -> None:
    quoted = 'https://www.ultrafilms.xxx/?s=%22' + quote('wild scene') + '%22'
    unquoted = respx.get('https://www.ultrafilms.xxx/?s=' + quote('wild scene')).mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get(quoted).mock(
        return_value=httpx.Response(200, text=f'<html><body>{_row("1", "Wild Scene", "/scene/wild", "https://cdn/uf/thumb.jpg")}</body></html>')
    )
    results: list[SearchResult] = []
    await UltrafilmsClient().search(results, SearchContext(title='wild scene', encoded=quote('wild scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://www.ultrafilms.xxx/scene/wild'
    assert not unquoted.called


@respx.mock
async def test_search_falls_back_to_unquoted() -> None:
    quoted = 'https://www.ultrafilms.xxx/?s=%22' + quote('nothing') + '%22'
    unquoted = 'https://www.ultrafilms.xxx/?s=' + quote('nothing')
    respx.get(quoted).mock(return_value=httpx.Response(200, text='<html><body><main></main></body></html>'))
    respx.get(unquoted).mock(
        return_value=httpx.Response(200, text=f'<html><body>{_row("2", "Nothing Found", "/scene/nf", "https://cdn/uf/nf.jpg")}</body></html>')
    )
    results: list[SearchResult] = []
    await UltrafilmsClient().search(results, SearchContext(title='nothing', encoded=quote('nothing'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Nothing Found'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.ultrafilms.xxx/scene/wild'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="entry-title">Page Title — IGNORED</h1>
              <main><article>
                <h1 class="entry-title">Wild Scene</h1>
                <meta property="article:published_time" content="2024-01-05T12:30:00Z" />
                <div class="video-description"><div class="desc"><p>A blurb.</p></div></div>
                <div class="tags-list">
                  <a href="/anal"><i class="fa fa-folder-open"></i> Anal Movies</a>
                  <a href="/hardcore"><i class="fa fa-folder-open"></i> Hardcore</a>
                  <a href="/random"><i class="fa fa-clock"></i> Not a genre</a>
                </div>
                <div id="video-actors"><a>Jane Doe</a><a>Mary Roe</a><a>Mike Jones</a></div>
              </article></main>
            </body></html>""",
        )
    )
    detail = await UltrafilmsClient().fetch_scene_detail(f'{url}||https://cdn/uf/thumb.jpg', SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Ultrafilms'
    assert detail.tagline == 'Ultrafilms'
    assert detail.collections == ['Ultrafilms']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['anal', 'hardcore', 'Threesome']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'Mary Roe', 'Mike Jones']
    assert detail.raw_image_urls == ['https://cdn/uf/thumb.jpg']
