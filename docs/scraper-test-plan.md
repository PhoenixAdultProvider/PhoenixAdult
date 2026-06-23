# Scraper Test Plan

Every scraper has two layers of verification:

1. **Unit tests** — fast, offline, `respx`-mocked. One test module per source
   module, run on every change and required green before each commit.
2. **Live health checks** — real HTTP, fixture-driven, run on demand. See
   [healthcheck.md](./healthcheck.md).

Plus an optional manual pass in the [`/dev` UI](./dev-ui.md) when you want to eyeball
a scraper against the live site while developing.

## The gate (before every commit)

```bash
./.venv/Scripts/python.exe -m ruff format <files>
./.venv/Scripts/python.exe -m ruff check <files>     # must pass
./.venv/Scripts/python.exe -m mypy app               # "Success: no issues"
./.venv/Scripts/python.exe -m pytest -q              # full suite green
```

One commit per scraper. After adding a scraper, regenerate the sitelist
(`python -m scripts.generate_sitelist`).

## Unit-test conventions

Tests mirror the source tree: a scraper at `app/clients/networks/<x>.py` (or
`app/clients/scrapers/<x>.py`) gets `tests/clients/networks/test_<x>.py` (resp.
`tests/clients/scrapers/test_<x>.py`). Each module is `respx`-mocked — no network.

A typical module covers **search** and **detail** for one site:

```python
import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.example import ExampleClient
from app.registry import find_site

SITE = find_site('Example Site')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    respx.get('https://example.com/search?q=cool+scene').mock(return_value=httpx.Response(200, text='<...>'))
    results = await ExampleClient().search(_ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    # curID round-trips back to the payload the detail step expects:
    assert ExampleClient().decode(results[0].cur_id) == 'https://example.com/v/7'


@respx.mock
async def test_detail() -> None:
    url = 'https://example.com/v/7'
    respx.get(url).mock(return_value=httpx.Response(200, text='<...>'))
    detail = await ExampleClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.studio == 'Example'
    assert detail.genres == ['Teen']
    assert detail.actors is not None and detail.actors[0].name == 'Jane Doe'
    assert detail.raw_image_urls == ['https://cdn/p.jpg']
```

Conventions that recur:

- **`find_site('<exact registry name>')`** resolves the `ResolvedSiteInfo` to drive
  the client; `assert SITE is not None` at module load surfaces a registration
  mistake immediately.
- **Mock by exact URL** (`respx.get(url)`) when you know it, or
  `respx.get(url__startswith=...)` for query-string-bearing search URLs. respx
  raises on any unmocked request, so mock every fetch the client makes (including
  actor/photo sub-pages and fallback lookups).
- **`@respx.mock` + `async def test_...`** — the suite runs under asyncio; clients
  are async.
- **Assert the mapped fields**, not internals: `title`, `summary`, `studio`,
  `tagline`, `collections`, `release_date`, `genres`, `actors[*].name/photo_url/
  gender`, `directors`, `raw_image_urls`.
- **curID round-trip** — decode the search result's `cur_id` and assert it's exactly
  what `fetch_scene_detail` / `load_scene_context` consumes (URL, or the packed
  `<url>|<date>|...` tail). This catches pack/unpack drift.
- **Patch web search** when a client calls it: `monkeypatch.setattr(mod,
  'web_search_urls', _stub)` (or `web_search_available`) so tests stay deterministic
  and offline.
- **Cover real quirks** the port introduced — date formats, de-censoring, per-site
  genre tables, `bic_`/placeholder fallbacks, scene-ID gating — with a dedicated
  assertion or a small extra test.

Keep fixtures (the HTML/JSON strings) minimal: include only the nodes the selectors
read. Split long literal HTML across concatenated strings to stay under the line
limit.

## Live health checks

The automated regression net for "does this still work against the real site" is
`tests/health/fixtures.json` driven by `python -m scripts.site_health`. Add a
fixture per site (the `/dev` UI's fixture builder emits one ready to paste), then:

```bash
python -m scripts.site_health new      # run just the newly added fixtures
python -m scripts.site_health          # full sweep -> docs/site-health.md
```

See [healthcheck.md](./healthcheck.md) for the fixture schema and the per-field
comparison rules.

## Manual dev-UI smoke (optional)

When iterating on a scraper it's often fastest to watch it live:

1. `uvicorn app.main:app --reload` → open `http://localhost:3000/dev`.
2. Type a known filename for the site, press Enter — confirm ≥1 result.
3. Click the top result — confirm `title`, `release_date`, `summary` populate.
4. Confirm ≥1 image URL appears and opens; confirm actors + genres (some sites
   legitimately have none — note it).
5. If something's off, expand the capture panel to see the exact HTML the scraper
   saw and re-check your XPath. See [dev-ui.md](./dev-ui.md).
