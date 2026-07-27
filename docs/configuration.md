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
| `PHOENIX_BASE_URL` | `http://localhost:3000` | Public base URL the provider advertises to Plex. Behind a reverse proxy or Cloudflare tunnel, set this to the externally reachable URL — it's the base for served image/poster links (see `IMAGE_BASE_URL` for local images specifically). |
| `NODE_ENV` | `production` | `production` enables prod behavior (host redaction defaults on, no auto-reload, `/dev` disabled). Set `development` (or `dev`/`test`/`local`) for local work and the `/dev` UI. |

### Admin Auth

_Read from the environment at startup; not editable in the Config UI._

| Variable | Default | Description |
| --- | --- | --- |
| `ADMIN_TOKEN` | _(unset)_ | Guards the admin surfaces (`/config`, `/dev`, `/people`, `/metadata`, `/logos`, `/queue`). When unset, those are reachable from loopback only. Set a token to reach them from another host (sent as the `x-admin-token` header or a `token` query param). |

### Logging

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `info` | Verbosity, least to most: `error`, `warn`, `info`, `debug`, `http`, `verbose`. Each level includes everything before it; HTTP access lines only appear at `http` or `verbose`. Restart to apply. |
| `LOG_DIR` | `./logs` | Directory for the rolling `agent.log` file. Set in `.env` only; restart to apply. |
| `LOG_REDACT_HOSTS` | on in `production`, else off | Masks the server's own host/FQDN (from `PHOENIX_BASE_URL`) **and** private/LAN/loopback IPs in logs — so with it **off** you can see your own LAN address (e.g. `IMAGE_BASE_URL=localipv4`) while debugging. **Public/routable IPs are always redacted**, in every environment, so a real address never leaks. |
| `LOG_REDACT_TOKEN` | on in `production`, else off | Masks secret query values (`?token=…`, `?apikey=…`, `?password=…`) in logs. Off outside production so you can see the admin token in URLs while testing. |

### Images

| Variable | Default | Description |
| --- | --- | --- |
| `IMAGE_DIR` | `./local/images` | Directory of local image files served back to Plex. |
| `IMAGE_MAX_BYTES` | `20M` | Hard ceiling on a single upstream image fetch; larger images are rejected. Accepts a byte count or a size like `20M`, `2000K`, `100B`. |
| `IMAGE_PROXY_PIN` | `true` | SSRF hardening for `/images/proxy`: each hop is resolved once, validated public, and fetched by pinned IP (hostname kept in Host + TLS SNI). Turn off if a CDN rejects pinned fetches. |
| `IMAGE_BASE_URL` | `baseurl` | Base URL Plex uses to fetch our locally-served images — actor/director/producer headshots and the clearLogos pushed to collections. Plex re-requests these and doesn't keep them, so behind a Cloudflare tunnel the FQDN eventually dies and the images break — a stable local address is more durable (see the option table below). Poster/art images always use `PHOENIX_BASE_URL`. |
| `LOGO_CACHE_DIR` | `./local/images/logos` | Folder holding `logo.<site-slug>.<ext>` clearLogo files (per-studio subfolders). Scenes are never given logos; instead, manage the files at `/logos` and push them to Plex **collections** from the Plex tab of `/config` ("Push Logos to Collections"). |

`IMAGE_BASE_URL` options:

| Value | Resolves To | Use When |
| --- | --- | --- |
| `baseurl` | `PHOENIX_BASE_URL` (tunnel/FQDN) | you want local images on the public URL too |
| `localhost` | `http://localhost:<PORT>` | Plex runs on the same machine |
| `localipv4` | `http://<LAN-IPv4>:<PORT>` | Plex is elsewhere on the LAN |
| `localipv6` | `http://[<LAN-IPv6>]:<PORT>` | LAN, over IPv6 |
| an explicit address | `http://192.0.2.10:<PORT>` (scheme defaults to http, `PORT` appended when missing) | auto-detection picks the wrong interface |

The LAN address is detected automatically. Changing this value requires a metadata
refresh in Plex to re-emit the image URLs.

### Manual NFO

| Variable | Default | Description |
| --- | --- | --- |
| `MANUAL_NFO_PATH` | `./local/manual` | Root folder served by the "Manual NFO" scraper. |
| `MANUAL_NFO_TOKEN` | `manual` | Leading filename token that pins a match request to the Manual NFO scraper. |

See the [manual searching](./manualsearch.md) doc for how manual matching works.

### Metadata Cache

| Variable | Default | Description |
| --- | --- | --- |
| `METADATA_CACHE_ENABLE` | `false` | Snapshot each scraped scene's metadata + images and serve cache-first afterward — offline-safe protection against a source going down or changing its anti-scrape. Scene text lives in `STATE_DB_PATH`; manage/purge at `/metadata`. |
| `METADATA_CACHE_DIR` | `./local/cache` | On-disk location for the snapshot image files. |
| `STATE_DB_PATH` | `./local/phoenixadult.db` | SQLite database (WAL) holding queue replays, the search store, and the scene snapshot store (see [database.md](database.md)). Scene text is primary data — do not delete this file. **Keep it on storage only this process touches**: a network mount, or an SMB/NFS-exported path another machine can open, breaks WAL locking and corrupts the file. Restart to apply. |
| `DB_BACKUP_INTERVAL_HOURS` | `24` | How often the app writes a `VACUUM INTO` snapshot of the state database (no cron — the app runs its own timer). `0` disables. On startup, if the live database fails an integrity check it is quarantined (`*.corrupt-<timestamp>`) and the newest good snapshot is restored automatically. |
| `DB_BACKUP_KEEP` | `7` | Number of snapshots to retain; older ones are pruned after each backup. |
| `DB_BACKUP_DIR` | _(next to the DB)_ | Where snapshots are written; blank uses a `backups/` folder beside `STATE_DB_PATH`. A different local disk is safest so one failure doesn't take the database and its backups together. |

### People Cache & Sources

| Variable | Default | Description |
| --- | --- | --- |
| `PEOPLE_CACHE_ENABLE` | `true` | Cache downloaded cast/crew headshots. When off, photo URLs are re-resolved on every scene refresh. |
| `PEOPLE_CACHE_DIR` | `./local/images/people` | On-disk cache for actor / director / producer headshots. |
| `PEOPLE_CACHE_REPLACE_ENABLE` | `false` | Ignore existing cached photos and re-fetch every time. |
| `PEOPLE_CACHE_FACE_ENABLE` | `false` | Face-detect and crop cached headshots to head + shoulders for Plex's circular card. Requires `opencv-python-headless` (`pip install "opencv-python-headless"`); no-ops if absent. Placeholder images are never cropped. Review/undo at `/people`. |
| `PEOPLE_SOURCE_ORDER` | built-in order | Priority order of headshot lookup sources, comma-separated. `Scene` is the actor image from the scene page itself — **remove it to skip the scene image** and use only the external providers, or move it lower to prefer a provider over it. IAFD needs a bypass backend (Impersonate). Default order: Local Storage, Scene, IAFD, AdultDVDEmpire, Freeones, Indexxx, Boobpedia, Babes and Stars, Babepedia, JAVBus, JAVDatabase. Setting this variable replaces the default outright — sources you leave out are never consulted. |
| `ADULT_EMPIRE_LOGIN_TOKEN` | _(unset)_ | Session token for the AdultDVDEmpire headshot source. |

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
| `BYPASS_TIMEOUT_MS` | `10000` | Per-attempt challenge-solve ceiling (ms) for FlareSolverr/Playwright before the chain moves on. |
| `FLARESOLVERR_URL` | _(unset)_ | Self-hosted FlareSolverr endpoint used to clear Cloudflare challenges. |
| `REQBIN_ENABLE` | `false` | Use the third-party ReqBin service as a bypass fallback. |
| `REQBIN_API_KEY` | _(unset)_ | API key for the ReqBin fallback. |
| `PLAYWRIGHT_BROWSER` | `chromium` | Browser the Playwright bypass launches (`chromium`, `firefox`, `webkit`). On FreeBSD/linuxulator, Firefox is far more reliable than Chromium. |

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

### Plex Server

Only needed for reconciliation (below). Both must be set or the feature stays off.

| Variable | Default | Description |
| --- | --- | --- |
| `PLEX_URL` | _(unset)_ | Base URL of the Plex server, e.g. `http://plex.lan:32400`. A LAN address is fine — the provider dials out to Plex, Plex never dials in. |
| `PLEX_TOKEN` | _(unset)_ | `X-Plex-Token` for that server ([how to find yours](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)). Needs library write access, so treat it like a password. Sent as a header, never in a query string. Easiest setup: the **Plex tab** of `/config` — "Fetch New Token" signs in via plex.tv and saves it. |
| `PLEX_CLIENT_ID` | _(unset)_ | Device identifier the fetched token is bound to; saved automatically by "Fetch New Token". Clear it together with the token to unlink this device. |

The **Plex tab** of the `/config` UI drives all of this: fetch a token via plex.tv sign-in,
pick your server from the discovered list (fills `PLEX_URL`), verify the connection
(server identity + authenticated check), see the server version with a local-only
update check (no notifications), and run reconciliation dry-run/apply without curl.

### Editing a Cached Scene or Headshot

Both review UIs have per-row editors. The **Edit** button on `/metadata` (left of Purge) opens
`/metadata/edit?key=<rel path>`; the one on `/people` (between "Use Original" and Purge) opens
`/people/edit?filename=<file>`. Saving writes and returns to the list; Cancel discards.

`/metadata/edit` covers title, sort title, studio, tagline, summary, date, genres, collections,
actors, directors, producers, and the image set (previewed as a grid, each with its kind and a
Remove button; a pasted URL is downloaded on save). Notes:

- **Only the fields you send change.** Everything else in the snapshot — ratingKey, guid, data18
  reference, ratings, duration — is preserved.
- **Removing an image deletes the file**, because the snapshot writer copies only still-referenced
  images into the new generation. Add it back by URL if that was a mistake.
- **A kept actor keeps their headshot**; a newly added one resolves on the next serve.
- **Changing Studio or Tagline moves the snapshot folder** (the layout is derived from them). The
  old directory is removed and the response reports the new key.
- The title cannot be blank, and the snapshot writer still rejects error-looking titles.

`/people/edit` covers the upstream original URL and cropped status, with the performer's name as the
heading plus **Copy** and **Search IAFD** buttons. **Fetch From** runs one chosen photo source
(dropdown; `PEOPLE_SOURCE_ORDER`'s remote sources, minus Local Storage — it returns an
already-cached local file, not an upstream URL) and fills the URL field with what it finds. Nothing
is downloaded until you save, so a wrong hit costs nothing. Saving a change **re-downloads the image and
replaces the cached file**, cropping per the checkbox rather than `PEOPLE_CACHE_FACE_ENABLE` — so it
doubles as a way to crop or un-crop one headshot. The checkbox is disabled when
`opencv-python-headless` is absent.

Saving also **flags every scene crediting that performer to re-push their headshots**. A snapshot
freezes the served image URL, which carries a content-hash cache-buster; replacing the bytes changes
the token, but a cached serve would keep handing Plex the old URL and Plex only re-fetches when a URL
changes. The flag (`scenes.force_refresh`) makes the next serve clear that scene's people-cache
thumbs so the image backfill rebuilds them at the current bytes, then clears itself — one forced
re-push per edit, not a permanent state.

`/people` also has a name search over the current tab and a **No Upstream** filter next to
**Cropped Only**, for headshots with no recorded source URL (they cannot be re-pulled or restored).

#### Reconciling Stale Tags

Plex keeps agent-supplied tags that a provider stops returning: change a scene's collection and
the old one stays on the item. The HTTP provider API has no way to clear it — an agent-framework plugin
could call `metadata.collections.clear()` because it mutated a live Plex object, but a
provider only answers questions. Reconciliation closes that gap from the outside.

```
POST /plex/reconcile              # dry run: reports what it would remove
POST /plex/reconcile?apply=1      # performs the removals
POST /plex/reconcile?apply=1&limit=10
POST /plex/reconcile?fields=Genre,Collection   # only these tag types
POST /plex/reconcile?sites=myfamilypies        # only these scraper clients
GET  /plex/status                 # {"enabled": true|false}
```

Admin-guarded like the cache UIs (`?token=` or `x-admin-token`). It reconciles the five tag
fields — Collection, Genre, Role, Director, Producer — removing only
values Plex holds that the provider's current snapshot does not.

Notes:

- **Dry run by default.** Nothing is written without `apply=1`.
- **Locked fields are skipped**, never overwritten. Plex locks a field once you edit it by hand,
  so a lock means you chose that value. Skipped fields are listed in the report.
- Writes send `<field>.locked=0`. Without it Plex would lock the field it just saw edited,
  freezing out every future provider update.
- Scenes with no cached snapshot are skipped rather than re-scraped, so a run costs no upstream
  traffic.
- Items matched by another agent are ignored — only guids carrying our provider identifier.

#### Importing a Library Into the Cache

Scenes whose site has gone offline can no longer be re-scraped, but Plex still holds the metadata it
was given. Import reads one Plex movie library and writes each scene back as a provider snapshot, so
that history survives a cache purge or a rematch.

```
GET  /plex/libraries                          # movie sections, for the picker
POST /plex/import?section=27                  # dry run: reports what it would import
POST /plex/import?section=27&apply=1          # writes the snapshots
POST /plex/import?section=27&apply=1&limit=50
POST /plex/import?section=27&apply=1&overwrite=1   # replace cached scenes too
```

Pick the library and run it from the **Plex tab** of `/config` ("Import a Library Into the Cache").

Notes:

- **Dry run by default.** Nothing is written without `apply=1`.
- **Scenes already cached are skipped**, so a stored fresh scrape is never overwritten by Plex's
  older copy. Pass `overwrite=1` (or tick "Overwrite Cached Scenes") to replace them instead — use
  it to re-run an import after a fix rather than purging by hand.
- Each scene is keyed back to its `(site, cur_id)` from the guid — ours first, then the retired
  bundle's numeric site id, then the studio name. That last step also recovers scenes **another
  agent matched** (Kodi NFO, `local`, and friends): when the studio names a site we know, the
  scene is keyed on the identifier that agent's own guid carries. Scenes that match none are
  reported as `unresolved` with the reason, and skipped — never guessed at.
- **Every poster and art candidate is imported, not just the two Plex has selected** — the old agent
  handed Plex its whole image set, so that is where the scene stills live. Duplicates listed under
  both buckets are collapsed, and each image is typed by the same aspect-ratio classifier a fresh
  scrape uses. Images are staged on disk and adopted by the snapshot writer, so the Plex token never
  reaches stored metadata.
- **Actor headshots are not imported** — the people pipeline resolves those.
- Retired sites resolve through the **Archive** client (`phoenixadult/clients/aggregators/archive.py`):
  registry entries that exist only so their cached scenes stay servable. It never scrapes, and it
  yields to a real client if that site is ever ported back — its retired scraper waits in
  `phoenixadult/graveyard/`, imported by nothing but still linted and type-checked, so restoring it
  is re-registration rather than archaeology. Its **search reads the metadata cache**
  — cached scenes for that site scored against the query — so an imported scene can still be
  matched in Plex, which is what makes importing foreign-agent content worth doing.
- The per-item list in the report is capped at 500 entries; anything beyond that is counted in
  `itemsTruncated`.

### Matching & Title Parsing

| Variable | Default | Description |
| --- | --- | --- |
| `STRIP_ENABLE` | `false` | Enable the two strip-symbol rules below, which cut a junk prefix/suffix off the parsed title before searching. |
| `STRIP_SYMBOL` | _(unset)_ | When strip is on and this symbol appears in the title, keep only the text before its first occurrence. |
| `STRIP_SYMBOL_REVERSE` | _(unset)_ | When strip is on and this symbol appears in the title, keep only the text after its last occurrence. |
| `SEARCH_TITLE_TRASH` | built-in list | Whole-word release/scene-group tokens stripped from the parsed title before searching (e.g. `RARBG`, `1080p`, `WEB`). |
| `SEARCH_STRIP_ACTORS` | _(unset)_ | Sites whose filenames lead with actor names: the names are dropped when building the site search, and title scoring uses the best of the stripped and unstripped title. Entries match a site, a studio, or a whole network (e.g. `Nubiles`). Porn Pros does not need listing — it keys on the title alone and tries the stripped form itself. |
| `DISABLE_AUTO_MATCH` | `false` | Suppress every match request Plex did not flag as user-initiated (`manual=1`). |

### Scraping & Pacing

| Variable | Default | Description |
| --- | --- | --- |
| `PHOENIX_EXTRA_COLLECTIONS` | `false` | Restore the optional extra-collections pass (studio / serie / movie titles) in GammaEntOther. |
| `SCENE_GAP` | `10` | Base seconds between units of work on rate-limited scrapers (Nubiles, Naughty America) — searches and scene scrapes share one track. A 10–45s random jitter is always added on top, and at most 8 scenes run per 10 minutes regardless. Work that would block a Plex request runs in the background instead (watch it at `/queue`); finished background searches persist to the search store so a later scan consumes them. |
| `REFRESH_FORCE_COUNT` | `3` | Plex refreshes of one scene within 60 seconds that force a fresh scrape instead of the cached snapshot. Set `1` to refetch on every refresh. |
| `SEARCH_STORE_TTL_DAYS` | `0` | How long a cached search result stays valid before a later scan re-searches. `0` = perpetual (never expires), so matches survive indefinitely. Empty banned/no-result searches are never stored regardless. |

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
