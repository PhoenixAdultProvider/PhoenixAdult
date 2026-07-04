from __future__ import annotations

import httpx2

from app.config.env import env
from app.utils.http.bypass_types import BypassRequest, BypassResponse
from app.utils.logging.logger import logger


def _parse_header_blob(blob: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not blob:
        return out
    for line in blob.splitlines():
        idx = line.find(':')
        if idx <= 0:
            continue
        out[line[:idx].strip().lower()] = line[idx + 1 :].strip()
    return out


class _ReqBinBackend:
    name = 'ReqBin'

    def is_available(self) -> bool:
        return env.reqbin_enabled

    async def request(self, req: BypassRequest) -> BypassResponse | None:
        cookie_header = '; '.join(f'{k}={v}' for k, v in req.cookies.items()) if req.cookies else ''
        headers = dict(req.headers)
        if cookie_header and 'Cookie' not in headers:
            headers['Cookie'] = cookie_header
        header_blob = '\n'.join(f'{k}: {v}' for k, v in headers.items())

        api_key = env.reqbin_api_key
        cfg_headers = {'Content-Type': 'application/json'}
        if api_key:
            cfg_headers['X-Api-Key'] = api_key

        for node in ('US', 'DE'):
            payload: dict[str, object] = {
                'method': req.method,
                'url': req.url,
                'headers': header_blob,
                'apiNode': node,
                'idnUrl': req.url,
            }
            if req.method == 'POST' and req.body is not None:
                payload['content'] = req.body
            try:
                # Credentialed third-party API — verify TLS.
                async with httpx2.AsyncClient(timeout=70.0, verify=True) as client:
                    resp = await client.post('https://api.reqbin.com/api/v1/requests', json=payload, headers=cfg_headers)
                if 200 <= resp.status_code < 300:
                    data = resp.json()
                    if data.get('Status'):
                        return BypassResponse(
                            status=data['Status'],
                            body=data.get('Content', ''),
                            headers=_parse_header_blob(data.get('ResponseHeaders')),
                            cookies={},
                            final_url=req.url,
                        )
            except (httpx2.HTTPError, ValueError) as err:
                logger.warn(f'bypass:ReqBin/{node}', str(err))
        return None


req_bin_backend = _ReqBinBackend()
