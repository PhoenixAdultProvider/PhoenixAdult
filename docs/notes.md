# Notes

### Bypass

Adoption is opt-in per call site. Not every scraper routes through the bypass
orchestrator — that would be a sweeping change. Two ways to use it where you need
it (typically the CDN/Cloudflare-protected people sources under
`app/utils/people/sources/`, e.g. IAFD / JavBus):

1. **Inside a `Client`** — pass `use_bypass=True` on the `FetchCtx` so the
   base `fetch_and_load` / `fetch_json` go through the bypass chain:

   ```python
   loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture, use_bypass=True), label)
   ```

2. **Directly**, where you only have a URL (e.g. a standalone source module):

   ```python
   from app.utils.http.bypass import bypass_get

   resp = await bypass_get(url)
   if not resp or resp.status != 200:
       return None
   sel = Selector(resp.body)
   ```

The bypass chain (`app/utils/http/bypass.py`) tries the configured providers in
`BYPASS_ORDER` — by default Impersonate (only if `curl_cffi` is installed),
FlareSolverr, Playwright (only if installed), then ReqBin — and returns `None`
when none are configured or all fail. It is what unblocks IAFD-backed people
lookups (gender detection + the IAFD source) once a provider is set (e.g.
`curl_cffi` installed, or `FLARESOLVERR_URL`); without one those lookups degrade
to empty rather than erroring.
