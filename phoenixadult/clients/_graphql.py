from __future__ import annotations

import json
from typing import Any, ClassVar

import httpx2

from phoenixadult.clients.base import Client
from phoenixadult.config.env import env
from phoenixadult.models.capture import RawCaptureEntry
from phoenixadult.utils.http.bypass import bypass_post
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.logging.response_trace import trace_response


class GraphQLClient(Client):
    default_headers: ClassVar[dict[str, str]] = {'Content-Type': 'application/json'}

    def _envelope(self, text: str, tag: str, capture_label: str | None, capture_sink: list[RawCaptureEntry] | None) -> Any:
        try:
            data = json.loads(text)
        except ValueError as err:
            logger.warn('graphql', f'{tag} -> invalid JSON: {err}')
            return None
        if capture_sink is not None and capture_label is not None:
            capture_sink.append(RawCaptureEntry(capture_label, 'json', data))
        if isinstance(data, dict) and data.get('errors'):
            logger.warn('graphql', f'{tag} -> GraphQL errors: {json.dumps(data["errors"])[:300]}')
        return data.get('data') if isinstance(data, dict) else None

    async def graphql(
        self,
        endpoint: str,
        query: str,
        variables: dict[str, Any],
        headers: dict[str, str] | None = None,
        capture_label: str | None = None,
        capture_sink: list[RawCaptureEntry] | None = None,
        use_bypass: bool = False,
    ) -> Any:
        tag = capture_label or endpoint
        body = json.dumps({'query': query, 'variables': variables})
        bypass_ok = use_bypass or env.bypass_auto_retry

        try:
            r = await self.http.post(endpoint, content=body, headers=headers)
            trace_response(r)
        except httpx2.HTTPError as err:
            logger.warn('graphql', f'{tag} -> request failed: {err}')
            r = None

        if r is not None:
            content_type = r.headers.get('content-type', '')
            if r.status_code < 400 and 'json' in content_type.lower():
                logger.debug('graphql', f'{tag} -> HTTP {r.status_code} ({len(r.text)}B)')
                return self._envelope(r.text, tag, capture_label, capture_sink)
            snippet = ' '.join(r.text.split())[:160]
            logger.warn('graphql', f'{tag} -> HTTP {r.status_code} ({content_type or "?"}, {len(r.text)}B) non-JSON: {snippet}')
            if not bypass_ok:
                if capture_sink is not None and capture_label is not None:
                    capture_sink.append(RawCaptureEntry(capture_label, 'html', r.text))
                return None
        elif not bypass_ok:
            return None

        logger.info('graphql', f'{tag} -> retrying POST via bypass')
        resp = await bypass_post(endpoint, body, {'Content-Type': 'application/json', **(headers or {})})
        if not resp or resp.status >= 400:
            logger.warn('graphql', f'{tag} -> bypass failed (status={resp.status if resp else "none"})')
            return None
        logger.info('graphql', f'{tag} -> recovered via bypass ({resp.status}, {len(resp.body)}B)')
        return self._envelope(resp.body, tag, capture_label, capture_sink)
