---
sidebar_label: Conventions
description: The design patterns the code follows, coding conventions, and the commit gate.
---

# Patterns and Conventions

## Patterns (Mapped to Code)

| Pattern | Where | Why |
|---|---|---|
| Template Method / field hooks | `Client.search` / `fetch_scene_detail` + hooks | one orchestration, every site variation |
| Strategy / registry dispatch | `get_client` → `CLIENT_REGISTRY`; `ScraperConfig` union | data selects behavior |
| Adapter | `MetadataMapper` (SceneDetail → Plex schema) | isolate the Plex contract |
| Chain of Responsibility | bypass chain; people-source order | ordered fallback |
| Facade | services over scraper, mapper and people | thin routes |
| Guard / boundary validation | `ssrf_guard`, `safe_join`, `user_auth_guard` | trust boundaries |
| Lazy config accessor | `phoenixadult/config/env.py` property getters | testability and runtime overrides |
| Fail-fast + deferred work | `ScenePacer` + `scrape_queue` + serve budgets | Plex's 90s timeout vs. slow, ban-prone sites |

## Coding Conventions

- **Hand-written scrapers.** No shared `JsonClient`; shared helpers are explicit (`GraphQLClient`, `html_helpers`, image adapters). See [Scrapers](./scrapers.md).
- **XPath only.** HTML parsing goes through parsel (lxml-backed).
- **Dev UI capture.** `RawCaptureEntry` entries thread raw upstream responses to the dev UI.
- **Web search.** Optional web-search augmentation finds a scene URL through a search engine for clients that need it (`adultempire`, `colette`, `girlsoutwest` and others):
  - clients reach it through one helper, `web_search_urls` (`html_helpers`), which derives the `site:` operator from the client's own `base_url` and applies `include`/`exclude` substring filters;
  - the engine chain lives in `phoenixadult/utils/searchengines/`;
  - only clients that search a *third-party* domain (`javlibrary`, `xart`) call the low-level `web_search` directly.
- **No display text in code.** Every web UI string is a key in `phoenixadult/i18n/en.po` (see [Web UI](./web-ui.md#localization)).
- **Commits** follow Conventional Commits.

## Commit Gate

Run before every commit; CI runs the same checks:

| Step | Command |
|---|---|
| Format | `ruff format` (CI runs `ruff format --check`) |
| Lint | `ruff check` |
| Comments | `python scripts/check_comments.py` (CI checks the commit's own diff) |
| Types | `mypy phoenixadult` |
| Tests | `pytest` — includes the strings check (`scripts.i18n check`) and the event-loop guards |

Tests use **pytest + respx**. Coverage is opt-in (`pytest --cov`), because instrumenting the suite costs about as much as running it.
