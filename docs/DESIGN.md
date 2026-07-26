---
sidebar_label: Architecture & Design
description: Model-based architecture reference for the PhoenixAdult metadata provider (Python/FastAPI).
---

# PhoenixAdult — Design Document

**Status:** living document · **Audience:** maintainers & contributors
**Scope:** the Python/FastAPI Plex metadata provider in this repository, built on Plex's Metadata Provider API.

This document is *model-based*: each section leads with a diagram (UML-style, rendered with Mermaid) and the prose only explains what the model cannot. Diagrams are grounded in the current source — file references are given so a model can be checked against code.

---

## 1. Purpose & System Overview

PhoenixAdult is an HTTP service that implements the **Plex Metadata Provider** contract for adult video libraries. Plex sends it a filename to *match*, then asks it for *metadata* and *images* for the chosen result. The service scrapes ~hundreds of studio/network sites, normalizes the data into Plex's schema, resolves actor headshots from external sources, and proxies all images back through itself.

| Dimension | Value (current) |
|---|---|
| Providers | 1 (`phoenixadult`) |
| Scraper config variants (`type`) | ≈178 |
| `Client` subclasses | 178 (registered in `CLIENT_REGISTRY`) |
| Site/network definition groups | 178 (spanning ~1,200 individual sites) |
| Actor-photo sources | 10 (IAFD, Freeones, AdultDVDEmpire, Babepedia, …) |
| HTTP-bypass backends | 4 (Impersonate, FlareSolverr, Playwright, ReqBin) |
| Runtime | Python 3.13, FastAPI, uvicorn, httpx2 (async), parsel (XPath / lxml), Pillow |

---

## 2. System Context (C4 — Level 1)

```mermaid
flowchart LR
  classDef ext fill:#1e2433,stroke:#6366f1,color:#e2e8f0;
  classDef sys fill:#312e81,stroke:#a5b4fc,color:#fff;

  plex["Plex Media Server<br/>(metadata agent client)"]:::ext
  op["Operator / Admin<br/>(browser)"]:::ext

  sys["PhoenixAdult Provider<br/>(this repository)"]:::sys

  sites["Upstream studio/network sites<br/>(HTML + JSON APIs)"]:::ext
  flare["Impersonate / FlareSolverr / Playwright / ReqBin<br/>(anti-bot bypass)"]:::ext
  photos["Actor-photo & gender sources<br/>(IAFD, Freeones, …)"]:::ext
  websearch["Google CSE / DuckDuckGo<br/>(fallback site search)"]:::ext

  plex -- "match / metadata / image requests (HTTP)" --> sys
  op -- "config & dev UIs (HTTP)" --> sys
  sys -- "scrape scenes" --> sites
  sys -- "challenge bypass" --> flare
  sys -- "resolve headshots / gender" --> photos
  sys -- "locate scene URLs" --> websearch
  sys -- "proxied images" --> plex
```

**Trust note:** Plex and the upstream sites are *not* trusted inputs. Plex-supplied ratingKeys/filenames and scraped content both cross a trust boundary (see §10).

---

## 3. Use Cases

```mermaid
flowchart LR
  classDef actor fill:#0f1117,stroke:#94a3b8,color:#e2e8f0;
  classDef uc fill:#1e2433,stroke:#6366f1,color:#e2e8f0;

  plex(["Plex Media Server"]):::actor
  op(["Operator / Admin"]):::actor
  dev(["Developer"]):::actor

  subgraph S[PhoenixAdult Provider]
    direction TB
    u1("Discover provider capabilities"):::uc
    u2("Match scene by filename"):::uc
    u3("Fetch scene metadata"):::uc
    u4("Fetch / proxy images"):::uc
    u5("Serve local & manual-NFO images"):::uc
    u6("View & edit runtime config"):::uc
    u7("Reset overrides / restart"):::uc
    u8("Run scraper pipeline test"):::uc
  end

  plex --> u1
  plex --> u2
  plex --> u3
  plex --> u4
  plex --> u5
  op --> u6
  op --> u7
  dev --> u8

  u3 -. "«include»" .-> u4
  u2 -. "«include»" .-> u4
  u8 -. "«include»" .-> u2
  u8 -. "«include»" .-> u3
```

| Use case | Entry point | Auth |
|---|---|---|
| Discover capabilities | `GET /<provider mount>/` | none (public contract) |
| Match scene | `POST /<mount>/library/metadata/matches` | none |
| Fetch metadata | `GET /<mount>/library/metadata/{rating_key}` | none |
| Fetch/proxy image | `GET\|HEAD /images/proxy`, `/images/proxy-classified` | none (SSRF-guarded) |
| Local/manual images | `GET /images/local/{filename}`, `/images/manual-nfo/*` | none (path-guarded) |
| Runtime config | `GET\|POST /config/...` | **loopback or `ADMIN_TOKEN`** |
| Cache / logo / queue review UIs | `GET /people`, `/metadata`, `/logos`, `/queue` | **loopback or `ADMIN_TOKEN`** |
| Cache editors | `GET /metadata/edit`, `/people/edit` + `POST …/save` | **loopback or `ADMIN_TOKEN`** |
| Dev pipeline test | `GET\|POST /dev/...` (non-prod only) | **loopback or `ADMIN_TOKEN`** |

> Auth caveat: when `ADMIN_TOKEN` is **blank/unset**, the admin guard (`phoenixadult/utils/auth/env_auth.py`) disables auth entirely — `/config` and `/dev` become open to any caller. This is a deliberate convenience-over-safety default for trusted/local networks; it is documented at the top of `env_auth.py`. Set `ADMIN_TOKEN` whenever the server is reachable beyond loopback.

---

## 4. Container / Component Model (C4 — Level 2)

```mermaid
flowchart TB
  classDef r fill:#1a2035,stroke:#6366f1,color:#e2e8f0;
  classDef s fill:#14532d,stroke:#4ade80,color:#e2e8f0;
  classDef c fill:#3b0764,stroke:#c084fc,color:#fff;
  classDef u fill:#1e2433,stroke:#64748b,color:#cbd5e1;
  classDef ext fill:#0f1117,stroke:#475569,color:#94a3b8;

  subgraph app["FastAPI app (phoenixadult/app_factory.py)"]
    direction TB
    mw["request-logging middleware"]:::r
    pr["provider_router<br/>/library/metadata/*"]:::r
    ir["image_routes<br/>/images/*"]:::r
    cr["env_routes<br/>/config/*  (env_auth_guard dep)"]:::r
    dr["dev_routes<br/>/dev/*  (env_auth_guard dep)"]:::r
  end

  subgraph svc["Services"]
    ms["MatchService"]:::s
    md["MetadataService"]:::s
    mm["MetadataMapper"]:::s
    sq["scrape_queue<br/>(deferred background work)"]:::s
  end

  subgraph scr["Scraper engine"]
    srt["ScraperRouter<br/>(type → Client via get_client)"]:::c
    cli["178 dedicated Client subclasses<br/>(sites / networks / aggregators)"]:::c
    base["base Client<br/>(field-hook orchestrator)"]:::c
  end

  subgraph reg["Registry (phoenixadult/registry)"]
    prov["ProviderInfo"]:::u
    site["SiteInfo / ResolvedSiteInfo"]:::u
    scfg["ScraperConfig union"]:::u
  end

  subgraph plat["Cross-cutting platform"]
    http["HTTP layer<br/>make_http + bypass chain"]:::u
    ssrf["ssrf_guard"]:::u
    img["Image pipeline<br/>fetcher · classifier · referers"]:::u
    ppl["PeopleManager<br/>+ photo sources + cache"]:::u
    cfg["Config<br/>env · catalog · overrides"]:::u
    log["logger + capture"]:::u
  end

  ext1["Upstream sites"]:::ext
  ext2["Bypass / photo / websearch"]:::ext

  pr --> ms & md
  dr --> ms & md
  ms --> sq
  md --> sq
  ms --> srt
  md --> srt
  ms --> mm
  md --> mm
  srt --> cli --> base
  cli --> reg
  base --> http
  ir --> ssrf --> img
  ir --> img
  mm --> img
  mm --> ppl
  md --> ssrf
  http --> ext1
  http --> ext2
  ppl --> ext2
  base --> log
  cfg -. configures .-> http
  cfg -. configures .-> img
  cfg -. configures .-> ppl
```

**Key relationships**

- **Routes are thin.** `provider_router` (`phoenixadult/routes/provider_router.py`) delegates immediately to `MatchService` / `MetadataService`.
- **`ScraperRouter`** (`phoenixadult/services/scraper_router.py`) is a dispatcher: it resolves a scraper `type` to its single `Client` instance via `get_client` (`phoenixadult/clients/__init__.py`, `CLIENT_REGISTRY`). It owns `search`, `fetch_scene_detail`, and `decode`.
- **`MetadataMapper`** (`phoenixadult/mappers/metadata_mapper.py`) translates the scraper's `SceneDetail` into Plex's schema and rewrites every image URL through the `/images/proxy` endpoint.
- **Registry** is static data: providers, sites, and per-site `ScraperConfig` that selects and parameterizes a client.
- **`scrape_queue`** (`phoenixadult/services/scrape_queue.py`) is a single sequential background worker (dedup by key, 500-job cap). When pacing or the serve budget defers a search/update (§7.6), the services enqueue it here to finish off the request path.

---

## 5. Domain & Data Model

```mermaid
classDiagram
  class ProviderInfo {
    +id: str
    +plex_identifier: str
    +title: str
    +version: str
    +media_type: PlexMediaType
  }
  class SiteInfo {
    +name: str
    +base_url: str
    +search_path: str
    +content_type: ContentType
    +provider_id: str | None
    +image_referers: list[str]
    +image_cookies: list[str]
    +use_bypass: bool
    +scraper_config: ScraperConfig
  }
  class ResolvedSiteInfo {
    +provider_id: str
  }
  class ScraperConfig {
    <<union ~173 variants>>
    +type: str
  }
  class SearchContext {
    +title: str
    +encoded: str
    +site_info: ResolvedSiteInfo
    +search_date: str | None
    +scene_id: str | None
    +full_title: str | None
    +allow_slow: bool
  }
  class SceneContext {
    +capture: list | None
    +language: str | None
    +subsite: str | None
    +allow_slow: bool
  }
  class SearchResult {
    +title: str
    +scene_url: str
    +cur_id: str
    +thumb_url: str | None
    +score: float | None
  }
  class SceneDetail {
    +title: str
    +summary: str
    +studio: str
    +genres: list[str]
    +actors: list[ActorResult]
    +art: list[str]
    +art_referer: str | None
    +art_cookie: str | None
    +logo: str | None
  }
  class ActorResult {
    +name: str
    +photo_url: str
    +gender: str
  }
  class PlexMatchResult {
    +ratingKey: str
    +guid: str
    +title: str
    +score: float
    +thumb: str | None
  }
  class PlexMetadata {
    +ratingKey: str
    +title: str
    +summary: str
    +thumb: str | None
    +art: str | None
    +Genre/Role/...: []
  }

  ProviderInfo "1" o-- "many" SiteInfo : owns
  SiteInfo <|-- ResolvedSiteInfo
  SiteInfo "1" *-- "1" ScraperConfig
  SearchContext --> ResolvedSiteInfo
  SearchContext ..> SearchResult : client.search() yields
  SearchResult ..> PlexMatchResult : MetadataMapper.to_match_result
  SceneDetail *-- ActorResult
  SceneDetail ..> PlexMetadata : MetadataMapper.to_metadata
```

### 5.1 Identifier Lifecycle (the Spine of the System)

The same scene is represented differently at each stage; the encoding is reversible so a Plex `ratingKey` round-trips back to a fetchable scene URL.

```mermaid
flowchart LR
  fn["filename<br/>site.24.03.15.scene.name.mp4"]
  parsed["parsed pieces<br/>ParsedFilename{site_token, date, content}"]
  q["search query + scene_id + full_title<br/>(build_search_pieces)"]
  sr["SearchResult.cur_id<br/>base64url(scene_url|date)"]
  rk["rating_key<br/>scene-&lt;site&gt;-&lt;cur_id&gt;.YYYYMMDD"]
  guid["Plex guid<br/>&lt;plex_id&gt;://movie/&lt;rating_key&gt;"]
  surl["scene_url (decoded)"]
  detail["SceneDetail → PlexMetadata"]

  fn -->|get_site_name_from_registry| parsed -->|build_search_pieces| q
  q -->|client.search| sr -->|to_rating_key| rk --> guid
  rk -->|parse_rating_key + decode| surl -->|fetch_scene_detail| detail
```

- Encode/decode: `Client.encode` / `Client.decode` = base64url, backed by `b64url_encode` / `b64url_decode` (`phoenixadult/utils/helpers/helpers.py`); `cur_id` is assembled by `pack_cur_id`.
- `to_rating_key` / `parse_rating_key`: `phoenixadult/mappers/metadata_mapper.py` (regex `^scene-([a-z0-9]+)-([A-Za-z0-9_-]+)(?:\.(\d{8}))?$`).
- **Security-relevant:** the decoded `scene_url` is attacker-influenceable and is validated by `ensure_fetchable_url` (`phoenixadult/utils/http/ssrf_guard.py`) before any fetch (§10).

### 5.2 Persistent State (phoenixadult.db)

Mutable state — queue replays, the search store, the fully normalized scene snapshot store (scalars on `scenes`; dimension + junction tables for genres, collections, countries, people; image metadata in `scene_images`, image bytes on disk), and the derived people-image/logo indexes plus the face-crop log — lives in one SQLite database opened by `phoenixadult/utils/db` (WAL, FK-enforced, `PRAGMA user_version` migrations). Schema, normalization rationale, scoped-people resolution, and backup guidance (`VACUUM INTO`) are documented in [database.md](database.md).

---

## 6. Scraper Client Hierarchy (Template Method / Field-Hook Pattern)

The base `Client` (`phoenixadult/clients/base.py`) defines two *orchestrators* — `search()` and `fetch_scene_detail()` — that call a fixed sequence of overridable *hooks*. A concrete client implements only the hooks relevant to its site; the orchestration (dedup, parallel field fetch, capture logging, bypass fallback) lives once in the base. **Every scraper is hand-written** — there is intentionally *no* shared, config-driven client (no `JsonClient`, no per-network base class). Shared *helpers* are fine: `GraphQLClient` (`phoenixadult/utils/helpers/graphql_client.py`), `html_helpers`, and the image adapters.

```mermaid
classDiagram
  class Client {
    <<base>>
    +search(ctx) SearchResult[]
    +fetch_scene_detail(payload, site, ctx) SceneDetail
    +encode(s) / decode(s) str
    #load_search_context(ctx) LoadedSearch
    #build_search_results(source, loaded) SearchResult[]
    #fetch_search_title / scene_url / date / score / thumb_url
    #load_scene_context(payload, site, ctx) LoadedScene
    #fetch_title / summary / studio / tagline / collections
    #fetch_release_date / genres / actors / directors / producers
    #fetch_image_urls(scene) list[str]
    #fetch_and_load(url, ctx) parsel.Selector  bypass-aware
    #fetch_json(url, ctx) Any  bypass-aware
  }
  class sites["phoenixadult/clients/sites/* (93)"] {
    «per-site XPath flow»
  }
  class networks["phoenixadult/clients/networks/* (76)"] {
    «per-network flow»
  }
  class aggregators["phoenixadult/clients/aggregators/* (11)"] {
    «Data18 / JavBus / MetadataAPI / …»
  }

  Client <|-- sites
  Client <|-- networks
  Client <|-- aggregators
  note for Client "178 dedicated subclasses registered in CLIENT_REGISTRY; ScraperConfig.type selects one instance."
```

The search default = `load_search_context` + per-source `build_search_results` (which calls `fetch_search_scene_url` / `fetch_search_title` / `fetch_search_date` / `fetch_search_score` / `fetch_search_thumb_url`, dedups on `scene_url`, and packs the `cur_id`). The detail default = `load_scene_context` + per-field hooks (`fetch_title` / `summary` / `studio` / `tagline` / `release_date` / `genres` / `actors` / `directors` / `producers` / `collections` / `image_urls`). `fetch_scene_detail()` fans the field hooks out with `asyncio.gather` (one network/parse step per field), then assembles a `SceneDetail`. `fetch_and_load` / `fetch_json` try a direct httpx2 request first and fall back to the bypass chain when enabled (§8); HTML is parsed XPath-only via `parsel.Selector` (lxml-backed). Images are classified by aspect ratio (`classify_image`): a portrait image with aspect ~1.4–1.6 is a `coverPoster`, a landscape image is a `background`. clearLogos are managed separately from scenes: `phoenixadult/utils/images/logo_cache.py` stores `logos/<studio-slug>/logo.<name-slug>.<ext>` files (SVG rasterized via rsvg-convert/cairosvg/ImageMagick), reviewed at `/logos`, and pushed to Plex **collections** by `plex_reconcile.push_collection_logos` (the "Push Logos to Collections" action) — scenes never carry a logo.

---

## 7. Request Flows (Sequence Models)

### 7.1 Match — `POST /library/metadata/matches`

```mermaid
sequenceDiagram
  autonumber
  participant Plex
  participant PR as provider_router
  participant MS as MatchService
  participant FP as filename_parser
  participant SR as ScraperRouter
  participant CL as Client(site)
  participant UP as Upstream site
  participant MM as MetadataMapper

  Plex->>PR: POST matches {filename, manual, includeAdult}
  PR->>MS: match(req, provider)
  alt suppressed (not adult / auto-match off & not manual)
    MS-->>Plex: empty MediaContainer
  else
    MS->>FP: get_site_name_from_registry(parse_source)
    FP-->>MS: ParsedFilename{site_token, date, content}
    MS->>MS: build_search_pieces() → query, scene_id, full_title
    MS->>SR: search(SearchContext)
    SR->>CL: search(ctx)   // type→Client dispatch
    CL->>UP: GET search / API
    UP-->>CL: HTML / JSON
    CL-->>SR: SearchResult[]
    SR-->>MS: SearchResult[]
    loop each result
      MS->>MM: to_match_result(raw, site_name, score, plex_id)
      MM-->>MS: PlexMatchResult (ratingKey, guid, proxied thumb)
    end
    MS-->>Plex: MediaContainer (sorted by score)
  end
```

### 7.2 Metadata — `GET /library/metadata/{rating_key}`

```mermaid
sequenceDiagram
  autonumber
  participant Plex
  participant PR as provider_router
  participant MD as MetadataService
  participant GUARD as ssrf_guard
  participant SR as ScraperRouter
  participant CL as Client(site)
  participant UP as Upstream site
  participant MM as MetadataMapper
  participant PM as PeopleManager
  participant IMG as Image pipeline

  Plex->>PR: GET /library/metadata/scene-...-...
  PR->>MD: get_metadata(rating_key, provider)
  MD->>MD: parse_rating_key → {site_name, cur_id}
  MD->>SR: decode(cur_id) → scene_url
  MD->>GUARD: ensure_fetchable_url(scene_url)
  alt blocked (private/loopback/metadata)
    GUARD-->>MD: raise ValueError → return None
  else allowed
    MD->>SR: fetch_scene_detail(scene_url, site)
    SR->>CL: fetch_scene_detail(...)
    CL->>UP: GET scene page / API
    UP-->>CL: content
    CL-->>MD: SceneDetail
    MD->>MM: to_metadata(detail, ...)
    MM->>IMG: fetch_dimensions(raw_url, referers, cookies)*
    IMG-->>MM: {width,height} → classify_image
    MM->>PM: resolve_all(actors/directors/producers)
    PM-->>MM: resolved people (+ cached headshots)
    MM-->>MD: PlexMetadata (proxied thumb/art/images/roles)
    MD-->>Plex: MediaContainer{Metadata:[...]}
  end
```

### 7.3 Scraper Fetch with Anti-Bot Bypass Fallback

```mermaid
sequenceDiagram
  autonumber
  participant CL as Client
  participant H as make_http (httpx2)
  participant UP as Upstream
  participant BP as bypass chain
  participant FS as Impersonate/FlareSolverr/Playwright/ReqBin

  CL->>H: GET url (direct)
  H->>UP: request
  alt 2xx
    UP-->>CL: body
  else error / 4xx-5xx and bypass enabled
    CL->>BP: bypass_get(url)
    loop configured order, first available wins
      BP->>FS: request(url)
      FS-->>BP: body or None
    end
    BP-->>CL: recovered body or None
  end
```

### 7.4 Image Proxy — `GET /images/proxy?url=…`

```mermaid
sequenceDiagram
  autonumber
  participant Plex
  participant IR as image_routes
  participant G as ssrf_guard.assert_fetchable_url
  participant IF as image_fetcher
  participant UP as Image host

  Plex->>IR: GET /images/proxy?url=…&referer=…&cookie=…
  IR->>G: parse + scheme check + resolve host
  alt private/loopback/metadata or bad scheme
    G-->>Plex: 400 Invalid url
  else public
    IR->>IF: fetch_image(url, referers, cookies)
    IF->>UP: GET (sanitized headers, redirect guard)
    UP-->>IF: bytes + content-type
    IF->>IF: enforce image content-type + max bytes, read Pillow dimensions
    IF-->>Plex: image bytes (Cache-Control)
  end
```

`/images/proxy-classified` is the same flow plus a `classify_image(width, height)` step; it returns 404 when the image classifies as `unknown` and stamps `X-Image-Type` on success.

### 7.5 Runtime Config Override

```mermaid
sequenceDiagram
  autonumber
  participant Op as Operator
  participant AG as env_auth_guard
  participant CR as env_routes
  participant OV as env_overrides
  participant FS as env.overrides.json

  Op->>AG: POST /config/api/save {updates}
  alt not loopback and no/invalid ADMIN_TOKEN
    AG-->>Op: 401
  else allowed
    AG->>CR: dependency passes
    CR->>CR: normalize_env_value per catalog spec
    CR->>OV: set_override(key, value)
    OV->>OV: os.environ[key]=value
    OV->>FS: persist JSON
    CR-->>Op: new UI state (secrets redacted)
  end
  note over OV,FS: On boot, load_overrides() re-applies<br/>FS over .env — overrides WIN.
```

### 7.6 Serve Budget & Deferred Work

```mermaid
sequenceDiagram
  autonumber
  participant Plex
  participant SVC as Match/MetadataService
  participant P as ScenePacer
  participant Q as scrape_queue
  participant CL as Client

  Plex->>SVC: request (Plex kills it at ~90s)
  SVC->>P: acquire turn (allow_slow=False)
  alt pending wait ≤ 10s and within 85s budget
    P-->>SVC: proceed
    SVC->>CL: search / fetch_scene_detail
    CL-->>Plex: results / metadata
  else would wait too long
    P-->>SVC: PacingDeferredError (or budget timeout)
    SVC->>Q: enqueue job (allow_slow=True)
    SVC-->>Plex: empty response now
    Q->>CL: run later, sleeping through gaps
    note over Q,CL: update → metadata snapshot cache<br/>search → in-memory memo (TTL 15 min)
  end
```

Plex aborts provider requests at ~90s, so both services cap serving at `PLEX_REQUEST_BUDGET` (85s): `MetadataService.get_metadata` wraps the coalesced scrape in `wait_for(shield(...))` — on timeout the scrape *continues* and lands in the snapshot cache — while `MatchService.match` cancels outright. Work deferred by pacing (`PacingDeferredError`, raised when a foreground request would wait >10s) is re-run through `scrape_queue` with `allow_slow=True`, which is allowed to sleep through the shared gap. On paced sites a finished background search persists to the search store (`phoenixadult/utils/cache/search_store.py`, in `phoenixadult.db`, case/whitespace-normalized keys, lifetime `SEARCH_STORE_TTL_DAYS` — perpetual by default), so any later Plex scan matches without re-searching; the in-memory memo fronts the store. The queue and pacer state are visible at `/queue`.

### 7.7 Thread Pools — Keeping the UI Responsive Under Load

Every route is `async def`, so anything synchronous runs on the event loop unless handed to a thread. `asyncio.to_thread` hands work to the **one** default executor (`min(32, cpu+4)`), which every caller shares — so a scrape probing 60+ artwork URLs, each ending in a Pillow decode, could fill it and leave a `/people` or `/metadata` page's SQLite read queued behind image work.

`phoenixadult/utils/concurrency/pools.py` replaces that single pool with named, bounded ones, and `run_in(name, fn, …)` is a drop-in for `to_thread` against a chosen pool (it copies contextvars the same way, so request-id logging survives):

| Pool | Size | Carries |
|---|---|---|
| `store` | 4 | SQLite reads/writes — cache pages, editors, search store, serve-path snapshot reads |
| `image` | `min(8, cpu/2)` | Pillow decode/dimension probing, face cropping |
| `fs` | 4 | People-cache file writes |

Artwork probing is additionally capped at `_PROBE_CONCURRENCY` (8) per scene, so one scene's image set arrives as a stream rather than a burst. Pools are created on first use and shut down in the lifespan's `finally`.

The `store` bound doubles as a cap on SQLite connections: connections are per-thread (§5), so a 4-thread pool means at most four from that pool rather than one per default-executor thread.

---

## 8. HTTP / Anti-Bot Bypass Model

```mermaid
flowchart LR
  classDef u fill:#1e2433,stroke:#64748b,color:#cbd5e1;
  direct["Direct httpx2 (make_http)<br/>UA, optional proxy, verify=False"]:::u
  chain["bypass chain (configurable order)"]:::u
  im["Impersonate (curl_cffi, Chrome TLS)"]:::u
  fs["FlareSolverr (Cloudflare)"]:::u
  pw["Playwright (headless Chromium)"]:::u
  rb["ReqBin (3rd-party)"]:::u

  direct -->|"on failure & enabled"| chain
  chain --> im
  chain --> fs
  chain --> pw
  chain --> rb
  note1["Per-site use_bypass (FetchCtx.use_bypass) or global<br/>BYPASS_AUTO_RETRY gates the fallback.<br/>First available backend wins."]
  chain -.-> note1
```

- `make_http` (`phoenixadult/utils/http/client.py`) builds a shared `httpx2.AsyncClient` (UA, optional proxy honouring `NO_PROXY`, TLS verification intentionally relaxed — `verify=False` — for janky CDNs; see §10 residuals).
- `phoenixadult/utils/http/bypass.py` (`bypass_get` / `bypass_post` / `http_bypass`) orders backends by `BYPASS_ORDER`, skips unavailable ones (each backend exposes `is_available()`), and returns the first 2xx that isn't itself a challenge page. The default order is **Impersonate → FlareSolverr → Playwright → ReqBin**; backends live in `impersonate.py`, `flaresolverr.py`, `playwright.py`, `reqbin.py`. The entry point used by clients is `bypass_get` (and `bypass_post` for GraphQL), surfaced on the base via `FetchCtx.use_bypass`.
  - **Impersonate** (`impersonate.py`) uses `curl_cffi` to mimic a real Chrome TLS/JA3 fingerprint. It is the only backend that defeats fingerprint-based Cloudflare blocks *and* forwards custom headers (e.g. `Referer`), so it leads the chain. Optional — install with `pip install -e ".[impersonate]"`; absent, it's skipped.
  - **FlareSolverr** solves Cloudflare interstitials via a sidecar container; it drops custom request headers.
  - **Playwright** drives headless Chromium (optional — `pip install -e ".[playwright]"`); forwards headers via the browser context.
  - **ReqBin** is a third-party fetch relay.
  - Challenge detection: a 2xx whose body still contains a challenge marker (AWS WAF, `just a moment`, `cf-chl-`, Turnstile) is treated as unsolved, so the chain continues to the next backend.
- **Ban-avoidance pacing** (`ScenePacer`, `phoenixadult/utils/http/rate_limit_helper.py`): ban-prone scrapers (`nubiles.py`, `naughtyamerica.py`) set `Client.pacer`, and the base orchestrators route every search and scene scrape through it. Searches and scenes share **one** gap track — after any turn the next waits `SCENE_GAP` (default 10s) plus a random 10–45s jitter — with a hard cap of 8 scenes per 10 minutes and jittered per-request spacing inside a scrape. A foreground (Plex-facing) request that would wait >10s raises `PacingDeferredError` and is finished via `scrape_queue` instead (§7.6).

---

## 9. People (Actor) Resolution Model

```mermaid
flowchart TB
  classDef u fill:#1e2433,stroke:#64748b,color:#cbd5e1;
  add["add_actor / add_director / add_producer"]:::u
  resolve["_resolve_entry (clean, title-case, alias tables, split commas)"]:::u
  cacheL["6a local cache lookup"]:::u
  head["6b scraped photo: HEAD + cache"]:::u
  src["6c external sources (find_photo, ordered)"]:::u
  gender["_detect_gender (IAFD) — independent of cache"]:::u
  generic["6d generic silhouette fallback"]:::u
  out["ResolvedPerson → to_plex_roles (proxied thumb)"]:::u

  add --> resolve --> cacheL --> head --> src --> gender --> generic --> out
  note["Concurrency capped (3 in-flight via asyncio.Semaphore).<br/>Headshots cached on disk, served via /images/local."]
  out -.-> note
```

`PeopleManager.resolve_all` (`phoenixadult/utils/people/__init__.py`) drives the cascade per person: clean the name, title-case it (`title_case(..., type='name')`), drop skip-names, apply the per-studio then global alias tables (`ACTORS_REPLACE` / `ACTORS_REPLACE_STUDIOS` in `phoenixadult/utils/people/data.py`), then resolve a headshot in order. External photo sources live under `phoenixadult/utils/people/sources/` (10 site-specific XPath sources: `iafd`, `freeones`, `adultDvdEmpire`, `babepedia`, `babesAndStars`, `boobpedia`, `indexxx`, `javBus`, `javDatabase`, `localStorage`) and are fanned by `find_photo`. Gender detection (`iafd_gender_check`, `phoenixadult/utils/people/gender.py`) is decoupled from the cache so `GENDER_DETECT_ENABLE` works regardless of `PEOPLE_CACHE_ENABLE`; `GENDER_SKIP_MALE_ENABLE` drops male actors. IAFD requires a bypass backend.

---

## 10. Security Model (Trust Boundaries)

```mermaid
flowchart TB
  classDef pub fill:#7f1d1d,stroke:#fca5a5,color:#fff;
  classDef adm fill:#14532d,stroke:#4ade80,color:#fff;
  classDef int fill:#1e2433,stroke:#64748b,color:#cbd5e1;

  subgraph PUB["UNTRUSTED — public HTTP"]
    p1["Plex routes (match/metadata/images)"]:::pub
    p2["rating_key / filename / proxy url"]:::pub
  end
  subgraph ADM["ADMIN — loopback or ADMIN_TOKEN"]
    a1["/config (state/save/reset/restart)"]:::adm
    a2["/dev pipeline test"]:::adm
  end
  subgraph INT["INTERNAL — server-side"]
    g1["ssrf_guard (proxy + rating_key decode)"]:::int
    g2["_safe_path (local & manual-nfo files)"]:::int
    g3["slug sanitize + write containment (photo cache)"]:::int
    g4["secret redaction in /config state"]:::int
  end

  p1 --> g1
  p2 --> g1
  p1 --> g2
  a1 --> g4
  g1 --> outbound["outbound fetch (scrape / image)"]
```

**Controls in place**

- **Admin auth** (`env_auth_guard`, `phoenixadult/utils/auth/env_auth.py`): wired as a router dependency (`APIRouter(dependencies=[Depends(env_auth_guard)])`) on both `env_routes` and `dev_routes`. When `ADMIN_TOKEN` is set, allows loopback **or** a matching token (timing-safe `hmac.compare_digest`, accepted via `Authorization: Bearer`, `X-Admin-Token`, or `?token=`). When `ADMIN_TOKEN` is blank, auth is **disabled** (open surfaces) — a deliberate convenience default for trusted/local networks.
- **SSRF guard** (`phoenixadult/utils/http/ssrf_guard.py`): scheme allow-list + private/loopback/link-local/CGNAT/metadata (`169.254.169.254`) blocklist with hostname resolution; applied to the image proxy (`assert_fetchable_url`) and to the rating-key-decoded scene URL (`ensure_fetchable_url`).
- **Path safety**: `_safe_path` (`phoenixadult/routes/image_routes.py`) anchors containment on the resolved root; photo-cache slugging strips separators/`..` with a write-containment backstop.
- **Secret hygiene**: `/config/api/state` redacts secret values (exposes only whether set); the request-logging middleware deliberately does not log `/config` bodies (they can carry secrets being saved).

**Known residuals (documented, not yet fixed)** — see also `memory` notes:

- DNS-rebinding TOCTOU in the SSRF guard (resolve-then-fetch); robust fix = pin the validated IP for the outbound connection.
- Hostname-based internal SSRF on the *general* scrape path (only the metadata boundary + image proxy are guarded).
- Admin loopback-trust is bypassable behind a same-host reverse proxy (documented caveat); and the blank-token "auth off" mode opens the surfaces entirely.
- No inbound rate limiting (the outbound `ScenePacer` in §8 is ban-avoidance, not a security control); TLS verification intentionally relaxed (`verify=False`) for upstream CDNs.

> The `title_case` ReDoS (O(n²) post-process passes on long scraped titles) is **mitigated** by a `MAX_TITLE_LENGTH` input cap — see Appendix A.

---

## 11. Configuration Model

```mermaid
flowchart LR
  classDef u fill:#1e2433,stroke:#64748b,color:#cbd5e1;
  envfile[".env (python-dotenv)"]:::u
  catalog["ENV_CATALOG<br/>(editable keys + kinds + validation)"]:::u
  ovfile["env.overrides.json"]:::u
  envmod["env (lazy property getters)"]:::u
  consumers["consumers (services, clients, image, people)"]:::u

  envfile -->|boot| envmod
  ovfile -->|load_overrides applies OVER .env| envmod
  catalog -->|drives /config UI + validation| ovfile
  envmod --> consumers
  note["Precedence: overrides > .env > built-in default.\nADMIN_TOKEN & bootstrap vars are runtime-exempt\n(not editable from the UI they protect)."]
  envmod -.-> note
```

- Single source of env reads: `phoenixadult/config/env.py` — an `_Env` instance with lazy `@property` getters so a runtime override (or a test mutating `os.environ`) is reflected immediately.
- `phoenixadult/config/__init__.py` bootstraps the process: `load_dotenv()` then `load_overrides()`, and exposes the immutable startup `config` snapshot (`port`, `base_url`, `log_level`). Base URL env var is `PHOENIX_BASE_URL` (default `http://localhost:3000`).
- `phoenixadult/config/env_catalog.py` (`ENV_CATALOG`, `EnvVarSpec`, `normalize_env_value`) is the authority for what the config UI may edit and how values validate/normalize.
- `phoenixadult/config/env_overrides.py` (`set_override` / `clear_override` / `load_overrides`, file `env.overrides.json`) persists UI edits and re-applies them on boot — **this is the #1 debugging gotcha** (a stale override silently shadows `.env`).

---

## 12. Deployment

```mermaid
flowchart LR
  classDef n fill:#1e2433,stroke:#6366f1,color:#e2e8f0;
  plex["Plex Media Server"]:::n
  proc["uvicorn process (FastAPI)<br/>:PORT"]:::n
  disk["Local disk<br/>image cache · manual NFO · logs · overrides"]:::n
  flare["FlareSolverr container (optional)"]:::n
  net["Internet (upstream sites, photo sources)"]:::n

  plex <-->|HTTP| proc
  proc <-->|fs| disk
  proc -->|HTTP| flare
  proc -->|HTTPS| net
```

Single stateless-ish uvicorn process (state = on-disk caches + overrides). Run it with `python -m phoenixadult.main` (it calls `uvicorn.run`, auto-reloading outside production). Restart is supervised: `POST /config/api/restart` sends `SIGTERM` to its own PID and relies on a process supervisor to relaunch. FlareSolverr is an optional sidecar.

---

## 13. Patterns & Conventions (Map to Code)

| Pattern | Where | Why |
|---|---|---|
| Template Method / field hooks | `Client.search` / `fetch_scene_detail` + hooks | one orchestration, 178 site variations |
| Strategy / Registry dispatch | `get_client` → `CLIENT_REGISTRY`; `ScraperConfig` union | data selects behavior |
| Adapter | `MetadataMapper` (SceneDetail → Plex schema) | isolate Plex contract |
| Chain of Responsibility | bypass chain; people-source order | ordered fallback |
| Facade | Services over scraper/mapper/people | thin routes |
| Guard / Boundary validation | `ssrf_guard`, `_safe_path`, `env_auth_guard` | trust boundaries |
| Lazy config accessor | `phoenixadult/config/env.py` property getters | testability + runtime overrides |
| Fail-fast + deferred work | `ScenePacer` + `scrape_queue` + serve budgets | Plex's 90s timeout vs. slow, ban-prone sites |

**Conventions:** every scraper is hand-written (no shared `JsonClient`); shared helpers are explicit (`GraphQLClient`, `html_helpers`, image adapters). HTML parsing is **XPath-only via parsel** (lxml-backed). `RawCaptureEntry` capture entries thread raw upstream responses to the dev UI. Optional web-search augmentation (`web_search_available` / `web_search`, `phoenixadult/utils/searchengines/`) provides a "find scene URL via search engine" path and is used by a number of clients (e.g. `adultempire`, `colette`, `girlsoutwest`). Commits follow Conventional Commits; the pre-commit gate is `ruff format` → `ruff check` → `mypy app` → `pytest` (tests use **pytest + respx**).

---

## 14. Directory Map (Orientation)

```
phoenixadult/
  main.py, app_factory.py    # uvicorn entrypoint + FastAPI wiring/bootstrap
  routes/                    # provider_router, image_routes, env_routes, dev_routes,
                             #   metadata_cache_routes, people_cache_routes, logo_routes,
                             #   queue_routes, plex_routes (+ html/)
  services/                  # match_service, metadata_service, scraper_router, scrape_queue,
                             #   plex_reconcile, plex_account, plex_import
  mappers/                   # metadata_mapper
  clients/                   # base Client (base.py) + 180 dedicated clients:
                             #   sites/ (93), networks/ (76), aggregators/ (11)
  registry/                  # ProviderInfo / SiteInfo / ResolvedSiteInfo, site_info,
                             #   selectors/ (site-definition modules, sites/networks/aggregators)
  models/                    # scraper_config (union), metadata, provider_info, media_provider
  graveyard/                 # retired scrapers, imported by nothing (see §Archive)
  utils/
    http/                    # client (make_http), bypass, flaresolverr, playwright, reqbin,
                             #   ssrf_guard, rate_limit_helper (ScenePacer)
    images/                  # image_fetcher, image_classifier, image_referers, logo_cache,
                             #   fanart, fansite_adapters
    people/                  # PeopleManager (__init__), sources/, cache, gender, generic, data
    processors/              # filename_parser, search_query, similarity, title_case, studio_name,
                             #   abbreviations, actor_strip
    concurrency/             # pools (named thread pools), coalescer, single_flight
    logging/, genres/, captcha/, cookies/, helpers/
  config/                    # env, env_catalog, env_overrides, __init__
scripts/                     # generate_sitelist, site_health, start-with-tunnel.ps1
docs/DESIGN.md               # this document
tests/                       # pytest + respx unit / client / selector / health fixtures
```

**Useful commands:** `NODE_ENV=development python -m phoenixadult.main` (dev, auto-reload) · `python -m phoenixadult.main` (run) · `python -m scripts.generate_sitelist` (site list) · `python -m scripts.site_health` (health) · `pwsh scripts/start-with-tunnel.ps1` (tunnel).

---

---

## Appendix A — Title-Case Parser Model

`title_case()` (`phoenixadult/utils/processors/title_case.py`) normalizes scraped titles and
actor names for Plex. It is a small pipeline: a stateless transform built from a
tokenizer, a per-word rule engine driven by lookup tables, and a post-process
regex stage. It is invoked by `MetadataMapper` (clean title + genre labels) and
`MatchService` (display title) and by `PeopleManager` (actor names, `type='name'`),
so it runs on every result and every actor name.

### A.1 Pipeline

```mermaid
flowchart LR
  classDef u fill:#1e2433,stroke:#64748b,color:#cbd5e1;
  inp["input (≤ MAX_TITLE_LENGTH, capped)"]:::u
  pre["pre-process<br/>underscores, smart quotes, w/ , spacing"]:::u
  tok["tokenize<br/>word / space / symbol / punct"]:::u
  rules["apply word rules<br/>normalize_word per token + capitalize first word"]:::u
  rec["reconstruct<br/>join tokens"]:::u
  post["post-process<br/>six named passes (below)"]:::u
  out["normalized title"]:::u

  inp --> pre --> tok --> rules --> rec --> post --> out
```

The post-process stage runs six named passes in order (`_post_process`):

1. `_normalize_quotes_and_articles` — straighten smart quotes; rotate a trailing `", The"`/`", A"`/`", An"` to the front.
2. `_fix_spacing` — space after sentence punctuation (domain suffixes exempt), strip stray spaces before punctuation, balance quote spacing.
3. `_capitalize_boundaries` — capitalize after sentence/bracket boundaries, before a spaced dash (segment-final, so `… Move In - Part Two` cases hold), and the final word.
4. `_normalize_initials` — collapse spaced initialisms (`J. J.` → `J.J.`), apply `collapse_initial_pairs`, normalize `vs.`.
5. `_fix_grammar` — `s's`→`s'` possessives, a/an agreement (with `u`-sound exceptions), honorifics get their period (skipped for `type='name'`).
6. `_finish_by_type` — titles get `normalize_sequence_separator`; then `expand_initial_pairs`, `W/`→`w/`, and per-scraper phrase corrections (`SCRAPER_PHRASE_CORRECTIONS`).

### A.2 Per-Word Decision Cascade (`normalize_word`)

```mermaid
flowchart TB
  classDef u fill:#1e2433,stroke:#64748b,color:#cbd5e1;
  classDef d fill:#3b0764,stroke:#c084fc,color:#fff;

  w["word"]:::u
  s{"== site_name?"}:::d
  sym{"contains - / . + ' ?"}:::d
  con{"contraction suffix?"}:::d
  acr{"acronym / size code / 2-4 all-caps?"}:::d
  up{"in UPPER_EXCEPTIONS?"}:::d
  allcaps{"ALL CAPS & not lower-exc?"}:::d
  low{"in LOWER_EXCEPTIONS?"}:::d
  mix{"mixed-case brand?"}:::d
  def["capitalize (default)"]:::u
  mf["manual word fix<br/>(MANUAL_CORRECTIONS)"]:::u

  w --> s
  s -- yes --> mf
  s -- no --> sym
  sym -- yes --> mf
  sym -- no --> con
  con -- yes --> con2["keep base + lower suffix"]:::u --> mf
  con -- no --> acr
  acr -- yes --> acrU["UPPER"]:::u --> mf
  acr -- no --> up
  up -- yes --> upU["UPPER"]:::u --> mf
  up -- no --> allcaps
  allcaps -- yes --> upU
  allcaps -- no --> low
  low -- yes --> lowU["lower"]:::u --> mf
  low -- no --> mix
  mix -- yes --> asis["leave as-is"]:::u --> mf
  mix -- no --> def --> mf
```

### A.3 Rule Tables (Data That Drives Behavior)

| Table | Purpose | Examples |
|---|---|---|
| `LOWER_EXCEPTIONS` | small words kept lowercase mid-title | of, the, and, vs |
| `TLD_FRAGMENTS` | lowercased only as a domain suffix, else normal words | co, com, org |
| `SPANISH_LOWER_EXCEPTIONS` / `SPANISH_SITE_KEYS` | Spanish small words, applied on Spanish-language sites | de, del, con / fakings, sexmex |
| `UPPER_EXCEPTIONS` | force uppercase | bbc, xxx, pov, milf, usa |
| `ACRONYMS` / `SIZE_CODES` | uppercase tech/size tokens | vr, hd, 4k / xs, xl, xxl |
| `CONTRACTIONS` | suffixes kept lowercase after an apostrophe | 're, 't, 'll, 've |
| `HONORIFICS` / `ROMAN_NUMERALS` | grammar-pass period fix / sequence-number detection | mr, dr / ii, iv, xii |
| `INITIAL_PAIRS` | two-letter stage names kept as initials | AJ → A.J., TJ → T.J. |
| `SYMBOL_RULES` | how `- / . + '` split + rejoin | `.`→initials/acronym, `'`→contraction |
| `MANUAL_CORRECTIONS` | exact restylings | dont→Don't, mccray→McCray, milfs→MILFs |
| `SCRAPER_PHRASE_CORRECTIONS` | per-scraper phrase restylings | strike3: a game→A Game |
| `NAME_EXCEPTION_SITES` | site-specific name casing | JavBus, JAVDatabase |

These tables are functional config consumed inline by the engine, so they live in
`title_case.py` rather than in `_data/json`.

### A.4 Robustness — ReDoS Guard

The post-process stage includes O(n²) passes that backtrack badly on long
whitespace-free input. Real titles/names are short, so `title_case()` caps input
at `MAX_TITLE_LENGTH` (1000) before parsing — this bounds the worst case to
~1e6 ops (instant) and removes the event-loop-block DoS without altering output
for realistic inputs.

```mermaid
flowchart LR
  classDef u fill:#1e2433,stroke:#64748b,color:#cbd5e1;
  classDef g fill:#14532d,stroke:#4ade80,color:#fff;
  a["scraped title (any length)"]:::u --> cap{"len > 1000?"}:::g
  cap -- yes --> trunc["text[:1000]"]:::g --> eng["engine"]:::u
  cap -- no --> eng
```

### A.5 Companion Helpers (Module Exports)

```mermaid
flowchart LR
  classDef u fill:#1e2433,stroke:#64748b,color:#cbd5e1;
  t["title"]:::u
  art["strip leading article<br/>(The/A/An)"]:::u
  conv["_convert_bounded_numbers<br/>(spelled-out → digits, only<br/>touching a sequence marker)"]:::u
  ts["title_sort → sort value | None"]:::u
  csn["convert_sequence_numbers → digits | None"]:::u

  t --> art --> conv --> ts
  t --> conv --> csn
```

Beyond `title_case()`, the module exports helpers used by the mapper and clients:

- `normalize_sequence_separator` — folds the separator before a numbered sequence marker into `: ` (`… - Scene 4` / `… (Part 2)` → `…: Scene 4` / `…: Part 2`); a marker word followed by a non-number is left alone. Applied automatically for `type='title'`.
- `title_sort` — Plex `titleSort` value: strips the leading article and digit-converts marker-bounded spelled-out numbers (`Episode Twelve` → `Episode 12`, via `text2digits`); returns `None` when it wouldn't differ. Emitted by the mapper and backfilled into cached snapshots.
- `convert_sequence_numbers` — the digit conversion alone, no article strip; also `None` on no change. Used in title-similarity scoring and data18's search fallback.
- `collapse_initial_pairs` / `expand_initial_pairs` — round-trip `A. J.` ↔ `A.J.` so spacing passes can't split known two-letter stage names (`INITIAL_PAIRS`); also used directly by clients that rebuild summaries (e.g. `pornbox`).

---

*Diagrams render in the repo's Markdown viewer (Mermaid — supported on both GitHub and Codeberg). Update them alongside the code they model — a stale model is worse than none.*
