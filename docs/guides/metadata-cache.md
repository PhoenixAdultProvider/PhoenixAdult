---
sidebar_label: Metadata Cache
description: Review, filter and edit cached scene snapshots.
---

# Metadata Cache

The metadata cache (`METADATA_CACHE_ENABLE`) keeps a frozen snapshot of every scene served, browsable at `/metadata`.

## Reviewing Cached Scenes

`/metadata` filters run in SQL, so a filtered page's total always matches its contents. The bar
covers search, **Provider**, Studio, Year, Month, Day, Tagline, Collection and Data18, and every
filter narrows Export Mappings and the bulk purge to the same set.

**Provider** is the network a snapshot's site is registered under — the `PROVIDER_NAME` in its
selector file, so Brazzers filters under `Project1Service` and Vixen under `Strike3`. It is resolved
from the registry at query time rather than stored on the row, so regrouping a site moves its
snapshots immediately, with nothing to backfill.

## Editing a Cached Scene

The **Edit** button on `/metadata` (left of Purge) opens `/metadata/edit?key=<rel path>`. Saving writes and returns to the list; Cancel discards.

`/metadata/edit` covers title, sort title, studio, tagline, summary, date, genres, collections,
actors, directors, producers, the Data18 reference, and the image set (previewed as a grid, each
with its kind and a Remove button; a pasted URL is downloaded on save). Notes:

- **Only the fields you send change.** Everything else in the snapshot — ratingKey, guid, ratings,
  duration — is preserved.
- **The Data18 ID is editable**, and an edited one is flagged manual (see [The Data18 Reference](#the-data18-reference)).
- **Removing an image deletes the file**, because the snapshot writer copies only still-referenced
  images into the new generation. Add it back by URL if that was a mistake.
- **A kept actor keeps their headshot**; a newly added one resolves on the next serve.
- **Changing Studio or Tagline moves the snapshot folder** (the layout is derived from them). The
  old directory is removed and the response reports the new key.
- The title cannot be blank, and the snapshot writer still rejects error-looking titles.

### The Data18 Reference

A scene's Data18 reference is in one of three states: *blank* (none recorded), *filled* (the scrape resolved it) or *manual* (typed in the editor).

- **Clearing** the ID drops the reference.
- **Several pages.** Extra page IDs may follow the first, space- or comma-separated. Images are pulled from every page in the order given, which covers a feature split across several Data18 pages.
- **Mapping slug.** The section shows the scene's computed mapping slug with a Copy button, ready to paste into a `data18_manual_mappings*.json` entry.
- **Exporting.** The state is a real column, so `/metadata` can filter on it: set **Data18** to *Manual*, and **Export Mappings** writes just the hand-made ones to a `data18_manual_mappings*.json` you can drop next to the base mappings file.
- A later scrape that resolves the same ID on its own records it as *filled*.

### Source Links and Source JSON

The header links back to the source site. Every scrape records what it fetched as the scene's source reference — URL, kind, and any raw API JSON — and the editor reads that first:

- a scene page shows **Scene ↗**;
- sites with no scene pages of their own (DirtyFlix-style) show **Listing ↗**;
- API-backed scrapers (Project1Service, FuckYouCash, Unzip VR…) get a collapsed **Source JSON** panel that pretty-prints the stored response instantly. Auth is a non-issue, because the JSON was captured during the scrape.

Scenes not re-scraped since source references were introduced fall back to decoding the identifier:

- browsable payloads still link;
- slug-only identifiers (Strike3, Reptyle, Nubiles, Naughty America, Stepped Up, ModelCentro) are rebuilt from each site's `direct_url_template`;
- API-endpoint payloads fetch into the panel on first expand, through the SSRF-guarded `GET /metadata/source-json` proxy.

Identifiers with nothing recoverable show neither link until their next refresh.
