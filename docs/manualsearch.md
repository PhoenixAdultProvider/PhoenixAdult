# Manual Search Usage

Each search query can be comprised of *up to* 5 parts, depending on the supported [*search type*](./manualsearch.md#search-types-and-their-capabilities):
- `Site` - Either the shorthand abbreviation, or full site name.
- `Date` - Follows immediately after site name, in the format of either `YYYY-MM-DD` or `YY-MM-DD` ([more on how this can be used](./manualsearch.md#search-types-and-their-capabilities))
- `Actor(s)`
- `Title` - The title/name of the scene.
- `StudioID` - A numeric value found in the URL of a studio page.
- `Studio` - Studio name used for manual add.
- `ActressID` - An alphanumeric value found in the URL of an actress page. Typically similar to the name of the actress.
- `SceneID` - A numeric value found in the URL of a scene page.
- `Direct URL` - A string of characters at the end of a URL of a scene page. Typically includes some combination of a SceneID, Scene Title, or Actor.

## Search Types and their Capabilities
There are 4 available search/matching methods, as listed below:
+ **Enhanced Search:** `Title` `Actor` `Date` `SceneID`
+ **Limited Search:** `Title` `Actor`
+ **Exact Match:** `StudioID` `ActressID` `SceneID` `Direct URL`
+ **Manual NFO:** `manual.<basename>.<ext>` — pulls metadata from a local `.nfo` file

## Enhanced Search
#### Multi-Search Available.
+ **Available search methods:**
  - **Title**
  - **Actor(s)**
+ **Available match methods:**
*These can be used in conjunction with available search methods and will increase the possibility of locating the correct scene. However, it is not recommended they be used as standalone search terms. Usually, at least one of these can be utilized (depending on the site)*
  - **Date**
  - **SceneID**

+ **Date Match:** Date can be entered directly after the site name, but before any other search terms. This will increase the possibility for a match.
+ **SceneID Match:** SceneID can be entered directly after the site name (and date), but before all other search terms. This will increase the possibility for a match.

## Limited Search
#### Limited-Search Available.
+ **Available search methods:**
  - **Title**
  - **Actor(s)**

## Exact Match
#### No Search Available.
*Locating the correct scene is entirely dependent on entering the correct StudioID, ActressID, SceneID, or Direct URL. However, entering additional search terms may help with matching.*
+ **StudioID:** Typically used when sites host many small, independent studios (ie. Clips4Sale).
  - Can add the Date (before the StudioID).
  - Can add a Title/Actor (after the StudioID). This acts as a search term.
+ **ActressID:** Typically used when actresses have their own page, but scenes do not. 
  - Can add the Date (before the ActressID).
  - Can add a Title/Actor (after the ActressID). This acts as a search term.
+ **SceneID**
  - Can add the Date (before the SceneID).
  - Can add a Title/Actor (after the SceneID).
+ **Direct URL**
  - Can add the Date (before the URL).
  - Adding any additional terms (ie. Title/Actors) will cause issues with matching.

## Manual NFO

*If the studio is not yet supported (or you simply want full control over the metadata), drop a Kodi/XBMC-style `.nfo` file on disk and PhoenixAdult will serve its contents to Plex. Check [the sitelist](./sitelist.md) for upstream-scraped sites first.*

### How it Works

When the filename Plex sends starts with the **match token** (`manual.` by default), the provider skips every upstream scraper, strips the token, and looks for an `.nfo` whose basename matches the rest of the filename exactly. Match found → metadata served from the NFO; match missed → empty result.

### Folder

Default: `./local/manual/` (relative to the provider's working directory). Override with the `MANUAL_NFO_PATH` env var or the **Manual NFO folder** entry in the config UI.

Two layouts are supported per basename — pick whichever fits the item:

**Folder layout** (recommended for items with sibling images):
```
<MANUAL_NFO_PATH>/
  <basename>/
    <basename>.nfo
    <basename>-poster.{jpg,png,webp}    (optional)
    <basename>-fanart.{jpg,png,webp}    (optional)
```

The folder layout also supports arbitrary categorization folders above the
basename folder — any depth, any names. The lookup walks the tree and matches
the first `<basename>/<basename>.nfo` it finds. Shallower wins on collisions:
```
<MANUAL_NFO_PATH>/
  Studios/
    Paradise Films/
      <basename>/
        <basename>.nfo
        <basename>-poster.jpg
  VR/
    <basename2>/
      <basename2>.nfo
```

**Flat layout** (NFO + images directly under the root, no per-item folder):
```
<MANUAL_NFO_PATH>/
  <basename>.nfo
  <basename>-poster.{jpg,png,webp}      (optional)
  <basename>-fanart.{jpg,png,webp}      (optional)
```

Sibling poster/fanart files are preferred over any `<thumb>` / `<fanart><thumb>` URLs declared in the NFO — those URLs are only used when no sibling exists.

### Indexing & Freshness

The provider builds an in-memory index of every `.nfo` under `MANUAL_NFO_PATH` on the first lookup, then reuses it for ~60 seconds before refreshing. This keeps Plex match + detail fetches fast even on libraries with thousands of items. Newly-dropped NFOs are picked up two ways:
- automatically on the next lookup after the 60-second TTL expires, or
- immediately on the first match attempt that misses the cache — the index is rebuilt once on miss (throttled to at most one rebuild every ~2s) so adding a new file + scanning it in Plex generally Just Works.

If you ever need to force a refresh sooner, restart the provider — there's no public flush endpoint.

### Match Token

The token is configurable via `MANUAL_NFO_TOKEN` (default `manual`). The match is case-insensitive on the token, and the rest of the filename (the **basename**) is preserved verbatim — dots, digits, and case — so the on-disk lookup is unambiguous.

### NFO Schema

The full schema PhoenixAdult reads (every field is optional except `<title>`):

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<movie>
  <title></title>
  <originaltitle></originaltitle>
  <sorttitle></sorttitle>
  <set></set>              <!-- maps to the Plex collection -->
  <year></year>            <!-- used as YYYY-01-01 when <releasedate> is empty -->
  <trailer></trailer>
  <votes></votes>
  <rating></rating>
  <outline></outline>      <!-- summary fallback when <plot> is empty -->
  <plot></plot>            <!-- summary -->
  <tagline></tagline>
  <runtime></runtime>
  <releasedate></releasedate>
  <studio></studio>
  <thumb></thumb>          <!-- poster fallback when no -poster.* sibling exists -->
  <fanart>
    <thumb></thumb>        <!-- fanart fallback when no -fanart.* sibling exists -->
  </fanart>
  <mpaa></mpaa>
  <id></id>
  <data18></data18>        <!-- optional: pin the data18 scene for image enrichment (see below) -->
  <genre></genre>          <!-- may repeat -->
  <actor>
    <name></name>
    <role></role>
    <thumb></thumb>
    <gender></gender>      <!-- male | female | trans (case-insensitive); any other value drops to "" -->
  </actor>                 <!-- may repeat -->
</movie>
```

### Malformed XML is Repaired, not Rejected

Tags the provider doesn't know (`<uniqueid>`, `<premiered>`, …) are ignored, and every tag above is
optional. A file that isn't well-formed XML is repaired rather than dropped:

| in the file | what you get |
|---|---|
| `<genre>Pantyhose & Stockings</genre>` | `Pantyhose & Stockings` — a bare `&` is escaped |
| `<plot>3 < 4</plot>` | `3 < 4` — a stray `<` is escaped |
| `&nbsp;`, `&eacute;`, … | the character it names |
| control characters | stripped |
| unclosed or mis-nested tags | salvaged where possible |

Each repair logs a warning naming the file and quoting the offending line. Writing valid XML
(`&amp;`, `&lt;`) is still preferred — the repair pass is a safety net, not a licence.

### Pinning the Data18 Scene

When data18 enrichment is on (`DATA18_ENABLE=true`), extra images are normally found by
searching data18 for `<title>`. A `<data18>` tag pins the exact scene instead, skipping the
search — useful when the title is ambiguous or the search picks the wrong scene.

Any of these forms work; they all resolve to `https://www.data18.com/scenes/1150700`:

```xml
<data18>1150700</data18>
<data18>scenes/1150700</data18>
<data18>https://www.data18.com/scenes/1150700</data18>
<data18>delicious-firsts-hussiepass</data18>   <!-- a scene slug works too -->
```

Notes:

- `<data18>` never turns enrichment on. `DATA18_ENABLE=true` and the site's `data18_enrichment`
  flag still gate it — the tag only changes *how* the scene is found.
- A value that isn't a data18 scene reference (an off-host URL, a non-scene path) is refused with
  a warning, and the normal title search runs instead.
- With a `<data18>` tag, `<title>` is no longer required for enrichment.

### End-to-End Example

Filename Plex sends:
```
manual.paradisefilms.27885.naughty.fantasy.mp4
```

Layout on disk:
```
./local/manual/
  paradisefilms.27885.naughty.fantasy/
    paradisefilms.27885.naughty.fantasy.nfo
    paradisefilms.27885.naughty.fantasy-poster.jpg
    paradisefilms.27885.naughty.fantasy-fanart.jpg
```

The provider strips `manual.`, looks up `paradisefilms.27885.naughty.fantasy/paradisefilms.27885.naughty.fantasy.nfo`, parses it, and returns a single match with the poster/fanart wired through `/images/manual-nfo/...`.

## Notes
+ **Date Add** - Some sites don't make release dates available. The agent will scrape the date from your filename/search term, instead.

## Search Examples
Depending on the capability of any one network/site, you can try a few combiations of the above.

Here are some examples for each type of search:
+ **Enhanced Search** examples:
  - A full search, with all available details:
    - `SiteName` - `YY-MM-DD` - `SceneID` - `Jane Doe` - `An Interesting Plot`
  - A minimal search, with fewer details, but includes SceneID:
    - `SiteName` - `SceneID` - `Jane Doe`
  - A basic search with the most common details:
    - `SiteName` - `YY-MM-DD` - `An Interesting Plot`
  - Another minimal search, using site shorthand:
    - `SN` - `An Interesting Plot`

+ **Limited Search** examples:
  - A search using both actor and scene title:
    - `SiteName` - `Jane Doe` - `An Interesting Plot`
  - A search using site name and an actor from the scene:
    - `SiteName` - `Jane Doe`
  - A search using site shorthand with the scene title:
    - `SN` - `An Interesting Plot`

+ **Exact Match** examples:
  - An exact search using site name and ID:
    - `SiteName` - `SceneID`
  - An exact search using site shorthand and ID:
    - `SN` - `SceneID`
  - A direct url match, using only a suffix:
    - `SiteName` - `Direct URL`
      - `PornPros` - `eager-hands` (taken from the URL [https://pornpros.com/video/**eager-hands**](https://dereferer.me/?https%3A//pornpros.com/video/eager-hands))
    - `SiteName` - `YY-MM-DD` - `Direct URL`
      - `Mylf` - `2019.01.01` - `1809 manicured-milf-masturbation` (taken from the URL [https://www.mylf.com/movies/**1809/manicured-milf-masturbation**](https://dereferer.me/?https%3A//www.mylf.com/movies/1809/manicured-milf-masturbation))
      - `Wicked` - `2019.10.10` - `Stranger-Than-Fiction 77675` (taken from the URL [https://www.wicked.com/en/movie/**Stranger-Than-Fiction/77675**](https://dereferer.me/?https%3A//www.wicked.com/en/movie/Stranger-Than-Fiction/77675))
      - `Wicked` - `2019.10.10` - `Stranger Than Fiction Scene 1 167063` (taken from the URL [https://www.wicked.com/en/video/**Stranger-Than-Fiction-Scene-1/167063**](https://dereferer.me/?https%3A//www.wicked.com/en/video/Stranger-Than-Fiction-Scene-1/167063))

+ **Manual NFO** examples:
  - Folder layout, full metadata:
    - File: `manual.paradisefilms.27885.naughty.fantasy.mp4`
    - On disk: `./local/manual/paradisefilms.27885.naughty.fantasy/paradisefilms.27885.naughty.fantasy.nfo` (+ optional `-poster.jpg` / `-fanart.jpg` siblings)
  - Categorized folder layout, same basename:
    - On disk: `./local/manual/Studios/Paradise Films/paradisefilms.27885.naughty.fantasy/paradisefilms.27885.naughty.fantasy.nfo`
  - Flat layout, single one-off:
    - File: `manual.my.test.scene.mp4`
    - On disk: `./local/manual/my.test.scene.nfo` (+ optional `my.test.scene-poster.jpg`)
  - Custom match token (e.g. `MANUAL_NFO_TOKEN=nfo`):
    - File: `nfo.my.test.scene.mp4` → same lookup as above

## Custom Title Naming

#### Create a Custom Title from Data Pulled by Scrapers

Enable custom title formats in agent settings

Create a string with a combination of fixed characters and metadata tags

Tags should be used in the format: `{Tag Name}`

- `Title` - The title/name of the scene originally pulled by scraper
- `Actors` - Comma separated string consisting of all actors
- `Studio` - Studio producing video
- `Series` - Specific series for video

### Examples:
- \[Series\] Title:
    - `[{Series}] {Title}`
- \[Actors\] Title:
    - `[{Actors}] {Title}`
