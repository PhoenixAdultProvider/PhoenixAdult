---
sidebar_label: Directory Map
description: Where things live in the repository.
---

# Directory Map

```
phoenixadult/
  main.py, app_factory.py    # uvicorn entrypoint + FastAPI wiring and lifespan
  routes/                    # provider_router + provider_guard, image, env (config), auth, dev,
                             #   metadata/people cache, logo, queue, search, plex routes (+ html/)
  services/                  # match_service, metadata_service, scraper_router, scrape_queue,
                             #   plex_connections, plex_account, plex_import, plex_reconcile,
                             #   plex_jobs, snapshot_backfill, provider_errors
  mappers/                   # metadata_mapper
  clients/                   # base Client (base.py) + one client per scraper, auto-discovered:
                             #   sites/, networks/, aggregators/
  registry/                  # ProviderInfo / SiteInfo / ResolvedSiteInfo,
                             #   selectors/ (site-definition modules: sites/networks/aggregators)
  models/                    # scrape (SearchContext/SearchResult/SceneDetail/ActorResult), capture,
                             #   scraper_config (union), site_info, metadata, provider_info
  graveyard/                 # retired scrapers and people sources, imported by nothing
  i18n/                      # en.po (every web UI string, keyed) + gettext/strings loaders
  config/                    # env, env_catalog, env_overrides
  utils/
    auth/                    # sessions, users, API keys, passwords, image guard, URL signing
    cache/                   # snapshot read/write/edit, scene_store, search_store, duplicates,
                             #   integrity, layout, listing, locks, text_rules, bundle_sweep
    concurrency/             # pools (named thread pools), gate, coalescer, single_flight
    db/                      # SQLite connections, schema, maintenance (backup, integrity)
    fs/                      # safe paths, atomic writes, JSON I/O, reloadable files
    http/                    # client (make_http), connectivity, ssrf_guard, pinned_fetch,
                             #   bypass + backends, rate_limit_helper (ScenePacer)
    images/                  # image_fetcher, image_classifier, image_referers, face_crop,
                             #   logo_cache, logo_template, fanart, fansite_adapters
    people/                  # PeopleResolver (__init__), sources/, cache, gender, generic, data
    plex/                    # rating keys, Plex responses, client hits, daily quotas
    processors/              # filename_parser, search_query, similarity, title_case, studio_name,
                             #   abbreviations, actor_strip
    searchengines/           # Google CSE, DuckDuckGo, metasearch (ddgs)
    logging/, genres/, captcha/, cookies/, helpers/
scripts/                     # new_scraper, generate_sitelist, site_health, i18n, check_comments,
                             #   bump_version, reset_password, rename_studio, start-with-tunnel.*
docs/                        # user docs; design/ holds these pages
website/                     # Docusaurus site that publishes docs/
packaging/systemd/           # Debian/Ubuntu unit + installer
.forgejo/, .github/          # CI, docs deploys, Docker check, Dependabot
tests/                       # pytest + respx: unit, client, selector, route and health fixtures
```

## Useful Commands

| Command | Does |
|---|---|
| `NODE_ENV=development python -m phoenixadult.main` | run in development, auto-reloading |
| `python -m phoenixadult.main` | run |
| `python scripts/new_scraper.py --name "…" --base-url … --kind sites` | scaffold a new scraper |
| `python -m scripts.generate_sitelist` | regenerate `docs/sitelist.md` |
| `python -m scripts.site_health` | live health sweep into `docs/site-health.md` |
| `python -m scripts.i18n check` | check the UI strings file against the code |
| `pwsh scripts/start-with-tunnel.ps1` | Windows: quick tunnel + app |
