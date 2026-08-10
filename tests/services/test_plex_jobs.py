from __future__ import annotations

import pytest

from phoenixadult.services import plex_jobs


@pytest.fixture(autouse=True)
def _fresh() -> None:
    plex_jobs.reset()


class _Report:
    def as_dict(self) -> dict:
        return {'ok': True, 'n': 7}


async def test_launch_runs_the_job_and_stores_the_serialized_report() -> None:
    async def work() -> _Report:
        plex_jobs.set_progress(1, 'reconcile', total=10, done=4, phase='inspecting')
        return _Report()

    assert plex_jobs.launch(1, 'reconcile', work) is True
    assert plex_jobs.is_active(1, 'reconcile') is True
    assert plex_jobs.launch(1, 'reconcile', work) is False, 'no second launch while active'

    await plex_jobs._jobs[(1, 'reconcile')]['task']
    status = plex_jobs.status_for(1)['reconcile']
    assert status['active'] is False
    assert status['report'] == {'ok': True, 'n': 7}
    assert status['total'] == 10 and status['done'] == 4
    assert 'task' not in status, 'the asyncio task handle is never serialized to the client'


async def test_a_raising_job_captures_the_error() -> None:
    async def boom() -> _Report:
        raise RuntimeError('kaboom')

    plex_jobs.launch(2, 'import', boom)
    await plex_jobs._jobs[(2, 'import')]['task']
    status = plex_jobs.status_for(2)['import']
    assert status['active'] is False and status['error'] == 'kaboom' and status['report'] is None


async def test_a_relaunch_after_completion_is_allowed() -> None:
    async def work() -> _Report:
        return _Report()

    plex_jobs.launch(3, 'collection-logos', work)
    await plex_jobs._jobs[(3, 'collection-logos')]['task']
    assert plex_jobs.launch(3, 'collection-logos', work) is True, 'a finished job can run again'
    await plex_jobs._jobs[(3, 'collection-logos')]['task']
