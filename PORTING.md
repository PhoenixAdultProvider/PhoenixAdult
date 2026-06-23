# Porting checklist

Tracks the port of the legacy bundle (`../PhoenixAdult.bundle`, the source of
reusable logic/data and the scraper behaviour to match) into this FastAPI app.

Legend: `[x]` done · `[~]` partial / placeholder in repo · `[ ]` not started.

Rule reminders: **every scraper is hand-written** (no shared `JsonClient`/per-network
client); shared *helpers* (`GraphQLClient`, `html_helpers`, image adapters) are
fine. Tabular reference data lives in `_data/json/`. Confirm
`PROVIDER_SEARCH_METHOD`/`PROVIDER_SEARCH_NOTES` against the legacy sitelist.
Always read the legacy bundle before porting, and verify selectors against the
site's current markup.

**HTML extraction uses XPath.** parsel's `Selector.xpath()` is lxml-backed, so
clients and people sources parse with XPath, ported close to the legacy bundle's
expressions — then checked against the live page in case the markup has since
changed.

Tests mirror the source tree under `tests/` (e.g. `tests/utils/test_processors.py`,
`tests/routes/test_provider.py`), one test module per source module.

---

## Done — framework foundation

- [x] App factory + entrypoint (`app/app_factory.py`, `app/main.py`)
- [x] Config: env, env catalog, runtime overrides (`app/config/`)
- [x] Registry: `SiteInfo`, provider/site tables, lookups (`app/registry/`)
- [x] Base `Client` + field-hook orchestrator (`app/clients/base.py`)
- [x] Scraper-type → client dispatch (`app/clients/__init__.py`, `routes/scraper_router.py`)
- [x] Services: match + metadata (`app/services/`)
- [x] Mapper: results → Plex models (`app/mappers/metadata_mapper.py`)
- [x] Routes: provider, image proxy, config UI, dev UI (`app/routes/`)
- [x] Admin auth guard (`app/routes/env_auth.py`)
- [x] Logging + per-request capture + orchestrator logs (`app/utils/logging/`)
- [x] HTTP client (`app/utils/http/client.py`)
- [x] SSRF guard (`app/utils/http/ssrf_guard.py`)
- [x] Helpers: curID codec, slug, dates, scoring, search-result builder (`app/utils/helpers/`)
- [x] Processors: abbreviations (full data), filename parser, search query, similarity
- [x] Images: classifier, fetcher (Pillow), referers
- [x] Cloudflare quick-tunnel launcher (`scripts/start-with-tunnel.ps1`)

---

## Tier 1 — core output utilities (every scraper depends on these)

Port these first so scrapers emit correct metadata from day one.

- [x] Genres DB — full pipeline (`app/utils/genres/`)
  - [x] Synonym/canonical map (`_data/json/genres.json`; legacy `PAdatabaseGenres.py`)
  - [x] Skip lists (exact + partial, in `genres.json`)
- [x] Title casing — full engine (`app/utils/processors/title_case.py`)
  - [x] Exception / acronym / size / per-site tables + manual corrections + post-process pass
- [x] Studio-name normalization (`processors/studio_name.py` + `_data/json/studios.json`)

## Tier 2 — people (actor / director / producer resolution) — DONE

Replace the pass-through placeholder in `app/utils/people/`.

- [x] Photo source base (`sources/_http.py`) + source registry (`sources/__init__.py`)
- [x] localStorage source
- [x] AdultDvdEmpire source
- [x] Freeones source
- [x] IAFD source (plain HTTP; yields nothing against Cloudflare until a bypass is wired)
- [x] Indexxx source
- [x] Boobpedia source
- [x] BabesAndStars source
- [x] Babepedia source
- [x] JavBus source
- [x] JavDatabase source
- [x] Gender detection (`people/gender.py`, IAFD via XPath; degrades to '' until the bypass lands)
- [x] Generic placeholder logic (`people/generic.py`)
- [x] On-disk headshot cache (`people/cache.py`)
- [x] Actor-alias tables (`people/data.py` + `_data/json/actors.json` + `actorsJavBusSearch.json`; legacy `PAdatabaseActors.py`)
- [x] Full PeopleManager pipeline (clean → alias → cache/HEAD/sources/generic → gender)

**Tier 2 complete.** All 10 photo sources are site-specific XPath modules under
`app/utils/people/sources/` wired into `ALL_SOURCES`. IAFD-backed lookups (gender
detection + the IAFD source) only return data once the bypass chain (Tier 3) lands.

## Tier 3 — cross-cutting subsystems (many scrapers opt in) — DONE

- [x] HTTP bypass orchestrator (`http/bypass.py`) — wired into base `Client`
  - [x] FlareSolverr provider
  - [x] Playwright provider (optional; only if `playwright` is installed)
  - [x] ReqBin provider
  - Unblocks IAFD-backed people lookups (gender + IAFD source) when configured.
- [x] Search engines (URL-resolution fallback) — `app/clients/searchengines/`
  - [x] DuckDuckGo (HTML scrape, XPath)
  - [x] Google CSE (`web_search` / `web_search_filtered` chain)
- [x] Data18 image enrichment
  - [x] `Data18Client` engine (`app/clients/databases/data18.py`, XPath; + dice metric in similarity)
  - [x] JavBus images helper (`app/clients/helpers/javbus_images.py`)
  - [x] Fanart + fansite image adapters (`app/utils/images/fanart.py` + `fansite_adapters.py`,
        16 adapters; parsel `.css()` with a `:not(:contains())` shim). Xart's
        `xartFanArtOverrides` data lands when the Xart scraper is ported (Tier 4).
  - [x] (legacy reference: `PAdata18ImageSearch.py`)

**Tier 3 complete.**
- [x] Captcha proof-of-work solver (`app/utils/captcha/pow.py`)
- [x] Per-site cookies (`app/utils/cookies/site_cookies.py`)
- [x] Shared HTML helpers (`app/clients/helpers/html_helpers.py`) — XPath/web-search
- [x] Shared GraphQL helper (`app/clients/helpers/graphql_client.py`)

## UI / parity polish

- [x] Config UI styling — full styled page at `app/routes/html/config_ui.html`
      (dark theme, sticky toolbar, grouped cards,
      per-var badges, secret reveal, image preview, drag-sortable list controls,
      dirty tracking, save/reset/reload/restart). Client-rendered from the state
      JSON; forwards the admin token to its API calls for tunnel use.

## Tier 4 — scrapers (dedicated client + selector + data + tests each)

Each item = `Client` subclass in `app/clients/` (`aggregators/`, `networks/`, or
`sites/`), selector in `app/registry/selectors/`, registry wiring, `_data/json`
assets, and a fixture-driven test. Run `ruff`/`mypy`/`pytest` before each commit
(one commit per scraper).

### Database / aggregator clients (8)

- [x] Data18Empire
- [x] Data18Movies
- [x] Data18Scenes
- [x] JAVDatabase
- [x] JavBus
- [x] JavLibrary
- [x] MetadataAPI
- [x] Pornbox

### Network clients (77)

- [x] AbbyWinters
- [x] AdultEmpireCash
- [x] AdultPrime
- [x] BadoinkVr
- [x] Bang
- [x] BellaPass
- [x] Bellesa
- [x] BlurredMedia
- [x] CaramelCash
- [x] CherryPimps
- [x] CouplesCinema
- [x] CzechAV
- [x] CzechVR
- [x] DerangedDollars
- [x] DirtyFlix
- [x] DirtyHardDrive
- [x] EvolvedFights
- [x] FAKings
- [x] FTV
- [x] FemdomEmpire
- [x] FuelVirtual
- [x] FullPornNetwork
- [x] GammaEnt
- [x] GammaEntOther
- [x] Gasm
- [x] Grooby
- [x] HighTechVR
- [x] InterracialPass
- [x] Intersec
- [x] JulesJordan
- [x] Karups
- [x] KellyMadison
- [x] Killergram
- [x] Kink
- [x] LittleCaprice
- [x] LoveHerFilms
- [x] MetArt
- [x] MissaX
- [x] ModelCentro
- [x] NVG
- [x] NaughtyAmerica
- [x] Network18
- [x] Network5KP
- [x] NewSensations
- [x] NewSensationsOther
- [x] Nubiles
- [x] PKJMedia
- [x] PerfectGonzo
- [x] PervCity
- [x] PornPros
- [x] PornCZ
- [x] PornWorld
- [x] PorndoePremium
- [x] Private
- [x] Project1Service
- [x] Puffy
- [x] PureCFNM
- [x] QueenSnake
- [x] RadicalCash
- [x] RadicalCashOther
- [x] Reptyle
- [x] Romero
- [x] ScoreGroup
- [x] SinX
- [x] Spizoo
- [x] SteppedUp
- [x] Strike3
- [x] TeenCoreClub
- [x] TeenMegaWorld
- [x] ThickCash
- [x] ThickCashOther
- [x] VIP4K
- [x] UnzipVR
- [x] VNA
- [x] Wankz
- [x] WankzVR
- [x] WowNetwork

### Site clients (93)

- [x] AdultEmpire
- [x] AllureMedia
- [x] AlsAngels
- [x] AmourAngels
- [x] AnalVids
- [x] BAMVisions
- [x] BelAmi
- [x] BlackPayBack
- [x] BoundHoneys
- [x] BrandNewAmateurs
- [x] Caribbeancom
- [x] Clips4Sale
- [x] ClubFilly
- [x] Colette
- [x] CumLouder
- [x] Cumbizz
- [x] DarkRoomVR
- [x] DesperateAmateurs
- [x] DickDrainers
- [x] DorcelClub
- [x] DorcelVision
- [x] ExpliciteArt
- [x] FamilyTherapy
- [x] Femjoy
- [x] FinishesTheJob
- [x] FirstAnalQuest
- [x] FittingRoom
- [x] FuckingAwesome
- [x] GirlsOutWest
- [x] GirlsRimming
- [x] HeavyOnHotties
- [x] Hegre
- [x] HollyRandall
- [x] HoloGirlsVR
- [x] HotwifeXXX
- [x] Hucows
- [x] InTheCrack
- [x] JVRPorn
- [x] JacquieEtMichel
- [x] JesseLoadsMonsterFacials
- [x] Kin8tengoku
- [x] LustReality
- [x] Lustomic
- [x] ManualNfo
- [x] Manyvids
- [x] MeanaWolf
- [x] MelenaMariaRya
- [x] MeloneChallenge
- [x] MomComesFirst
- [x] MomPOV
- [x] MyDirtyHobby
- [x] PJGirls
- [x] POVR
- [x] PenthouseGold
- [x] PlayboyPlus
- [x] PlumperPass
- [x] PornstarPlatinum
- [x] Puba
- [x] Putalocura
- [x] RealityLovers
- [x] ReidMyLips
- [x] ScrewMeToo
- [x] Screwbox
- [x] SexLikeReal
- [x] SexMex
- [x] Sicflics
- [x] SinsLife
- [x] StasyQ
- [x] StepSecrets
- [x] StraponCum
- [x] SwallowBay
- [x] TeenyTaboo
- [x] TonightsGirlfriend
- [x] TwoTGirls
- [x] Ultrafilms
- [x] VIPissy
- [x] VRAllure
- [x] VRLatina
- [x] VRPFilms
- [x] VirtualReal
- [x] VirtualTaboo
- [x] Vivid
- [x] VogoV
- [x] WakeUpNFuck
- [x] Watch4Beauty
- [x] WeAreHairy
- [x] WoodmanCastingX
- [x] XConfessions
- [x] XSinsVR
- [x] XVirtual
- [x] Xart
- [x] XevUnleashed
- [x] Xillimite

---

## Tier 5 — documentation

Documentation for the FastAPI/Python architecture (XPath selectors, dedicated
clients, `ruff`/`mypy`/`pytest`, uvicorn, etc.), plus the Docusaurus site under
`website/`.

- [x] DESIGN.md (architecture overview — rewrite for FastAPI)
- [x] file-naming.md (filename parsing rules)
- [x] manualsearch.md / dev-ui.md (config + dev UI usage)
- [x] selectors.md (rewrite for XPath/parsel)
- [x] healthcheck.md / site-health.md (when health checks land)
- [x] hosting.md (uvicorn/Docker/tunnel)
- [x] scraper-test-plan.md (pytest fixture conventions)
- [x] sitelist.md (generated — when the sitelist generator is ported)
- [x] notes.md + misc
- [x] Docusaurus site under `website/` (config, sidebars, build) — decide whether
      to port now or after scrapers exist
- [x] README.md expansion (mostly done in the foundation)

## Scripts / tooling

Python scripts under `scripts/`, invoked via `python -m scripts.<name>`.

- [x] Sitelist generator (regenerates `docs/sitelist.md` from `SITE_DEFINITIONS`;
      run after each scraper, per the workflow rule)
- [x] Site-health checker (probes each site's search/detail and reports failures)
- [x] Asset mirroring — NO-OP (no build step; Python reads `_data/json/*.json`
      directly via `Path`)
- [x] `start-with-tunnel.ps1` — Cloudflare tunnel launcher

## Deferred scrapers (need shared infrastructure — surface before porting)

These aren't self-contained web scrapers; each needs cross-cutting work (new env
vars → config UI, new routes, login tokens). Left unchecked in the lists above.

- [x] AdultEmpire — `adultEmpireLoginToken` env var (→ config UI), JSON actor-data
      table, split-scene logic, `titleCase`/`webSearch`
- [x] ManualNfo — local-filesystem NFO provider: `MANUAL_NFO_PATH` env var (→ config
      UI), a `/images/manual-nfo/` image-serving route, filesystem index + XML parse

## Legacy-bundle features to reconcile

Reconcile against legacy behaviour when the related scrapers land (don't drop silently):

- [ ] Extras / trailers (`PAextras.py`)
- [ ] Collections (`PAcollections.py`)
- [ ] Captcha helper (`PAcaptchaHelper.py`) vs `app/utils/captcha/pow.py`
- [ ] Confirm search method/notes from legacy `PAsiteList.py` per scraper

## Image-URL policy (2026-06-17 decision)

The provider does NOT cache metadata/images today (Plex used to download + cache
in the old bundle). Until provider-side caching lands, scrapers must always emit
the **full resolved image URL** — do NOT strip query strings (timestamps/tokens),
because a stripped URL may not resolve. AdultPrime's legacy `?`-strip was dropped
for this reason.

- [ ] **Tier 6 — provider-side image caching.** Cache fetched images to the
      provider data directory (protects against upstream site changes/deletions).
      Once this lands, revisit whether stripping volatile query params is safe.
- [ ] **Audit: image-URL stripping across scrapers.** While porting the remaining
      scrapers, do NOT strip image query strings; flag any legacy `?`-strip /
      URL-cleaning as a drift. Then a follow-up review of already-ported scrapers
      to find + fix any that strip image URLs.
