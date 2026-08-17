# PhoenixAdult Provider (FastAPI)

This FastAPI metadata agent helps fill Plex with information for your adult videos, connecting to Plex as a Metadata Provider. It is an evolution of the legacy [PhoenixAdult.bundle](https://github.com/PAhelper/PhoenixAdult.bundle) Plex agent, ported onto Plex's newer Metadata Provider API. Please note porting the existing scrapers will take some time. This is currently in alpha, and is co-authored with Claude, to migrate to the new Metadata API framework.

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
- Dev UI: `GET /dev` (non-production, signed in)
- People cache: `GET /people` — browse and manage cached cast & crew headshots (actors, directors, producers) and gender tags (needs `PEOPLE_CACHE_ENABLE`)
- Metadata cache: `GET /metadata` — filterable view of frozen scene snapshots, with per-scene purge and refresh (needs `METADATA_CACHE_ENABLE`)
- Logo cache: `GET /logos` — the clearLogo wall, with `GET /logos/add` to file a new one
- Scrape queue: `GET /queue` — background searches and metadata updates deferred by pacing
- Stored searches: `GET /searches` — cached search results, with duplicate spellings grouped
- Plex agent mount: `/<provider>/movies` (e.g. `/phoenixadult/movies`)

These surfaces are guarded the same way as `/config` and `/dev` — a signed-in session or an API key. They're optional, off by default, and enabled via their `*_ENABLE` env vars in the Config UI.

See the [configuration document](./docs/configuration.md) for every environment variable — with defaults and detailed usage — and the two ways to set them (`.env` at boot vs the runtime Config UI).

Lint / type-check / test:

```bash
ruff check . && ruff format --check .
mypy phoenixadult
pytest             # add --cov for a coverage report (roughly doubles the runtime)
```

### Clients

Each site/network/database gets its own dedicated `Client` subclass under
`phoenixadult/clients/` — grouped into `aggregators/` (databases like Data18, JavBus),
`networks/` (multi-site networks), and `sites/` (single sites). Every client is
registered by its scraper-config `type` in `phoenixadult/clients/__init__.py`, with its
URL/selector definitions in `phoenixadult/registry/selectors/`.

Each client should prefer the base **field-hook orchestrator** —
override `load_scene_context` + the per-field `fetch_*` hooks (`fetch_title`,
`fetch_actors`, `fetch_image_urls`, …) rather than re-implementing
`fetch_scene_detail` end to end. HTML extraction uses **XPath** via parsel.

## Cloudflare Tunnel

`scripts/start-with-tunnel.ps1` is a one-click launcher (Windows / PowerShell).
It downloads `cloudflared.exe` on first run, opens an ephemeral
`https://*.trycloudflare.com` quick tunnel to `http://localhost:3000`, writes
that URL into `.env` as `PHOENIX_BASE_URL`, then starts the app
(`python -m phoenixadult.main`, which auto-reloads in dev). Ctrl+C tears the tunnel down.

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

### Admin Surfaces Through the Tunnel

Every admin page requires a signed-in user, from a tunnel or from loopback alike:

1. Start the server and open `https://<sub>.trycloudflare.com/setup` on first run to
   create the admin account; afterwards sign in at `/login`. Passwords need 8+ characters
   with an uppercase letter, a number, and a special character.
2. The session cookie carries auth across pages, so links and API calls work with no
   token threading. It is `HttpOnly` and `SameSite=Lax`, and marked `Secure` automatically
   when the tunnel terminates TLS.

For scripts and automation, generate an API key on `/account` (shown once) and send it
as a header — no secret ever lands in a URL, browser history, or tunnel access log:

```bash
curl -H 'Authorization: Bearer pa_…' https://<sub>.trycloudflare.com/metadata/entries
# or: curl -H 'x-api-key: pa_…' …
```

Locked out? Run `python scripts/reset_password.py <username>` on the server (add
`--create-admin` if no admin account remains).
