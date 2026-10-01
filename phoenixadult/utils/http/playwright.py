from __future__ import annotations

import importlib.util
import os
import tempfile
from typing import Any
from urllib.parse import urlsplit

from phoenixadult.config.env import env
from phoenixadult.utils.http.bypass_types import BypassRequest, BypassResponse
from phoenixadult.utils.http.ssrf_guard import guard_target
from phoenixadult.utils.logging.logger import logger


class _PlaywrightBackend:
    name = 'Playwright'

    def is_available(self) -> bool:
        return importlib.util.find_spec('playwright') is not None

    async def request(self, req: BypassRequest) -> BypassResponse | None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.debug('bypass:Playwright', 'not installed; skipping')
            return None
        try:
            await guard_target(req.url)
        except ValueError as err:
            logger.warn('bypass:Playwright', f'refusing {req.url}: {err}')
            return None

        timeout = req.timeout_ms or env.bypass_timeout_ms
        try:
            async with async_playwright() as pw:
                launch_env = {**os.environ, 'HOME': os.environ.get('HOME') or tempfile.gettempdir()}
                browser = await getattr(pw, env.playwright_browser).launch(headless=True, env=launch_env)
                ctx = await browser.new_context(ignore_https_errors=True, extra_http_headers=req.headers or {})
                if req.cookies:
                    host = urlsplit(req.url).hostname or ''
                    await ctx.add_cookies([{'name': n, 'value': v, 'domain': host, 'path': '/'} for n, v in req.cookies.items()])
                page = await ctx.new_page()
                try:
                    response: Any
                    if req.method == 'POST':
                        response = await page.request.post(req.url, headers=req.headers or {}, data=req.body, timeout=timeout)
                        body = await response.text()
                    else:
                        response = await page.goto(req.url, wait_until='domcontentloaded', timeout=timeout)
                        body = await page.content()
                    if not response:
                        return None
                    cookie_map = {c['name']: c['value'] for c in await ctx.cookies()}
                    user_agent = await page.evaluate('navigator.userAgent')
                    return BypassResponse(
                        status=response.status,
                        body=body,
                        headers=dict(response.headers),
                        cookies=cookie_map,
                        final_url=page.url,
                        user_agent=str(user_agent or ''),
                    )
                finally:
                    await ctx.close()
                    await browser.close()
        except Exception as err:  # noqa: BLE001 - any Playwright failure → skip backend
            logger.warn('bypass:Playwright', f'{req.url} failed: {err}')
            return None


playwright_backend = _PlaywrightBackend()
