---
sidebar_label: Plex Connections
description: Pair Plex servers, reconcile stale tags, and import a Plex library into the cache.
---

# Plex Connections

Plex servers are paired per user from the **Plex tab** of `/config` — nothing is
configured through environment variables. Add a connection, then either use **Fetch New
Token** (a plex.tv sign-in whose token is stored server-side, never passing through the
browser) or paste a token; pick the server address from the discovered list, and
**Verify Server** to confirm identity and library access.

Each connection stores its own:

- **Server URL** — a LAN address is fine; the provider dials out to Plex, never the reverse.
- **Token** — encrypted at rest with the server secret and never shown again; the UI only
  reports whether one is saved.
- **Allowed Plex Clients** — `X-Plex-Client-Identifier` values associated with this
  connection. They map an incoming client to its owning user, which is how a request picks
  up that user's MetadataAPI token, and they are the allowlist `CLIENT_TOKEN_REQUIRED`
  checks on match/metadata requests. An identifier already listed under another user's
  connection is refused (409), so one user cannot take over another's Plex client. Find a
  server's identifier in a verbose request dump, the Clients tab, or its `Preferences.xml`
  (`ProcessedMachineIdentifier`).
- **Update channel and release** — `plex` follows the server's own channel preference
  (`ButlerUpdateChannel`), or force `public`/`beta` (beta needs Plex Pass). The release
  dropdown appears whenever a platform lists more than one build; unset picks the release
  carrying the platform's latest version, since Plex lists stale builds (e.g. frozen
  Windows 32-bit) first.
- **Image base URL override** — set this when a particular server must reach the provider
  at a different address than the global `IMAGE_BASE_URL`. It lives on the **Images** tab
  (admin-only) and edits the connection currently selected on the Plex tab.

  Plex Media Server 1.43.5 and later only fetch provider images from **publicly reachable**
  addresses, so the override (like `IMAGE_BASE_URL`) must point at a public hostname — see
  [Hosting](../hosting.md#plex-needs-public-image-urls).

Reconcile, library import, and collection-logo pushes all run against the selected
connection; a second reconcile on the same connection is refused while one is running,
but different connections run in parallel. Upgrading from an older release migrates any
existing `PLEX_*` settings into the first admin's connection automatically and clears
them from `env.overrides.json`.

## Reconciling Stale Tags

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

Requires a signed-in session or an API key, like the cache UIs. It reconciles the five tag
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

## Importing a Library Into the Cache

Scenes whose site has gone offline can no longer be re-scraped, but Plex still holds the metadata it
was given. Import reads one Plex movie library and writes each scene back as a provider snapshot, so
that history survives a cache purge or a rematch.

```
GET  /plex/libraries                          # movie sections, for the picker
POST /plex/import?section=27                  # dry run: reports what it would import
POST /plex/import?section=27&apply=1          # writes the snapshots
POST /plex/import?section=27&apply=1&limit=50
POST /plex/import?section=27&apply=1&overwrite=1   # replace cached scenes too
POST /plex/import-item?ratingKey=51767             # import one scene (dry-run row button)
```

Pick the library and run it from the **Plex tab** of `/config` ("Import a Library Into the Cache").

Notes:

- **Dry run by default.** Nothing is written without `apply=1`.
- **Single scenes import from the dry-run report**: each `importable` (and `skipped`) row carries an
  **Import** button that writes just that scene via `POST …/import-item?ratingKey=…`, honoring the
  Overwrite checkbox — cherry-pick a few scenes without applying the whole library.
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
