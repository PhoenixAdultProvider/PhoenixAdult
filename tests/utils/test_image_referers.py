from __future__ import annotations

from app.utils.images.image_fetcher import _is_data18_host, _referers_for

_DT18_REFERERS = ['http://i.dt18.com', 'https://www.data18.com']


def test_dt18_host_detected() -> None:
    assert _is_data18_host('https://bdn.dt18.com/312/3353/350516/08.jpg')
    assert _is_data18_host('https://vs.dt18.com/img/1/312/350516/04.jpg')
    assert _is_data18_host('https://www.data18.com/covers/1.jpg')
    assert not _is_data18_host('https://images.momlover.com/videos/photos/459/1.jpg')


def test_dt18_referers_win_over_configured() -> None:
    url = 'https://bdn.dt18.com/312/3353/350516/08.jpg'
    assert _referers_for(url, ['https://momwantstobreed.com/video/watch/204116']) == _DT18_REFERERS
    assert _referers_for(url, None) == _DT18_REFERERS


def test_configured_referers_apply_to_other_hosts() -> None:
    url = 'https://images.momlover.com/videos/photos/459/1.jpg'
    assert _referers_for(url, ['https://momlover.com/video/watch/1']) == ['https://momlover.com/video/watch/1', None]
    assert _referers_for(url, None) == [None]
