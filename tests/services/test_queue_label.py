from __future__ import annotations

from phoenixadult.models.scrape import SearchResult
from phoenixadult.services.metadata_service import _queue_label
from phoenixadult.utils.cache import search_store
from phoenixadult.utils.helpers.helpers import embed_subsite, pack_cur_id
from phoenixadult.utils.plex.rating_key import to_rating_key


def _seed(cur_id: str, title: str, subsite: str | None = None) -> None:
    search_store.save(
        ('Nubiles Porn', 'some search', '2024-03-14', '', ''),
        [SearchResult(title=title, scene_url='https://nubiles-porn.com/video/watch/9', cur_id=cur_id, subsite=subsite)],
    )


def test_the_update_label_finds_the_title_behind_an_embedded_subsite() -> None:
    plain = pack_cur_id(['181500', '2024-03-14'])
    _seed(plain, 'Sneaky Study Break', subsite='Step Siblings Caught')
    rating_key = to_rating_key(embed_subsite(plain, 'Step Siblings Caught'), 'Nubiles Porn', '2024-03-14')
    assert _queue_label(rating_key) == 'Sneaky Study Break [Step Siblings Caught] 2024-03-14'


def test_the_update_label_without_a_stored_row_brands_the_subsite() -> None:
    plain = pack_cur_id(['181501', '2024-03-14'])
    rating_key = to_rating_key(embed_subsite(plain, 'Moms Teach Sex'), 'Nubiles Porn', '2024-03-14')
    assert _queue_label(rating_key) == '[Moms Teach Sex] 2024-03-14'


def test_the_update_label_still_resolves_a_plain_cur_id() -> None:
    plain = pack_cur_id(['181502', '2024-03-14'])
    _seed(plain, 'Plain Title')
    rating_key = to_rating_key(plain, 'Nubiles Porn', '2024-03-14')
    assert _queue_label(rating_key) == 'Plain Title [Nubiles Porn] 2024-03-14'
