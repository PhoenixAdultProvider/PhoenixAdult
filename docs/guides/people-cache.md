---
sidebar_label: People Cache
description: Review, edit and re-fetch the cached cast and crew headshots.
---

# People Cache

The people cache (`PEOPLE_CACHE_ENABLE`) stores a headshot for every actor, director and producer the provider has served, browsable at `/people`.

## Browsing and Filtering

Each card shows the person's headshot and the source it came from: `IAFD`, `Indexxx`, `Scene` (the scene page's own actor image) or `Generic` (the placeholder silhouette). Sources are recorded as images are cached; images that predate the recording had theirs derived from the image host, with anything no source claims counted as `Scene`.

The upstream original loads beside each card, two at a time as cards scroll into view, so a slow upstream never ties up the page.

Filters (all persist with the others and clear with **Reset Filters**):

| Filter | Shows |
|---|---|
| Name search | names matching the text, within the current tab |
| **Source** | headshots from one source — a dropdown of the sources actually present, plus Unrecorded |
| **Cropped Only** | face-cropped headshots |
| **No Upstream** | headshots with no recorded source URL — they cannot be re-pulled or restored |
| **Generic Only** | people still carrying the placeholder silhouette |
| **Single Name** | mononyms: one word and nothing after it, so `Haley`, `LaSirena69` and `A.J.` match while `Kate Smith` does not — credits a site published without a surname |

## Editing a Headshot

The **Edit** button on `/people` (between "Use Original" and Purge) opens `/people/edit?filename=<file>`. Saving writes and returns to the list; Cancel discards.

The editor shows the performer's name as its heading, with **Copy** and **Search IAFD** buttons, and covers the upstream original URL and the cropped status.

- **Fetch From** runs one chosen photo source — `PEOPLE_SOURCE_ORDER`'s remote sources, minus Local Storage, which returns an already-cached file rather than an upstream URL — and fills the URL field with what it finds. Nothing is downloaded until you save, so a wrong hit costs nothing.
- **Saving re-downloads the image** and replaces the cached file, cropping per the checkbox rather than `PEOPLE_CACHE_FACE_ENABLE`. That makes it a way to crop or un-crop one headshot. The checkbox is disabled when `opencv-python-headless` is not installed.
- **Recorded Source** relabels where the headshot came from without touching the image — for entries that predate source tracking, or one filed under the wrong site. Fetch From sets it to whatever answered. IAFD already returns a framed head-and-shoulders portrait, so fetching from there also clears Cropped Status, and a second crop is not applied.
- **Scenes** lists every cached snapshot that credits the person in that headshot's role — title (linking to the snapshot editor), date, studio and sub-site — newest first. It reads the snapshot cache, so it says so when `METADATA_CACHE_ENABLE` is off.
- **SFW Mode** hides the preview card. Like the metadata screens it shares the setting, and never hands the browser an image URL while it is on.

### Why Saving Re-Pushes Scenes

Saving also **flags every scene crediting that performer to re-push their headshots**:

1. A snapshot freezes the served image URL, which carries a content-hash cache-buster.
2. Replacing the bytes changes that token, but a cached serve would keep handing Plex the old URL — and Plex only re-fetches when a URL changes.
3. The flag (`scenes.force_refresh`) makes the next serve clear that scene's people-cache thumbs, so the image backfill rebuilds them at the current bytes. Then it clears itself: one forced re-push per edit, not a permanent state.

## Fetching Images in Bulk

**Fetch Images for Shown** applies one source to everyone the current filters leave visible. Tab, Cropped Only, No Upstream and the name search all narrow it, so "every actor with no upstream recorded" is a filter away.

- It asks for confirmation with the count first.
- For each person it looks the name up at that source. On a hit it replaces the cached file, keeps that person's existing cropped setting, and flags their scenes to re-push. A person the source doesn't know is left exactly as they were.
- Lookups run three at a time to stay polite to the source.
- A batch is capped at 250 people; anything beyond is reported as skipped rather than silently dropped.
- Progress streams back per person (`Fetching 21 of 60 from IAFD…` plus a bar).
