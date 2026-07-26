# Selectors: XPath in parsel

Every client in this provider parses HTML with **XPath** via
[`parsel`](https://parsel.readthedocs.io/) (`Selector.xpath(...)`, lxml-backed).
This page collects the parsel
idioms and gotchas that come up most often.

## The Class-Selector Gotcha

The single most common "the scraper finds 0 rows" bug. `contains(@class,"title")`
is a plain **substring** match, so it wrongly matches `sup-title`, `date-and-site`,
etc. When you need a whole-token match (one exact class in the list), use the
concat-padding form — the house helper is:

```python
def _cls(name: str) -> str:
    return f'contains(concat(" ",normalize-space(@class)," ")," {name} ")'
```

Use the loose `contains(@class,"x")` for stable single-class markup, and the `_cls()` form
when a substring would over-match (Karups' `_cls('title')` is the canonical
example).

## House Idioms

- **Single text node** — the standard scalar read, trimmed, never throwing:

  ```python
  (sel.xpath('(//h1[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()
  ```

  `string(.)` collapses all descendant text into one string.

- **Multi-source extraction** — a local `xpaths` list looped with `for xpath in
  xpaths:` (the house formula). Name them by purpose: images → `xpaths`, summary
  → `summary_xpaths`, genres → `genre_xpaths`:

  ```python
  xpaths = ('//video/@poster', '//div[contains(@class,"gallery")]//a/@href')
  for xpath in xpaths:
      for raw in sel.xpath(xpath).getall():
          coll['push'](raw)
  ```

- **Fallback chains** — try each, take the first non-empty:

  ```python
  title = (sel.xpath('(//h1[@class="nice-title"])[1]').xpath('string(.)').get() or '').strip()
  if not title:
      title = (sel.xpath('(//div[@class="nazev"]//h2)[1]').xpath('string(.)').get() or '').strip()
  ```

- **Attributes** — `.../@src`, `.../@href`, `//meta[@property="og:image"]/@content`
  returned directly by `.get()` / `.getall()`.

- **Images** go through `self.image_collector(clean=...)` which trims, applies the
  per-source transform, skips empties, and de-dupes.

## Common XPath Patterns in This Repo

| Intent | parsel XPath |
|---|---|
| `//div[contains(@class,"item-update")]` | same (loose) |
| exact class `movie-block` | `//div[contains(concat(" ",normalize-space(@class)," ")," movie-block ")]` |
| `.//a/@href` | `el.xpath('@href').get()` / `el.xpath('(.//a)[1]/@href').get()` |
| `.//img/@src` | `el.xpath('(.//img)[1]/@src').get()` |
| `h1.title` text | `(sel.xpath('(//h1[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()` |
| `meta[property="og:image"]` content | `sel.xpath('(//meta[@property="og:image"])[1]/@content').get()` |
| `(//div[@class="gallery"]//a)[1]/@href` | same |

## Testing a Selector Quickly

Before committing, sanity-check the selector live:

1. Open the upstream page in Chrome / Firefox → DevTools → Console.
2. Run `$x("//your/xpath/here")` (Chrome's built-in XPath helper).

This catches most "compiles fine but matches nothing" problems before you boot the
dev server. The remainder is captured live in the `/dev` UI — the capture panel
shows the exact HTML the scraper saw, so you can re-run the selector against it.
See the [Dev UI guide](./dev-ui.md).
