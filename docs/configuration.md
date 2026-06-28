# Configuration

The provider is configured with environment variables. There are **two ways** to set
them, and it's worth understanding how they interact before changing anything.

## Two Ways to Configure

### 1. Environment / `.env` (Boot-Time)

Set variables in the process environment. The simplest way is a `.env` file in the
working directory (loaded automatically at startup); you can also export real
environment variables or pass them to a container (`docker run -e PORT=3000 …`).

```bash
cp .env.example .env      # then edit
```

Read **once at startup**, so changes take effect on the next restart. This method works
for **every** variable below — including the server, auth, and network ones that are
not exposed in the Config UI.

### 2. Config UI (Runtime)

Open **`GET /config`** in a browser (allowed from loopback, or with the `ADMIN_TOKEN`
header/query elsewhere). Edit a value and **Save**, and it is written to
`env.overrides.json` and applied live — no restart for most options.

The Config UI covers the per-feature options (caching, gender handling, sources,
bypass, …). It does **not** edit the server, auth, and network variables — `PORT`,
`PHOENIX_BASE_URL`, `NODE_ENV`, `ADMIN_TOKEN`, `LOG_DIR`, `HTTPS_PROXY`, `NO_PROXY`,
and `ENV_OVERRIDES_PATH` — which come from the environment at startup. **Reset** on a
row clears its override and reverts to the `.env`/built-in value.

### How They Interact

`env.overrides.json` is layered **on top of** the environment at startup, so a saved
override **shadows `.env`**. If a `.env` change doesn't seem to take effect, it's almost
always because the Config UI previously saved an override for that key — clear it with
**Reset** in the UI (or delete the entry from `env.overrides.json`).

`env.overrides.json` lives in the working directory (or `ENV_OVERRIDES_PATH`) and is
git-ignored — it holds only the keys you changed in the UI. Only UI-editable keys are
honored from that file; unknown keys are ignored.

### What Needs a Restart

Most options apply immediately. These are read once at startup — change them and
restart: `PORT`, `PHOENIX_BASE_URL`, `NODE_ENV`, `LOG_LEVEL`, `LOG_DIR`.

---

## Variable Reference

Defaults are the value used when the variable is unset.

### Server

_Read from the environment at startup; not editable in the Config UI._

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` | `3000` | TCP port the HTTP server binds to. |
| `PHOENIX_BASE_URL` | `http://localhost:3000` | Public base URL the provider advertises to Plex. Behind a reverse proxy or Cloudflare tunnel, set this to the externally reachable URL — it's the base for served image/poster links (see `PEOPLE_IMAGE_URL` for actor images specifically). |
| `NODE_ENV` | `production` | `production` enables prod behavior (host redaction defaults on, no auto-reload, `/dev` disabled). Set `development` (or `dev`/`test`/`local`) for local work and the `/dev` UI. |

### Admin Auth

_Read from the environment at startup; not editable in the Config UI._

| Variable | Default | Description |
| --- | --- | --- |
| `ADMIN_TOKEN` | _(unset)_ | Guards the admin surfaces (`/config`, `/dev`, `/people-cache`, `/metadata-cache`). When unset, those are reachable from loopback only. Set a token to reach them from another host (sent as the `x-admin-token` header or a `token` query param). |

### Logging

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `info` | Verbosity: `error`, `warn`, `info`, `http`, `verbose`, `debug`. Restart to apply. |
| `LOG_DIR` | `./logs` | Directory for the rolling `agent.log` file. Set in `.env` only; restart to apply. |
| `LOG_REDACT_HOSTS` | on in `production`, else off | Additionally masks the server's own host/FQDN (from `PHOENIX_BASE_URL`) in logs. IP addresses are always redacted, in every environment — this flag only affects the hostname. |
| `LOG_REDACT_TOKEN` | `false` | Masks secret query values (`?token=…`, `?apikey=…`, `?password=…`) in logs. Off by default so you can see the admin token in URLs while testing. |

### Images

| Variable | Default | Description |
| --- | --- | --- |
| `IMAGE_DIR` | `./local/images` | Directory of local image files served back to Plex. |
| `IMAGE_MAX_BYTES` | `20M` | Hard ceiling on a single upstream image fetch; larger images are rejected. Accepts a byte count or a size like `20M`, `2000K`, `100B`. |

### Manual NFO

| Variable | Default | Description |
| --- | --- | --- |
| `MANUAL_NFO_PATH` | `./local/manual` | Root folder served by the "Manual NFO" scraper. |
| `MANUAL_NFO_TOKEN` | `manual` | Leading filename token that pins a match request to the Manual NFO scraper. |

See the [manual searching](./manualsearch.md) doc for how manual matching works.

### Metadata Cache

| Variable | Default | Description |
| --- | --- | --- |
| `METADATA_CACHE_ENABLE` | `false` | Snapshot each scraped scene's metadata + images under the cache dir and serve cache-first afterward — offline-safe protection against a source going down or changing its anti-scrape. Manage/purge at `/metadata-cache`. |
| `METADATA_CACHE_DIR` | `./local/cache` | On-disk location for those snapshots (text + images). |

### People Cache & Sources

| Variable | Default | Description |
| --- | --- | --- |
| `PEOPLE_CACHE_ENABLE` | `true` | Cache downloaded cast/crew headshots. When off, photo URLs are re-resolved on every scene refresh. |
| `PEOPLE_CACHE_DIR` | `./local/images/people` | On-disk cache for actor / director / producer headshots. |
| `PEOPLE_CACHE_REPLACE_ENABLE` | `false` | Ignore existing cached photos and re-fetch every time. |
| `PEOPLE_CACHE_FACE_ENABLE` | `false` | Face-detect and crop cached headshots to head + shoulders for Plex's circular card. Requires `opencv-python-headless` (`pip install "opencv-python-headless"`); no-ops if absent. Placeholder images are never cropped. Review/undo at `/people-cache`. |
| `PEOPLE_SOURCE_ORDER` | built-in order | Priority order of headshot lookup sources, comma-separated. IAFD needs a bypass backend (Impersonate). Default order: Local Storage, AdultDVDEmpire, Freeones, IAFD, Indexxx, Boobpedia, Babes and Stars, Babepedia. |
| `PEOPLE_IMAGE_URL` | `baseurl` | Which base URL actor/director/producer image links use. Plex re-requests these periodically and doesn't keep them, so behind a Cloudflare tunnel the FQDN eventually dies and the images break — a stable local address is more durable. See the option table below. Poster/art images always use `PHOENIX_BASE_URL`. |
| `ADULT_EMPIRE_LOGIN_TOKEN` | _(unset)_ | Session token for the AdultDVDEmpire headshot source. |

`PEOPLE_IMAGE_URL` options:

| Value | Resolves To | Use When |
| --- | --- | --- |
| `baseurl` | `PHOENIX_BASE_URL` (tunnel/FQDN) | you want actor images on the public URL too |
| `localhost` | `http://localhost:<PORT>` | Plex runs on the same machine |
| `localipv4` | `http://<LAN-IPv4>:<PORT>` | Plex is elsewhere on the LAN |
| `localipv6` | `http://[<LAN-IPv6>]:<PORT>` | LAN, over IPv6 |

The LAN address is detected automatically. Changing this value requires a metadata
refresh in Plex to re-emit the image URLs.

### Gender Handling

| Variable | Default | Description |
| --- | --- | --- |
| `GENDER_DETECT_ENABLE` | `true` | Query IAFD for each uncached actor and bake the gender into the cached filename. |
| `GENDER_SKIP_MALE_ENABLE` | `false` | Hide male actors from the served Plex cast list. Applied at serve time, so it also re-filters already-cached scenes; actors stay in the snapshot on disk and reappear if you turn it off. |
| `GENERIC_IMAGE_ENABLE` | `true` | Use a generic silhouette when an actor has no resolvable photo. |
| `GENERIC_FEMALE_URL` | _(built-in)_ | Override the built-in female placeholder image. |
| `GENERIC_MALE_URL` | _(built-in)_ | Override the built-in male placeholder image. |

### Web Search

| Variable | Default | Description |
| --- | --- | --- |
| `GOOGLE_SEARCH_API_KEY` | _(unset)_ | Google Custom Search API key. With the CX set, Google CSE runs before the DuckDuckGo fallback. |
| `GOOGLE_SEARCH_CX` | _(unset)_ | Programmable Search Engine ID (CX) paired with the API key. |

### HTTP Bypass

| Variable | Default | Description |
| --- | --- | --- |
| `BYPASS_ORDER` | Impersonate, FlareSolverr, Playwright, ReqBin | Order of HTTP-bypass strategies to try for anti-scrape sites. |
| `BYPASS_AUTO_RETRY` | `false` | Re-route every failed scraper request (4xx/5xx) through the bypass chain. |
| `FLARESOLVERR_URL` | _(unset)_ | Self-hosted FlareSolverr endpoint used to clear Cloudflare challenges. |
| `REQBIN_ENABLE` | `false` | Use the third-party ReqBin service as a bypass fallback. |
| `REQBIN_API_KEY` | _(unset)_ | API key for the ReqBin fallback. |

### Data18 Enrichment

| Variable | Default | Description |
| --- | --- | --- |
| `DATA18_ENABLE` | `false` | Master on/off for data18.com image enrichment (per-site opt-in still required). |
| `DATA18_ACCURACY` | `100` | Minimum match accuracy (0–100). Lower = more matches but more false positives. |
| `DATA18_EXTRA` | `false` | Include large/low-quality photoset (1001) and 1901 galleries. |

### MetadataAPI

| Variable | Default | Description |
| --- | --- | --- |
| `METADATAAPI_TOKEN` | _(unset)_ | Bearer token for api.theporndb.net. Optional — without it the API serves a reduced response. |

### Title Processing & Misc

| Variable | Default | Description |
| --- | --- | --- |
| `STRIP_ENABLE` | `false` | Enable the two strip-symbol rules below, which cut a junk prefix/suffix off the parsed title before searching. |
| `STRIP_SYMBOL` | _(unset)_ | When strip is on and this symbol appears in the title, keep only the text before its first occurrence. |
| `STRIP_SYMBOL_REVERSE` | _(unset)_ | When strip is on and this symbol appears in the title, keep only the text after its last occurrence. |
| `SEARCH_TITLE_TRASH` | built-in list | Whole-word release/scene-group tokens stripped from the parsed title before searching (e.g. `RARBG`, `1080p`, `WEB`). |
| `PHOENIX_EXTRA_COLLECTIONS` | `false` | Restore the optional extra-collections pass (studio / serie / movie titles) in GammaEntOther. |
| `DISABLE_AUTO_MATCH` | `false` | Suppress every match request Plex did not flag as user-initiated (`manual=1`). |

### Network

_Read from the environment at startup; not editable in the Config UI._

| Variable | Default | Description |
| --- | --- | --- |
| `HTTPS_PROXY` | _(unset)_ | Upstream proxy for outbound scraper/image requests. `HTTP_PROXY` and the lowercase forms are also honored. |
| `NO_PROXY` | _(unset)_ | Comma-separated hosts that bypass the proxy. |

### Advanced

_Read from the environment at startup; not editable in the Config UI._

| Variable | Default | Description |
| --- | --- | --- |
| `ENV_OVERRIDES_PATH` | `./env.overrides.json` | Where the Config UI persists runtime overrides. |
