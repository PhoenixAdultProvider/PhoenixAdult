# PhoenixAdult Provider (FastAPI)

This FastAPI metadata agent helps fill Plex with information for your adult videos, connecting to Plex as a Metadata Provider. It is an evolution of the legacy [PhoenixAdult.bundle](https://github.com/PAhelper/PhoenixAdult.bundle) Plex agent, ported onto Plex's newer Metadata Provider API. Please note porting the existing scrapers will take some time. This is currently a proof of concept co-authored with Claude for seeing how to migrate to the new Metadata API framework.

## Disclaimer

This repository contains **source code only** — a FastAPI metadata bridge between Plex Media Server and adult-industry websites' publicly accessible metadata (titles, release dates, performer credits, scene URLs). No media, images, video, or other copyrighted content is hosted, distributed, or redistributed by this project.

Users self-host the provider on their own hardware to enrich Plex libraries with metadata for content they have legitimately obtained access to elsewhere. The scraper does not bypass paywalls, media file DRM, or site authentication — when an upstream site requires a login, the user supplies their own credentials.

**Issues, pull requests, and discussions in this repository must remain text-only.** Do not attach or link to screenshots, posters, thumbnails, cast photos, or any other media content from adult-industry sites. URLs to scene pages are text and may be shared; the images those URLs resolve to may not. See the [bug-report template](.github/ISSUE_TEMPLATE/bug_report.yml) for what's appropriate to include in a report.

Contributors who repeatedly include media content in issues will be blocked. The project complies with the acceptable-use policies of the hosts it's published on (e.g. GitHub's [Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)) regarding sexually obscene content — content of that kind is explicitly **out of scope** for this repository.

## File Naming
The agent will try to match your file automatically, usually based on the filename. You can assist it by renaming your video appropriately.
If the video is not successfully matched, you can try to manually match it using the [Match...] function in Plex. See the [manual searching document](./docs/manualsearch.md) for more information.
Best practice for each site is listed in the [sitelist document](./docs/sitelist.md).

Specific filename patterns and examples are available in the [file naming document](./docs/file-naming.md)

## Supported Networks
To view the full list of supported sites, [check out the sitelist doc](./docs/sitelist.md). Requesting New sites is not currently being supported at this time and issues are currently disabled, so that time can be given to port, integrate and test all the exisitng scrapers. Any sites/networks that are currently broken on the main scraper will be skipped in this scraper if they cannot be fixed. For the current status of which sites have been tested please see the [Scraper Test Plan](./docs/scraper-test-plan.md) (note some sites may already be working).

## Develop

### Enviroment Setup

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows
pip install -e ".[dev]"
cp .env.example .env

# .env.example ships NODE_ENV=production; set development for local work + the /dev UI.
# Outside production this auto-reloads on change; PORT (default 3000) sets the port.
NODE_ENV=development python -m app.main
```

- Health: `GET /health`
- Config UI: `GET /config` (loopback or `ADMIN_TOKEN`)
- Dev UI: `GET /dev` (non-production, loopback or `ADMIN_TOKEN`)
- People-cache review: `GET /people-cache` — browse/manage cached cast & crew headshots (actors, directors, producers) and gender tags (needs `PEOPLE_CACHE_ENABLE`)
- Metadata-cache review: `GET /metadata-cache` — sortable/filterable table of frozen scene snapshots, with per-row purge (needs `METADATA_CACHE_ENABLE`)
- Plex agent mount: `/<provider>/movies` (e.g. `/phoenixadult/movies`)

The two cache surfaces are admin-guarded the same way as `/config` and `/dev` (loopback or `ADMIN_TOKEN`). They're optional, off by default, and enabled via their `*_ENABLE` env vars in the Config UI.

See the [configuration document](./docs/configuration.md) for every environment variable — with defaults and detailed usage — and the two ways to set them (`.env` at boot vs the runtime Config UI).

Lint / type-check / test:

```bash
ruff check . && ruff format --check .
mypy app
pytest
```

### Clients

Each site/network/database gets its own dedicated `Client` subclass under
`app/clients/` — grouped into `aggregators/` (databases like Data18, JavBus),
`networks/` (multi-site networks), and `sites/` (single sites). Every client is
registered by its scraper-config `type` in `app/clients/__init__.py`, with its
URL/selector definitions in `app/registry/selectors/`.

Each client should prefer the base **field-hook orchestrator** —
override `load_scene_context` + the per-field `fetch_*` hooks (`fetch_title`,
`fetch_actors`, `fetch_image_urls`, …) rather than re-implementing
`fetch_scene_detail` end to end. HTML extraction uses **XPath** via parsel.

## Cloudflare Tunnel

`scripts/start-with-tunnel.ps1` is a one-click launcher (Windows / PowerShell).
It downloads `cloudflared.exe` on first run, opens an ephemeral
`https://*.trycloudflare.com` quick tunnel to `http://localhost:3000`, writes
that URL into `.env` as `PHOENIX_BASE_URL`, then starts the app
(`python -m app.main`, which auto-reloads in dev). Ctrl+C tears the tunnel down.

```bash
pwsh -ExecutionPolicy Bypass -File scripts/start-with-tunnel.ps1
# Windows PowerShell 5.1:
powershell -ExecutionPolicy Bypass -File scripts/start-with-tunnel.ps1
# custom local port:
pwsh -ExecutionPolicy Bypass -File scripts/start-with-tunnel.ps1 -Port 8080
```

No Cloudflare account or domain is required; the URL is ephemeral and changes on
every run. The script prefers the project `.venv` interpreter and sets `PORT` so
the agent listens on the tunnel's target port. For a stable URL, set up a named
tunnel with `cloudflared` and point `PHOENIX_BASE_URL` at its hostname.

### Admin surfaces through the tunnel

`/config` and `/dev` are admin-guarded by `ADMIN_TOKEN`:

- **`ADMIN_TOKEN` set** — open on loopback; any remote request (including via the
  tunnel) must present the token.
- **`ADMIN_TOKEN` blank/unset** — auth is **disabled**; the admin surfaces are
  open to anyone who can reach the server. The startup log prints a warning when
  this is the case. Only leave it blank on a trusted/local network.

Over a tunnel with a token set:

1. Set `ADMIN_TOKEN` in `.env` (any secret string) and start the server.
2. Open the page with the token in the URL:
   `https://<sub>.trycloudflare.com/dev?token=YOURTOKEN`
   (same for `/config?token=YOURTOKEN`).

The startup banner prints these admin links with the token already included, so
you can copy them straight from the log. The page forwards the token to its own
API calls, so Search / Fetch / Save work without further steps. The token can
also be sent as an `Authorization: Bearer <token>` or `X-Admin-Token` header.
Note the `?token=` form puts the secret in the URL (browser history, tunnel
access logs) — fine for a dev tunnel, but prefer a header for anything
longer-lived.
