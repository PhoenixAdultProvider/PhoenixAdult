---
sidebar_label: Request Flows
description: Sequence models for match, metadata, bypass, image proxy and config requests.
---

# Request Flows

## Match — `POST /library/metadata/matches`

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

## Metadata — `GET /library/metadata/{rating_key}`

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
  participant PM as PeopleResolver
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

## Provider Status Codes

Both features answer with the four codes Plex defines for metadata providers:

| Code | Match | Metadata |
|------|-------|----------|
| 200 | Results, or an empty MediaContainer (suppressed request, no registry site in the filename, no perfect auto match, site down while the internet is up) | Scraped or cached scene |
| 400 | No title/filename to parse | Malformed ratingKey: bad format, missing parts, unknown site, undecodable curID |
| 404 | Never | Valid ratingKey whose scene yields nothing while online |
| 500 | Pacing deferral, Plex-budget timeout, no network connectivity, unexpected exception | Same |

- **Error types.** Requests that can never succeed raise `MalformedRequestError`; transient failures raise `ProviderUnavailableError` (`services/provider_errors.py`). The router maps them to 400 and 500.
- **Site down or offline?** Connectivity is judged only when a scrape came up empty *and* the shared HTTP transport recorded a transport-level failure (DNS or connect). The shared connectivity probe — TCP to 1.1.1.1/8.8.8.8 plus a DNS lookup, cached 15s — then decides between "site down" (200/404) and "offline" (500). See [HTTP and Bypass](./http-bypass.md#network-down-fast-fail).
- **Tracing.** At `LOG_LEVEL=verbose` every match and metadata request is dumped with full headers and JSON body.

## Scraper Fetch with Anti-Bot Bypass Fallback

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

## Image Proxy — `GET /images/proxy?url=…`

```mermaid
sequenceDiagram
  autonumber
  participant Plex
  participant IR as image_routes
  participant G as ssrf_guard.assert_fetchable_url
  participant IF as image_fetcher
  participant UP as Image host

  Plex->>IR: GET /images/proxy?url=…&referer=…&cookie=…
  alt failed for this url in the last 10 min
    IR-->>Plex: 502 (remembered)
  else network down
    IR-->>Plex: 503 (no lookup attempted)
  end
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

- **Remembered failures.** A failed upstream fetch is remembered for ten minutes per URL, referer and cookie set, and answered 502 at once. Failures while the network is down are not remembered, so images return as soon as the connection does.
- **Network down.** The proxy answers 503 before resolving anything (see [HTTP and Bypass](./http-bypass.md#network-down-fast-fail)), so a page full of images cannot queue behind a dead resolver.
- **Pinned fetch.** With `IMAGE_PROXY_PIN` (on by default) the fetch connects to the IP the guard validated, closing the DNS-rebinding gap for this route.
- **Classified variant.** `/images/proxy-classified` is the same flow plus a `classify_image(width, height)` step. It returns 404 when the image classifies as `unknown` and stamps `X-Image-Type` on success.

## Runtime Config Override

```mermaid
sequenceDiagram
  autonumber
  participant Op as Operator
  participant AG as user_auth_guard + admin_auth_guard
  participant CR as env_routes
  participant OV as env_overrides
  participant FS as env.overrides.json

  Op->>AG: POST /config/api/save {updates}
  alt no session cookie and no valid API key
    AG-->>Op: 401 (browsers: 302 to /login)
  else signed in but not an admin
    AG-->>Op: 403
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
