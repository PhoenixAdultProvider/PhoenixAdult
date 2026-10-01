from __future__ import annotations

import re
from pathlib import Path

from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.routes.provider_router import _INTERNAL_METADATA_FIELDS
from phoenixadult.services import plex_connections
from phoenixadult.utils.auth import user_store
from phoenixadult.utils.plex import client_hits
from tests.support import authed_client, plex_client

_HTML = Path(__file__).resolve().parents[2] / 'phoenixadult' / 'routes' / 'html'


def test_client_hits_are_recorded_only_on_the_provider_mount() -> None:
    client = plex_client()
    client.get('/health', headers={'x-plex-client-identifier': 'drive-by'})
    client.get('/phoenixadult/movies', headers={'x-plex-client-identifier': 'real-pms'})
    assert [h['clientId'] for h in client_hits.list_hits()] == ['real-pms']


def test_a_non_numeric_user_id_is_a_bad_request() -> None:
    client = authed_client()
    for path in ('/users/api/delete', '/users/api/password', '/users/api/admin'):
        assert client.post(path, json={'id': 'abc', 'password': 'Password12!'}).status_code == 400


def test_a_client_id_owned_by_another_user_cannot_be_claimed() -> None:
    admin = authed_client()
    theirs = plex_connections.create(user_store.create_user('owner', 'pw-owner', is_admin=False), 'Theirs')
    plex_connections.set_allowed_clients(theirs, ['their-pms'])
    mine = admin.post('/plex/connections', json={'name': 'Mine'}).json()['id']
    refused = admin.post(f'/plex/connections/{mine}', json={'allowedClients': ['their-pms']})
    assert refused.status_code == 409
    assert admin.post(f'/plex/connections/{mine}', json={'allowedClients': ['my-pms']}).status_code == 200


def test_guessing_the_current_password_is_throttled() -> None:
    client = authed_client()
    codes = [client.post('/account/api/password', json={'current': 'wrong', 'new': 'Newpassword1!'}).status_code for _ in range(8)]
    assert codes[0] == 403
    assert 429 in codes


def test_internal_fields_never_reach_plex() -> None:
    md = {
        'type': 'movie',
        'ratingKey': 'k',
        'guid': 'g',
        'title': 't',
        'sourceRef': {'url': 'https://x', 'data': {'secret': 1}},
        'data18': {'type': 'scene', 'id': '1'},
        'Image': [{'url': 'https://x/1.jpg', 'type': 'coverPoster', 'locked': True, 'rotate': 90}],
    }
    response = PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': 'p', 'size': 1, 'Metadata': [md]}})
    served = response.model_dump(by_alias=True, exclude_none=True, exclude=_INTERNAL_METADATA_FIELDS)['MediaContainer']['Metadata'][0]
    assert 'sourceRef' not in served and 'data18' not in served
    assert served['Image'] == [{'url': 'https://x/1.jpg', 'type': 'coverPoster'}]


def test_inline_handlers_never_embed_escaped_values_in_js_strings() -> None:
    for page in _HTML.glob('*.html'):
        for line in page.read_text(encoding='utf-8').splitlines():
            assert not re.search(r"on\w+=\"[^\"]*\\'' \+ esc\(", line), f'{page.name}: {line.strip()}'
