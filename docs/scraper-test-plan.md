# Scraper Test Plan

Every scraper has two layers of verification:

1. **Unit tests** — fast, offline, `respx`-mocked. One test module per source
   module, run on every change and required green before each commit.
2. **Live health checks** — real HTTP, fixture-driven, run on demand. See
   [healthcheck.md](./healthcheck.md).

Plus an optional manual pass in the [`/dev` UI](./dev-ui.md) when you want to eyeball
a scraper against the live site while developing.

## The Gate (Before Every Commit)

```bash
./.venv/Scripts/python.exe -m ruff format <files>
./.venv/Scripts/python.exe -m ruff check <files>     # must pass
./.venv/Scripts/python.exe -m mypy app               # "Success: no issues"
./.venv/Scripts/python.exe -m pytest -q              # full suite green
```

One commit per scraper. After adding a scraper, regenerate the sitelist
(`python -m scripts.generate_sitelist`).

## Unit-Test Conventions

Tests mirror the source tree: a scraper at `phoenixadult/clients/networks/<x>.py` (or
`phoenixadult/clients/scrapers/<x>.py`) gets `tests/clients/networks/test_<x>.py` (resp.
`tests/clients/scrapers/test_<x>.py`). Each module is `respx`-mocked — no network.

A typical module covers **search** and **detail** for one site:

```python
import httpx
import respx

from phoenixadult.clients.base import SearchContext
from phoenixadult.clients.networks.example import ExampleClient
from phoenixadult.registry import find_site

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

## Live Health Checks

The automated regression net for "does this still work against the real site" is
`tests/health/fixtures.json` driven by `python -m scripts.site_health`. Add a
fixture per site (the `/dev` UI's fixture builder emits one ready to paste), then:

```bash
python -m scripts.site_health new      # run just the newly added fixtures
python -m scripts.site_health          # full sweep -> docs/site-health.md
```

See [healthcheck.md](./healthcheck.md) for the fixture schema and the per-field
comparison rules.

## Manual Dev-UI Smoke (Optional)

When iterating on a scraper it's often fastest to watch it live:

1. `NODE_ENV=development python -m phoenixadult.main` → open `http://localhost:3000/dev`.
2. Type a known filename for the site, press Enter — confirm ≥1 result.
3. Click the top result — confirm `title`, `release_date`, `summary` populate.
4. Confirm ≥1 image URL appears and opens; confirm actors + genres (some sites
   legitimately have none — note it).
5. If something's off, expand the capture panel to see the exact HTML the scraper
   saw and re-check your XPath. See [dev-ui.md](./dev-ui.md).

## Protocol per Scraper

1. **Search** — type a known scene title/for that network into the filename box; pick the network in the site dropdown; press Enter. Confirm at least one result row.
2. **Detail** — click the top result. Confirm `title`, `releaseDate`, and `summary` populate.
3. **Images** — confirm at least one image URL appears; open it in a new tab to verify it loads.
4. **Actors + genres** — confirm both populate. Some networks legitimately skip actors (filename-only, direct-URL); note "N/A" in that case.
5. **Collections** — populated only when the site scraper sets them. Don't fail on missing.

## Legend

**Status:** ✅ passes smoke test · ⬜ not yet tested · ⚠️ partial — see notes · ❌ broken or removed — see notes

**Method** (from the registry registration): `enhanced` = title + + date + · `limited` = title / · `exact` = or direct-URL only

## Progress

**12** ✅ passing · **3** ❌ removed · **159** ⬜ remaining — **174** total

## Providers

### #

| | Provider | Method | Notes |
|---|---|---|---|
| ✅ | 5K Porn | limited | |

### A

| | Provider | Method | Notes |
|---|---|---|---|
| ✅ | Abby Winters | enhanced | |
| ✅ | Adult Empire | enhanced | |
| ✅ | Adult Empire Cash | |
| ✅ | Adult Prime | enhanced | |
| ✅ | Allure Media | limited | |
| ✅ | ALS Angels | exact | |
| ✅ | AmourAngels | exact | |
| ✅ | AnalVids | enhanced | |
| ❌ | Angela White | — | Removed: site no longer exists |
| ❌ | ArchAngel | — | Removed: site changes |
| ❌ | ATKGirlfriends | — | Removed: paywall |

### B

| | Provider | Method | Notes |
|---|---|---|---|
| ✅ | BaDoink VR | enhanced | |
| ⬜ | BAMVisions | limited | |
| ⬜ | Bang! | limited | |
| ⬜ | Bel Ami Online | exact | |
| ⬜ | BellaPass | limited | slug |
| ⬜ | Bellesa | enhanced | |
| ⬜ | Black PayBack | limited | |
| ⬜ | BlurredMedia | enhanced | |
| ⬜ | Bound Honeys | limited | |
| ⬜ | Brand New Amateurs | limited | |

### C

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Caramel Cash | exact | |
| ⬜ | Caribbeancom | exact | |
| ⬜ | Cherry Pimps | enhanced | |
| ⬜ | Clips4Sale | exact | |
| ⬜ | ClubFilly | exact | |
| ⬜ | Colette | enhanced | |
| ⬜ | Couples Cinema | enhanced | |
| ⬜ | Cumbizz | exact | |
| ⬜ | CumLouder | exact | |
| ✅ | Czech Authentic Videos | limited | |
| ⬜ | CzechVR | enhanced | |

### D

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | DarkRoomVR | limited | |
| ⬜ | Data18 Porn Database | enhanced | |
| ⬜ | Deranged Dollars | enhanced | |
| ⬜ | Desperate Amateurs | limited | |
| ⬜ | DickDrainers | enhanced | |
| ⬜ | Dirty Flix | enhanced | |
| ⬜ | Dirty Hard Drive | enhanced | |
| ⬜ | Dorcel Vision | limited | |

### E

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Evolved Fights Network | enhanced | |
| ⬜ | Explicite Art | limited | |

### F

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | FAKings | enhanced | |
| ⬜ | Family Therapy | enhanced | |
| ⬜ | Femdom Empire | enhanced | |
| ⬜ | Femjoy | enhanced | |
| ⬜ | Finishes The Job | limited | |
| ⬜ | First Anal Quest | enhanced | |
| ⬜ | First Time Videos | enhanced | |
| ⬜ | Fitting-Room | exact | |
| ⬜ | FuckingAwesome | enhanced | |
| ⬜ | FuelVirtual | enhanced | |
| ⬜ | Full Porn Network | limited | |

### G

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Gamma | enhanced | |
| ⬜ | GASM | enhanced | |
| ⬜ | Girls Rimming | enhanced | |
| ⬜ | GirlsOutWest | enhanced | |
| ⬜ | Grooby | enhanced | |

### H

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Heavy on Hotties | enhanced | |
| ⬜ | Hegre | enhanced | |
| ⬜ | High-Tech VR | exact | |
| ⬜ | Holly Randall Productions | limited | |
| ⬜ | HoloGirlsVR | enhanced | |
| ⬜ | HotwifeXXX | enhanced | |
| ⬜ | HuCows | enhanced | |

### I

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | InterracialPass | enhanced | |
| ⬜ | Intersec | enhanced | |
| ⬜ | InTheCrack | limited | |

### J

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Jacquie Et Michel TV | enhanced | |
| ⬜ | JavBus | enhanced | |
| ⬜ | JAVDatabase | enhanced | |
| ⬜ | JAVLibrary | enhanced | |
| ⬜ | Jesse Loads Monster Facials | enhanced | |
| ⬜ | Jules Jordan | enhanced | |
| ⬜ | JVR Porn | enhanced | |

### K

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Karups | enhanced | |
| ⬜ | Kelly Madison | enhanced | |
| ⬜ | Killergram | exact | |
| ⬜ | Kin8tengoku | enhanced | |
| ⬜ | Kink | enhanced | |

### L

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | LittleCaprice | enhanced | |
| ⬜ | LoveHerFilms | enhanced | |
| ⬜ | Lust Reality | enhanced | |
| ⬜ | Lustomic | exact | |

### M

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | ManyVids | exact | |
| ⬜ | Marc Dorcel | enhanced | |
| ⬜ | Meana Wolf | limited | |
| ⬜ | Melena Maria Rya | exact | |
| ⬜ | Melone Challenge | enhanced | |
| ⬜ | MetadataAPI | enhanced | |
| ⬜ | MetArt Network | enhanced | |
| ⬜ | MissaX | limited | |
| ⬜ | ModelCentro Network | enhanced | |
| ⬜ | Mom Comes First | enhanced | |
| ⬜ | Mom POV | enhanced | |
| ⬜ | My Dirty Hobby | enhanced | |

### N

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Naughty America | enhanced | |
| ⬜ | Naughty America Other Sites | limited | |
| ⬜ | New Sensations | enhanced | |
| ⬜ | Nubiles | enhanced | |
| ⬜ | NVG Network | exact | |

### P

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Penthouse Gold | enhanced | |
| ⬜ | Perfect Gonzo | enhanced | |
| ⬜ | PervCity | limited | |
| ⬜ | PJGirls | enhanced | |
| ⬜ | PKJ Media | limited | |
| ⬜ | Playboy Plus | enhanced | |
| ⬜ | PlumperPass | enhanced | |
| ⬜ | Pornbox | enhanced | |
| ⬜ | PornCZ | limited | |
| ⬜ | Porndoe Premium | enhanced | |
| ⬜ | PornPros | enhanced | |
| ⬜ | Pornstar Platinum | enhanced | |
| ⬜ | PornWorld | enhanced | |
| ⬜ | POVR | limited | |
| ⬜ | Private | enhanced | |
| ⬜ | Project1Service | enhanced | |
| ⬜ | Puba | limited | |
| ⬜ | Puffy Network | limited | |
| ⬜ | PureCFNM | exact | |
| ⬜ | Putalocura | enhanced | |

### Q

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | QueenSnake | exact | |

### R

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Radical Cash | enhanced | |
| ⬜ | Radical Cash Other | enhanced | |
| ⬜ | Reality Lovers | enhanced | |
| ⬜ | ReidMyLips | exact | |
| ⬜ | Reptyle | enhanced | |
| ⬜ | Romero Multimedia | limited | |

### S

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Screwbox | limited | |
| ⬜ | ScrewMeToo | enhanced | |
| ⬜ | Sex Like Real | enhanced | |
| ⬜ | SexMex | enhanced | |
| ⬜ | Sicflics | enhanced | |
| ⬜ | SinsLife | limited | |
| ⬜ | SinX | limited | |
| ⬜ | Spizoo | limited | |
| ⬜ | StasyQ | exact | |
| ⬜ | Step Secrets | enhanced | |
| ⬜ | Stepped Up Media | enhanced | |
| ⬜ | Strapon Cum | exact | |
| ✅ | Strike3 | enhanced | |
| ⬜ | Swallow Bay | exact | |

### T

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Teen Mega World | enhanced | |
| ⬜ | TeenCoreClub | enhanced | |
| ⬜ | Teeny Taboo | enhanced | |
| ⬜ | The Score Group | enhanced | |
| ⬜ | Thick Cash | limited | |
| ⬜ | TwoTGirls | limited | |

### U

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | Ultrafilms | limited | |
| ⬜ | Unzip VR | enhanced | |

### V

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | VIP4K | enhanced | |
| ⬜ | VIPissy | limited | |
| ⬜ | VirtualRealPorn | exact | |
| ⬜ | VirtualTaboo | limited | |
| ⬜ | Vivid Network | enhanced | |
| ⬜ | VNA Network | enhanced | |
| ⬜ | VogoV | limited | |
| ⬜ | VR Latina | enhanced | |
| ⬜ | VRAllure | exact | |
| ⬜ | VRPFilms | enhanced | |

### W

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | WakeUpNFuck | limited | |
| ⬜ | Wankz | limited | |
| ⬜ | WankzVR | enhanced | |
| ⬜ | Watch4Beauty | limited | |
| ⬜ | We Are Hairy | enhanced | |
| ⬜ | WoodmanCastingX | limited | |
| ⬜ | WowNetwork | enhanced | |

### X

| | Provider | Method | Notes |
|---|---|---|---|
| ⬜ | X-Art | enhanced | |
| ⬜ | XConfessions | limited | |
| ⬜ | Xev Unleashed | enhanced | |
| ⬜ | Xillimite | limited | |
| ⬜ | XVirtual | limited | |
