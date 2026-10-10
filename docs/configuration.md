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

Open **`GET /config`** in a browser and sign in. Edit a value and **Save**, and it is
written to `env.overrides.json` and applied live — no restart for most options.

The Config UI covers the per-feature options (caching, gender handling, sources,
bypass, …). It does **not** edit the server, auth, and network variables — `PORT`,
`PHOENIX_BASE_URL`, `NODE_ENV`, `LOG_DIR`, `HTTPS_PROXY`, `NO_PROXY`,
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

On/off variables accept `true`/`1`/`yes`/`on` to switch on and `false`/`0`/`no`/`off` to
switch off, in any case. A blank value falls back to the default.

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
| `NODE_ENV` | `production` | `production` enables prod behavior (host redaction defaults on, no auto-reload). Set `development` (or `dev`/`test`/`local`) for local work. |
| `DEV_UI_ENABLE` | `false` | Serves the developer UI at `/dev`. Off everywhere until you turn it on, in any `NODE_ENV`; the routes answer 404 while off and stay admin-only when on. |

### User Accounts And API Keys

Authentication lives in the database, not the environment — there are no auth variables
to set. On first run every admin page redirects to **`/setup`**, which creates the first
account (an admin) and signs it in; afterwards `/setup` returns 404 and **`/login`** is
the only way in, including from loopback.

- **Sessions** last 30 days of inactivity and ride in an `HttpOnly`, `SameSite=Lax`
  cookie that is marked `Secure` whenever the request arrives over https (including
  behind a tunnel or reverse proxy that sets `X-Forwarded-Proto`).
- **API keys** replace the old admin token for scripts. Generate one on **`/account`**,
  where it stays visible (stored encrypted with the server secret, like Plex tokens) with
  a copy button, and send it as `Authorization: Bearer pa_…` or `x-api-key: pa_…`.
  Regenerating immediately invalidates the previous key — and does not reset the daily
  request limit, which is counted against the user, not the key.
- **Admins** manage other accounts from the **Users** tab of `/config`: add or delete
  users, reset passwords, and grant or revoke admin. The last admin cannot be deleted
  or demoted.
- **Non-admins** see only their own surface on `/config`: the **Plex** tab (their
  connections), the **Enrichment** tab (their MetadataAPI token), and the **Theme**
  tab. Every environment tab (Matching, Scraping, People, Images, System) plus
  **Logs** and the **Clients** hit log is admin-only, enforced server-side — the
  save/reset/reveal/restart/logs endpoints return 403 for non-admins.
- **The other admin UIs are read-only for non-admins.** `/metadata`, `/people`,
  `/logos` and `/queue` open and browse normally — filtering and Export Mappings
  included — but every write control is gone:
  - no purge (single or bulk), prune, rescan, flush, or queue pause/resume;
  - no image fetching on People;
  - the card action reads **View** instead of Edit, and the edit screens show locked
    fields with no add/remove chips, image rotate/remove, Save, or Refresh All.

  Each write endpoint behind those buttons also returns 403, so the read-only view
  cannot be bypassed with hand-crafted requests.
- **Metadata locks** — every field on `/metadata/edit` and every image carries a lock
  toggle (plus a whole-image-set lock). Locked pieces keep their stored values through
  Refresh Metadata and re-scrapes; editing a field and saving locks it automatically,
  Plex-style. Removed images only stay gone while the image-set lock is on.
- **`/searches`** (admin only, linked in the nav for admins) browses the stored-search
  store: every cached search with all its results, filterable by site, with per-search
  purge and re-search, per-site and full purges, and an expired-row sweep. Non-admins
  get 403 and never see the nav link.
- **Clients** (admin tab) records every provider-mount request that carried an
  `X-Plex-Client-Identifier` — one card per client with its X-Plex headers, hit
  count, and last path — the quickest way to grab an identifier for a connection's
  allowlist. Stored in SQLite, so counts survive a restart; only the 200 most recently
  seen clients are kept.
- **Lost every password?** Run `python scripts/reset_password.py <username>` on the
  server (add `--create-admin` when no usable admin remains).

Every password — at setup, on `/account`, from the Users tab, and in the recovery
script — must be at least 8 characters and contain an uppercase letter, a number, and a
special character. The password fields also show an advisory zxcvbn strength meter
(Very Weak → Very Strong); it never blocks — the composition rule is the only hard floor.

Passwords are hashed with argon2id; session tokens are stored as SHA-256 digests, and API
keys as a digest for lookup plus an encrypted copy for display on `/account`. A `secret.key` file is generated beside the database on first start and is used
to sign image URLs and encrypt stored Plex tokens — **back it up with the database**, and
note that losing it means re-fetching Plex tokens and refreshing Plex metadata once.

### Provider Access

The provider mount (`/phoenixadult/movies`) answers only requests whose `User-Agent`
contains `PlexMediaServer`; anything else — browsers, scanners, curl — gets a 404, so the
mount does not advertise its own existence. A user agent is trivially spoofed, so treat
this as noise reduction, not authentication; the settings below are the real gate.

| Variable | Default | Description |
| --- | --- | --- |
| `TOKEN_BASED_AUTH` | `false` | Require a user API key in the provider URL path: register it in Plex as `http://host:3000/api/hook/pa_…/phoenixadult/movies` (the **Account** page shows the exact URL with a copy button). The key rides in the path because Plex preserves the path prefix on every request it generates but drops query strings. Many keys serve the one route; revoking a key is regenerating it on **Account**. Enforced strictly — loopback and signed-in sessions do **not** bypass it, and the bare mount answers 404. Hook URLs serve only the provider mount, invalid-token attempts are rate-limited per source IP, and the token segment is always masked in logs. |
| `CLIENT_TOKEN_REQUIRED` | `false` | Require match and metadata requests to carry an `X-Plex-Client-Identifier` registered under a Plex connection. The provider URL itself (the capability document Plex reads when adding the provider) always answers, so the provider can be added at any time — Plex sends no identifier on that request. |
| `API_REQUESTS_PER_DAY` | `0` | Daily request cap applied separately to each Plex client and each API key; `0` is unlimited. Over the cap the provider answers `429` with `Retry-After` set to the seconds remaining until local midnight. Counts live in SQLite and survive restarts. |

Failures are logged at `warn` with the reason and the caller. Set `LOG_LEVEL=verbose` to
dump every provider request's headers — including refused ones, which is usually what you
need when Plex will not connect.

#### Log Redaction

**In production both redactions are always on and cannot be turned off** — the two
variables below disappear from the Config UI there and their values are ignored. In
development they default **off** so logs show real addresses and credentials while you
debug, and nothing is masked unless you opt in:

| Variable | Default (dev) | Description |
| --- | --- | --- |
| `LOG_REDACT_HOSTS` | off | Masks every IP address and the server's own host/FQDN (from `PHOENIX_BASE_URL`) in logs. |
| `LOG_REDACT_TOKEN` | off | Masks credentials in logs: the hook-path key segment (`/api/hook/…/`), secret query values (`?token=…`, `?password=…`), and credential-bearing headers (`Authorization`, `Cookie`, `X-Plex-Token`, …) in verbose request dumps. |

### Interface

| Variable | Default | Description |
| --- | --- | --- |
| `UI_LANGUAGE` | `en` | Language of the web pages. `en` (English) is the only one available today; an unknown code falls back to English. Applies on the next page load. |

### Logging

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `info` | Verbosity, least to most: `error`, `warn`, `info`, `debug`, `http`, `verbose`. Each level includes everything before it; HTTP access lines only appear at `http` or `verbose` — **except** requests made while scraping, which log at `info` (see below). Restart to apply. |
| `LOG_DIR` | `./logs` | Directory for the rolling `agent.log` file. Set in `.env` only; restart to apply. |
| `HTTP_BODY_DUMP` | `false` | Write every scraped page body to `<LOG_DIR>/dumps/` **regardless of log level**. The startup banner reports whether dumping is armed and where the files go. |
| `LOG_BODY_MAX_CHARS` | `0` | Characters of each scraped response body written to the log at `verbose`. `0` keeps the whole body. Ignored below `verbose`. |

#### Verbose Body Dumps

At `LOG_LEVEL=verbose` — the last step, **not** `http`, which shows access lines only — the body of every textual response the provider fetches is written to the log: the page source a scraper actually parsed, tagged `[scrape-body]` with the method, final URL, status and content type.

- JSON bodies are pretty-printed; binary responses (images above all) are skipped by content type.
- Pages recovered through the bypass chain are dumped too.
- This is the fastest way to see *why* a selector found nothing: a challenge page, an empty result list and a changed layout look identical in the scraper's own log lines, and completely different here.
- Bodies are large. `LOG_BODY_MAX_CHARS` caps them, and `agent.log` rotates at 10 MB with 5 backups.
- Every dumped body is also **written to a file** under `<LOG_DIR>/dumps/` — `0007-GET-site.com-path-a1b2c3.html`, numbered in request order — and an `info` line names the path, so the raw page opens in an editor. The newest 300 files are kept.
- The **Dev UI** test bench shows the same bodies in its Captures panel without needing `verbose`: it opens a capture sink for the run, which switches tracing on for that request alone. Log line and capture entry come from one call, so the two cannot drift.

#### Scrape Request Lines

Every request a scraper makes while searching or updating is logged at `info` with its method and full URL, tagged with the phase and site — `[search TeamSkeet] Requesting GET "…"`, `[update TeamSkeet] Requesting GET "…"`. That covers supporting fetches too: model pages, photo galleries, Data18 enrichment. Requests outside a scrape (image downloads, Plex calls, the UIs) stay at `http`, so you don't need a higher level to see how a match was reached.

#### Logs Tab

The **Logs** tab in the Config UI tails what this process has logged, polling every three seconds while the tab is open.

- It reads an in-memory ring buffer (1000 lines) fed by the same formatter and redaction filter as `agent.log`, so it never shows anything the file would hide. A restart starts it empty.
- Lines never wrap; the view scrolls both ways and follows the newest line until you scroll up.
- Toolbar: a **line limit** (50/100/200/500/1000, default 200); a **filter** that hides non-matching lines while collection continues behind it; **Pause** (new lines are dropped, not queued); **Clear** (empties the view only; the server buffer is untouched); **Copy** (the visible, filtered lines).

### Images

| Variable | Default | Description |
| --- | --- | --- |
| `IMAGE_DIR` | `./local/images` | Directory served back to Plex for local image files: headshots in `IMAGE_DIR/people`, clearLogos in `IMAGE_DIR/logos` (per-studio subfolders, managed at `/logos`). |
| `IMAGE_MAX_BYTES` | `20M` | Hard ceiling on a single upstream image fetch — proxied, snapshot and people-cache downloads alike; the download stops as soon as it passes the ceiling. Accepts a byte count or a size like `20M`, `2000K`, `100B`. |
| `IMAGE_PROXY_PIN` | `true` | SSRF hardening for `/images/proxy`: each hop is resolved once, validated public, and fetched by pinned IP (hostname kept in Host and TLS SNI). Turn off if a CDN rejects pinned fetches. |
| `IMAGE_GUARD_ENABLE` | `true` | Serve images only to Plex, signed URLs and signed-in users (see [Image Guard](#image-guard)). A browser typing an image URL directly gets a 403. |
| `IMAGE_BASE_URL` | `baseurl` | Base URL Plex uses to fetch our locally served images: cast photos and the clearLogos pushed to collections. **Must be publicly reachable** for Plex Media Server 1.43.5+ (see [below](#image_base_url)). Poster and art images always use `PHOENIX_BASE_URL`. |

#### Image Guard

With `IMAGE_GUARD_ENABLE` on (the default), logos, snapshot images and people images are served only to:

- **signed URLs** — every emitted image URL carries a permanent `sig=` HMAC keyed by the server secret, with no expiry, so Plex-held URLs never break;
- **Plex** — a `PlexMediaServer` User-Agent;
- **image fetchers** — `Accept: image/*` on a non-navigation request (e.g. Plex's cloud image proxy);
- **loopback**, **signed-in or API-key requests**, and **the admin UIs** (same-origin subresource checks).

Notes:

- The User-Agent and Accept checks are best-effort, not authentication; signatures require the exact URL the provider emitted.
- Snapshots store unsigned paths and are signed at serve time, so a Plex metadata refresh picks up signed URLs.
- With the guard off, requests that *would* have been refused are logged, so you can confirm nothing legitimate is caught before turning it back on.

#### `IMAGE_BASE_URL`

Plex fetches cast photos and collection logos from this address on demand and doesn't keep them. From **Plex Media Server 1.43.5**, Plex refuses provider images on private addresses — the log shows `Refusing to connect to <ip>: not a permitted destination for a caller-supplied URL` and cast photos appear as grey circles. Plex staff have confirmed provider images must be publicly accessible URLs.

So the address must be **public** and **stable** (Plex stores it): a named Cloudflare Tunnel or another fixed hostname. See [Hosting](./hosting.md#plex-needs-public-image-urls) for an images-only setup.

| Value | Resolves To | Notes |
| --- | --- | --- |
| `baseurl` | `PHOENIX_BASE_URL` | Works when that is a stable public hostname |
| an explicit address | e.g. `https://img.example.com` (scheme defaults to http, `PORT` appended when missing) | A dedicated public hostname for images |
| `localhost` | `http://localhost:<PORT>` | Private: refused by Plex 1.43.5+ |
| `localipv4` | `http://<LAN-IPv4>:<PORT>` | Private: refused by Plex 1.43.5+ |
| `localipv6` | `http://[<IPv6>]:<PORT>` | Refused when the address is private; untested with a global IPv6 address |

The LAN address is detected automatically. Changing this value requires a metadata refresh in Plex to re-emit the image URLs.

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
| `METADATA_CACHE_DIR` | `./local/cache` | On-disk location for the snapshot folders, one per scene at `scenes/<xx>/<hash>/` (images plus a self-contained `snapshot.json`). |
| `STATE_DB_PATH` | `./local/phoenixadult.db` | SQLite database (WAL) holding queue replays, the search store, and the scene snapshot store (see [database.md](database.md)). Scene text is primary data — do not delete this file. **Keep it on storage only this process touches**: a network mount, or an SMB/NFS-exported path another machine can open, breaks WAL locking and corrupts the file. Restart to apply. |
| `DB_BACKUP_INTERVAL_HOURS` | `24` | How often the app writes a `VACUUM INTO` snapshot of the state database (no cron — the app runs its own timer). `0` disables. On startup, if the live database fails an integrity check it is quarantined (`*.corrupt-<timestamp>`) and the newest good snapshot is restored automatically. |
| `DB_BACKUP_KEEP` | `7` | Number of snapshots to retain; older ones are pruned after each backup. |
| `DB_BACKUP_DIR` | _(next to the DB)_ | Where snapshots are written; blank uses a `backups/` folder beside `STATE_DB_PATH`. A different local disk is safest so one failure doesn't take the database and its backups together. |

### People Cache & Sources

| Variable | Default | Description |
| --- | --- | --- |
| `PEOPLE_CACHE_ENABLE` | `true` | Cache downloaded cast/crew headshots. When off, photo URLs are re-resolved on every scene refresh. |
| `PEOPLE_CACHE_REPLACE_ENABLE` | `false` | Ignore existing cached photos and re-fetch every time. |
| `PEOPLE_CACHE_FACE_ENABLE` | `false` | Face-detect and crop cached headshots to head + shoulders for Plex's circular card. Requires `opencv-python-headless` (`pip install "opencv-python-headless"`); no-ops if absent. Placeholder images are never cropped. Review/undo at `/people`. |
| `PEOPLE_SOURCE_ORDER` | built-in order | Priority order of headshot sources, comma-separated (see [Source Order](#source-order)). |
| `ADULT_EMPIRE_LOGIN_TOKEN` | _(unset)_ | Session token for the AdultDVDEmpire headshot source. |

#### Source Order

The default order is Local Storage, Scene, IAFD, AdultDVDEmpire, Indexxx, Boobpedia, Babes and Stars, Babepedia.

- **`Scene`** is the actor image from the scene page itself. Remove it to use only the external providers, or move it lower to prefer a provider over it.
- **IAFD** needs a bypass backend (Impersonate).
- **JAVDatabase** is selectable but off by default, being JAV-only.
- **Freeones and JAVBus** are retired (they sit in `phoenixadult/graveyard/`); naming either is ignored.
- Setting the variable **replaces** the default outright: sources you leave out are never consulted automatically, but stay available per person from the editor's Fetch From.

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

The engine chain is Google CSE (when configured) → DuckDuckGo → ddgs metasearch.
The final entry uses the [ddgs](https://github.com/deedy5/ddgs) library's auto
backend — several engines behind browser-impersonated TLS — so a DuckDuckGo
markup change or block no longer ends the chain.

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

The ThePornDB bearer token is stored **per user account** (encrypted, never shown
after save), not as an environment variable — set it on the **Enrichment** tab of
`/config`, which every signed-in user can reach. Scrapes serving a Plex server use
the token of the connection owner whose allowlist matched the calling server;
background/queued scrapes fall back to the first configured token. A legacy
`METADATAAPI_TOKEN` environment value migrates into the first admin account on
startup and is cleared from the overrides.

### Plex Connections, Cache Review and Editing

Plex servers are paired per user from the **Plex tab** of `/config` — nothing is configured
through environment variables. The UI how-tos live in the guides:

- [Plex Connections](./guides/plex-connections.md) — pairing servers, reconciling stale tags,
  importing a library into the cache.
- [Metadata Cache](./guides/metadata-cache.md) — reviewing and editing cached scenes.
- [People Cache](./guides/people-cache.md) — reviewing, editing and re-fetching headshots.

### Matching & Title Parsing

| Variable | Default | Description |
| --- | --- | --- |
| `STRIP_ENABLE` | `false` | Enable the two strip-symbol rules below, which cut a junk prefix/suffix off the parsed title before searching. |
| `STRIP_SYMBOL` | _(unset)_ | When strip is on and this symbol appears in the title, keep only the text before its first occurrence. |
| `STRIP_SYMBOL_REVERSE` | _(unset)_ | When strip is on and this symbol appears in the title, keep only the text after its last occurrence. |
| `SEARCH_TITLE_TRASH` | built-in list | Whole-word release/scene-group tokens stripped from the parsed title before searching (e.g. `RARBG`, `1080p`, `WEB`). Entries are regular expressions; the Config UI refuses an invalid one, and an invalid entry set in `.env` is skipped with a warning. |
| `SEARCH_STRIP_ACTORS` | _(unset)_ | Sites whose filenames lead with actor names: the names are dropped when building the site search, and title scoring uses the best of the stripped and unstripped title. Entries match a site, a studio, or a whole network (e.g. `Nubiles`). Porn Pros does not need listing — it keys on the title alone and tries the stripped form itself. |
| `DISABLE_AUTO_MATCH` | `false` | Suppress every match request Plex did not flag as user-initiated (`manual=1`). |

### Scraping & Pacing

| Variable | Default | Description |
| --- | --- | --- |
| `PHOENIX_EXTRA_COLLECTIONS` | `false` | Restore the optional extra-collections pass (studio / serie / movie titles) in GammaEntOther. |
| `SCENE_GAP` | `10` | Base seconds between units of work on rate-limited scrapers (Nubiles, Naughty America) — searches and scene scrapes share one track. A 10–45s random jitter is always added on top, and at most 8 scenes run per 10 minutes regardless. Work that would block a Plex request runs in the background instead (watch it at `/queue`); finished background searches persist to the search store so a later scan consumes them. |
| `REFRESH_FORCE_COUNT` | `3` | Plex refreshes of one scene within 60 seconds that force a fresh scrape instead of the cached snapshot. Set `1` to refetch on every refresh. **Refresh Metadata** on the snapshot editor forces the same re-scrape in one click, without the repeated Plex refreshes; **Refresh All / Refresh Filtered** on `/metadata` queues it for every snapshot matching the active filters. |
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
