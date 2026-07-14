import asyncio

import pytest

from r0s_pr_command_center.snapshot_store import RefreshInProgress, SnapshotStore


@pytest.mark.anyio
async def test_failed_refresh_retains_previous_snapshot(snapshot_factory) -> None:
    calls = 0

    def collector():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("GitHub unavailable")
        return snapshot_factory(repository_count=36)

    store = SnapshotStore(collector)
    first = await store.refresh()
    with pytest.raises(RuntimeError, match="GitHub unavailable"):
        await store.refresh()
    assert store.current is first


@pytest.mark.anyio
async def test_overlapping_refresh_is_rejected(snapshot_factory) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def collector():
        entered.set()
        await release.wait()
        return snapshot_factory(repository_count=36)

    store = SnapshotStore(collector)
    first = asyncio.create_task(store.refresh())
    await entered.wait()
    with pytest.raises(RefreshInProgress):
        await store.refresh()
    release.set()
    await first
