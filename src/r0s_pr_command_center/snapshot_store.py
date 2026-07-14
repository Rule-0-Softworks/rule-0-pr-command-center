from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import cast

from r0s_pr_read_model.models import DashboardSnapshot


class RefreshInProgress(RuntimeError):
    pass


class SnapshotStore:
    def __init__(
        self, collector: Callable[[], DashboardSnapshot | Awaitable[DashboardSnapshot]]
    ) -> None:
        self._collector = collector
        self._current: DashboardSnapshot | None = None
        self._lock = asyncio.Lock()

    @property
    def current(self) -> DashboardSnapshot | None:
        return self._current

    async def refresh(self) -> DashboardSnapshot:
        if self._lock.locked():
            raise RefreshInProgress("a refresh is already running")
        async with self._lock:
            result = self._collector()
            snapshot = cast(
                DashboardSnapshot, await result if inspect.isawaitable(result) else result
            )
            self._current = snapshot
            return snapshot
