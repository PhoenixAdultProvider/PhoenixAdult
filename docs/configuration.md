# Configuration

The provider is configured with environment variables. There are **two ways** to set
them, and it's worth understanding how they interact before changing anything.

## Two ways to configure

### 1. Environment / `.env` — boot-time

Set variables in the process environment. The simplest way is a `.env` file in the
working directory (loaded automatically at startup); you can also export real
environment variables or pass them to a container (`docker run -e PORT=3000 …`).

```bash
cp .env.example .env      # then edit
```

- Read **once at startup**, so changes take effect on the next restart.
- Works for **every** variable below — including the server, auth, and network ones
  that are *not* exposed in the Config UI.

### 2. Config UI — runtime

Open **`GET /config`** in a browser (allowed from loopback, or with the `ADMIN_TOKEN`
header/query elsewhere). Edit a value and **Save** and it is written to
`env.overrides.json` and applied live — no restart for most options.

- Covers the **per-feature options** (caching, gender handling, sources, bypass, …) —
  i.e. everything except the boot-only server/auth/network variables.
- **Reset** on a row clears its override and reverts to the `.env`/built-in value.
- A few options are read once at boot and are flagged **“requires restart”**; the UI
  has a **Restart** button for those.

### How they interact (important)

`env.overrides.json` is layered **on top of** the environment at startup, so **a saved
override shadows `.env`**. If a `.env` change doesn't seem to take effect, it's almost
always because the Config UI previously saved an override for that key — clear it with
**Reset** in the UI (or delete the entry from `env.overrides.json`).

- `env.overrides.json` lives in the working directory (or `ENV_OVERRIDES_PATH`) and is
  git-ignored — it holds only the keys you changed in the UI.
- Only UI-editable keys are honored from that file; unknown/boot-only keys are ignored.

### What needs a restart

Most options apply immediately. These are read at boot and need a restart (the Config
UI either isn't where you set them, or flags them): `PORT`, `PHOENIX_BASE_URL`,
`NODE_ENV`, `LOG_LEVEL`, `LOG_DIR`.

---

## Variable reference

Legend: **UI** = editable in the Config UI · **boot** = `.env`/environment only ·
⟳ = takes effect after a restart. Defaults are the value used when the variable is
unset.

### Server &nbsp;·&nbsp; boot

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` ⟳ | `3000` | TCP port the HTTP server binds to. |
| `PHOENIX_BASE_URL` ⟳ | `http://localhost:3000` | Public base URL the provider advertises to Plex. Behind a reverse proxy or Cloudflare tunnel, set this to the externally reachable URL — it's the base for served image/poster links (see `PEOPLE_IMAGE_URL` for actor images specifically). |
| `NODE_ENV` ⟳ | `production` | `production` enables prod behavior (host redaction defaults on, no auto-reload, `/dev` disabled). Set `development` (or `dev`/`test`/`local`) for local work and the `/dev` UI. |

### Admin auth &nbsp;·&nbsp; boot

| Variable | Default | Description |
| --- | --- | --- |
| `ADMIN_TOKEN` | _(unset)_ | Guards the admin surfaces (`/config`, `/dev`, `/people-cache`, `/metadata-cache`). When unset, those are reachable **from loopback only**. Set a token to reach them from another host (sent as the `x-admin-token` header or a `token` query param). |

### Logging

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` ⟳ · UI | `info` | Verbosity: `error`, `warn`, `info`, `http`, `verbose`, `debug`. |
| `LOG_DIR` ⟳ · boot | `./logs` | Directory for the rolling `agent.log` file. |
| `LOG_REDACT_HOSTS` · UI | on in `production`, else off | Additionally masks the server's own host/FQDN (from `PHOENIX_BASE_URL`) in logs. **IP addresses are always redacted, in every environment** — this flag only affects the hostname. |
| `LOG_REDACT_TOKEN` · UI | `false` | Masks secret query values (`?token=…`, `?apikey=…`, `?password=…`) in logs. Off by default so you can see the admin token in URLs while testing. |

### Images

| Variable | Default | Description |
| --- | --- | --- |
| `IMAGE_DIR` · UI | `./local/images` | Directory of local image files served back to Plex. |
| `IMAGE_MAX_BYTES` · UI | `20M` | Hard ceiling on a single upstream image fetch; larger images are rejected. Accepts a byte count or a size like `20M`, `2000K`, `100B`. |

### Manual NFO

| Variable | Default | Description |
| --- | --- | --- |
| `MANUAL_NFO_PATH` · UI | `./local/manual` | Root folder served by the “Manual NFO” scraper. |
| `MANUAL_NFO_TOKEN` · UI | `manual` | Leading filename token that pins a match request to the Manual NFO scraper. |

See the [manual searching](./manualsearch.md) doc for how manual matching works.

### Metadata cache

| Variable | Default | Description |
| --- | --- | --- |
| `METADATA_CACHE_ENABLE` · UI | `false` | Snapshot each scraped scene's metadata + images under the cache dir and serve cache-first afterward — offline-safe protection against a source going down or changing its anti-scrape. Manage/purge at `/metadata-cache`. |
| `METADATA_CACHE_DIR` · UI | `./local/cache` | On-disk location for those snapshots (text + images). |

### People cache & sources

| Variable | Default | Description |
| --- | --- | --- |
| `PEOPLE_CACHE_ENABLE` · UI | `true` | Cache downloaded cast/crew headshots. When off, photo URLs are re-resolved on every scene refresh. |
| `PEOPLE_CACHE_DIR` · UI | `./local/images/people` | On-disk cache for actor / director / producer headshots. |
| `PEOPLE_CACHE_REPLACE_ENABLE` · UI | `false` | Ignore existing cached photos and re-fetch every time. |
| `PEOPLE_CACHE_FACE_ENABLE` · UI | `false` | Face-detect and crop cached headshots to head + shoulders for Plex's circular card. Requires `opencv-python-headless` (`pip install "opencv-python-headless"`); no-ops if absent. Placeholder images are never cropped. Review/undo at `/people-cache`. |
| `PEOPLE_SOURCE_ORDER` · UI | `Local Storage,AdultDVDEmpire,Freeones,IAFD,Indexxx,Boobpedia,Babes and Stars,Babepedia` | Priority order of headshot lookup sources (comma-separated). IAFD needs a bypass backend (Impersonate). |
| `PEOPLE_IMAGE_URL` · UI | `baseurl` | Which base URL **actor/director/producer** image links use. Plex re-requests these periodically and doesn't keep them, so behind a Cloudflare tunnel the FQDN eventually dies and the images break — a stable local address is more durable. See the option table below. Poster/art images always use `PHOENIX_BASE_URL`. |
| `ADULT_EMPIRE_LOGIN_TOKEN` · UI | _(unset)_ | Session token for the AdultDVDEmpire headshot source. |

`PEOPLE_IMAGE_URL` options:

| Value | Resolves to | Use when |
| --- | --- | --- |
| `baseurl` | `PHOENIX_BASE_URL` (tunnel/FQDN) | you want actor images on the public URL too |
| `localhost` | `http://localhost:<PORT>` | Plex runs on the **same machine** |
| `localipv4` | `http://<LAN-IPv4>:<PORT>` | Plex is **elsewhere on the LAN** |
| `localipv6` | `http://[<LAN-IPv6>]:<PORT>` | LAN, over IPv6 |

The LAN address is detected automatically. Changing this value requires a metadata
refresh in Plex to re-emit the image URLs.

### Gender handling

| Variable | Default | Description |
| --- | --- | --- |
| `GENDER_DETECT_ENABLE` · UI | `true` | Query IAFD for each uncached actor and bake the gender into the cached filename. |
| `GENDER_SKIP_MALE_ENABLE` · UI | `false` | Hide male actors from the served Plex cast list. Applied at **serve time**, so it also re-filters already-cached scenes; actors stay in the snapshot on disk and reappear if you turn it off. |
| `GENERIC_IMAGE_ENABLE` · UI | `true` | Use a generic silhouette when an actor has no resolvable photo. |
| `GENERIC_FEMALE_URL` · UI | _(built-in)_ | Override the built-in female placeholder image. |
| `GENERIC_MALE_URL` · UI | _(built-in)_ | Override the built-in male placeholder image. |

### Web search

| Variable | Default | Description |
| --- | --- | --- |
| `GOOGLE_SEARCH_API_KEY` · UI | _(unset)_ | Google Custom Search API key. With the CX set, Google CSE runs before the DuckDuckGo fallback. |
| `GOOGLE_SEARCH_CX` · UI | _(unset)_ | Programmable Search Engine ID (CX) paired with the API key. |

### HTTP bypass

| Variable | Default | Description |
| --- | --- | --- |
| `BYPASS_ORDER` · UI | `Impersonate,FlareSolverr,Playwright,ReqBin` | Order of HTTP-bypass strategies to try for anti-scrape sites. |
| `BYPASS_AUTO_RETRY` · UI | `false` | Re-route every failed scraper request (4xx/5xx) through the bypass chain. |
| `FLARESOLVERR_URL` · UI | _(unset)_ | Self-hosted FlareSolverr endpoint used to clear Cloudflare challenges. |
| `REQBIN_ENABLE` · UI | `false` | Use the third-party ReqBin service as a bypass fallback. |
| `REQBIN_API_KEY` · UI | _(unset)_ | API key for the ReqBin fallback. |

### Data18 enrichment

| Variable | Default | Description |
| --- | --- | --- |
| `DATA18_ENABLE` · UI | `false` | Master on/off for data18.com image enrichment (per-site opt-in still required). |
| `DATA18_ACCURACY` · UI | `100` | Minimum match accuracy (0–100). Lower = more matches but more false positives. |
| `DATA18_EXTRA` · UI | `false` | Include large/low-quality photoset (1001) and 1901 galleries. |

### MetadataAPI

| Variable | Default | Description |
| --- | --- | --- |
| `METADATAAPI_TOKEN` · UI | _(unset)_ | Bearer token for api.theporndb.net. Optional — without it the API serves a reduced response. |

### Title processing & misc

| Variable | Default | Description |
| --- | --- | --- |
| `STRIP_ENABLE` · UI | `false` | Enable the two strip-symbol rules below, which cut a junk prefix/suffix off the parsed title before searching. |
| `STRIP_SYMBOL` · UI | _(unset)_ | When strip is on and this symbol appears in the title, keep only the text **before** its first occurrence. |
| `STRIP_SYMBOL_REVERSE` · UI | _(unset)_ | When strip is on and this symbol appears in the title, keep only the text **after** its last occurrence. |
| `SEARCH_TITLE_TRASH` · UI | _(built-in list)_ | Whole-word release/scene-group tokens stripped from the parsed title before searching (e.g. `RARBG`, `1080p`, `WEB`). |
| `PHOENIX_EXTRA_COLLECTIONS` · UI | `false` | Restore the optional extra-collections pass (studio / serie / movie titles) in GammaEntOther. |
| `DISABLE_AUTO_MATCH` · UI | `false` | Suppress every match request Plex did **not** flag as user-initiated (`manual=1`). |

### Network &nbsp;·&nbsp; boot

| Variable | Default | Description |
| --- | --- | --- |
| `HTTPS_PROXY` | _(unset)_ | Upstream proxy for outbound scraper/image requests. `HTTP_PROXY` and the lowercase forms are also honored. |
| `NO_PROXY` | _(unset)_ | Comma-separated hosts that bypass the proxy. |

### Advanced &nbsp;·&nbsp; boot

| Variable | Default | Description |
| --- | --- | --- |
| `ENV_OVERRIDES_PATH` | `./env.overrides.json` | Where the Config UI persists runtime overrides. |
