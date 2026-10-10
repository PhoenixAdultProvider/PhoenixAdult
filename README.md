# PhoenixAdult Provider (FastAPI)

This FastAPI metadata agent helps fill Plex with information for your adult videos, connecting to Plex as a Metadata Provider. It is an evolution of the legacy [PhoenixAdult.bundle](https://github.com/PAhelper/PhoenixAdult.bundle) Plex agent, ported onto Plex's newer Metadata Provider API. Please note porting the existing scrapers will take some time. It is currently in alpha and is co-authored with Claude to migrate the bundle to the new Metadata API framework.

## Disclaimer

This repository contains **source code only** — a FastAPI metadata bridge between Plex Media Server and adult-industry websites' publicly accessible metadata (titles, release dates, performer credits, scene URLs). No media, images, video, or other copyrighted content is hosted, distributed, or redistributed by this project.

Users self-host the provider on their own hardware to enrich Plex libraries with metadata for content they have legitimately obtained access to elsewhere. The scraper does not bypass paywalls, media file DRM, or site authentication — when an upstream site requires a login, the user supplies their own credentials.

**Issues, pull requests, and discussions in this repository must remain text-only.** Do not attach or link to screenshots, posters, thumbnails, cast photos, or any other media content from adult-industry sites. URLs to scene pages are text and may be shared; the images those URLs resolve to may not. See the [bug-report template](.github/ISSUE_TEMPLATE/bug_report.yml) for what's appropriate to include in a report.

Contributors who repeatedly include media content in issues will be blocked. The project complies with the acceptable-use policies of the hosts it's published on (e.g. GitHub's [Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)) regarding sexually obscene content — content of that kind is explicitly **out of scope** for this repository.

## File Naming
The agent matches your file automatically, usually from the filename, so renaming a video to the expected pattern is the single best thing you can do to help it.
If a video does not match, match it by hand with Plex's [Match…] function — see the [manual searching document](./docs/manualsearch.md).
The naming each site expects is listed in the [sitelist document](./docs/sitelist.md).

Specific filename patterns and examples are available in the [file naming document](./docs/file-naming.md)

## Supported Networks
To view the full list of supported sites, [check out the sitelist doc](./docs/sitelist.md). New site requests are closed for now, and issues are disabled with them, so the time goes into porting, integrating and testing the scrapers that already exist. A site that is broken in the legacy bundle is skipped here too unless it can be fixed. For which sites have been tested so far, see the [Scraper Test Plan](./docs/scraper-test-plan.md) — some not yet listed may already work.

## Develop

### Environment Setup

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows
pip install -e ".[dev]"
cp .env.example .env

# .env.example ships NODE_ENV=production; set development for local work + the /dev UI.
# Outside production this auto-reloads on change; PORT (default 3000) sets the port.
NODE_ENV=development python -m phoenixadult.main
```

- Health: `GET /health`
- First-run setup: `GET /setup` — creates the first (admin) account
- Sign in: `GET /login`; account and API key: `GET /account`
- Config UI: `GET /config` (signed in)
- Dev UI: `GET /dev` — the scraper test bench (needs `DEV_UI_ENABLE`)
- People cache: `GET /people` — browse and manage cached cast & crew headshots (actors, directors, producers) and gender tags (needs `PEOPLE_CACHE_ENABLE`)
- Metadata cache: `GET /metadata` — filterable view of frozen scene snapshots, with per-scene purge and refresh (needs `METADATA_CACHE_ENABLE`)
- Logo cache: `GET /logos` — the clearLogo wall, with `GET /logos/add` to file a new one
- Scrape queue: `GET /queue` — background searches and metadata updates deferred by pacing
- Stored searches: `GET /searches` — cached search results, with duplicate spellings grouped
- Plex agent mount: `/<provider>/movies` (e.g. `/phoenixadult/movies`)

Every page needs a signed-in session or an API key. The people and metadata caches and the dev UI are optional, enabled by `PEOPLE_CACHE_ENABLE`, `METADATA_CACHE_ENABLE` and `DEV_UI_ENABLE` in the Config UI.

See the [configuration document](./docs/configuration.md) for every environment variable — with defaults and detailed usage — and the two ways to set them (`.env` at boot vs the runtime Config UI).

Before committing, run the same gate CI runs (see [CONTRIBUTING](./CONTRIBUTING.md#linting-formatting-and-types)):

```bash
ruff format . && ruff check .
python scripts/check_comments.py
mypy phoenixadult
pytest             # add --cov for a coverage report (roughly doubles the runtime)
```

### Clients

Each site/network/database gets its own dedicated `Client` subclass under
`phoenixadult/clients/` — grouped into `aggregators/` (databases like Data18, JavBus),
`networks/` (multi-site networks), and `sites/` (single sites). Clients are discovered
automatically, keyed on their module name, with their URL/selector definitions in
`phoenixadult/registry/selectors/`. Start a new one with
`python scripts/new_scraper.py --name "Foo Bar" --base-url https://foo.bar --kind sites`.

Each client should prefer the base **field-hook orchestrator** —
override `load_scene_context` + the per-field `fetch_*` hooks (`fetch_title`,
`fetch_actors`, `fetch_image_urls`, …) rather than re-implementing
`fetch_scene_detail` end to end. HTML extraction uses **XPath** via parsel.

## Hosting

Plex fetches cast photos and collection logos from the provider itself, and from Plex Media Server
1.43.5 it only accepts **publicly reachable** image URLs. Behind a home network that means a stable
public hostname, such as a named Cloudflare Tunnel, which can be limited to the image routes.

See the [hosting document](./docs/hosting.md) for tunnels, Windows, Docker, the FreeBSD port and
systemd, and for signing in to the admin pages through a tunnel. The full design reference lives in
[docs/design](./docs/design/index.md).
