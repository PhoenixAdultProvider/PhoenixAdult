---
sidebar_label: Components
description: Containers and components of the provider (C4 Level 2).
---

# Components (C4 Level 2)

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
    cr["env_routes<br/>/config/*  (user_auth_guard + csrf_guard; admin_auth_guard on writes)"]:::r
    dr["dev_routes<br/>/dev/*  (user_auth_guard + csrf_guard + admin_auth_guard)"]:::r
  end

  subgraph svc["Services"]
    ms["MatchService"]:::s
    md["MetadataService"]:::s
    mm["MetadataMapper"]:::s
    sq["scrape_queue<br/>(deferred background work)"]:::s
  end

  subgraph scr["Scraper engine"]
    srt["ScraperRouter<br/>(type → Client via get_client)"]:::c
    cli["one Client subclass per scraper<br/>(sites / networks / aggregators)"]:::c
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
    ppl["PeopleResolver<br/>+ photo sources + cache"]:::u
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

## Key Relationships

- **Routes are thin.** `provider_router` (`phoenixadult/routes/provider_router.py`) delegates immediately to `MatchService` / `MetadataService`.
- **`ScraperRouter`** (`phoenixadult/services/scraper_router.py`) is a dispatcher: it resolves a scraper `type` to its single `Client` instance via `get_client` (`phoenixadult/clients/__init__.py`, `CLIENT_REGISTRY`). It owns `search`, `fetch_scene_detail`, and `decode`.
- **`MetadataMapper`** (`phoenixadult/mappers/metadata_mapper.py`) translates the scraper's `SceneDetail` into Plex's schema and rewrites every image URL through the `/images/proxy` endpoint.
- **Registry** is static data: providers, sites, and per-site `ScraperConfig` that selects and parameterizes a client.
- **`scrape_queue`** (`phoenixadult/services/scrape_queue.py`) runs background jobs on two lanes (dedup by key, 10,000-job cap): unpaced sites take five workers, sites behind a `ScenePacer` take exactly one, so a pacer's gate can never occupy every slot. When pacing or the serve budget defers a search/update (see [Concurrency](./concurrency.md)), the services enqueue it here to finish off the request path.
- **`FAST_GATE`** (`phoenixadult/utils/http/rate_limit_helper.py`) caps unpaced scene scrapes at five concurrent slots shared across all unpaced sites, inline and background alike (re-entrant per task, so a client that delegates to another client reuses its slot). An inline refresh waits up to the 10s sync budget for a slot, then raises `PacingDeferredError` and lands in the visible queue — so every unpaced backlog shows on `/queue`, which also renders the gate's busy/waiting counts. Searches on unpaced sites stay inline and ungated.
