"""FastAPI composition for the read-only PR command center."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from r0s_pr_read_model.client import GitHubClient
from r0s_pr_read_model.collect import collect_snapshot
from r0s_pr_read_model.models import DashboardSnapshot

from .github_auth import create_token_provider
from .settings import Settings
from .snapshot_store import RefreshInProgress, SnapshotStore
from .views import DashboardFilter, render_dashboard, render_pr_detail

# Keep the importable loopback scaffold available without reading a token at import time.
app = FastAPI()


def create_app(settings: Settings, store: SnapshotStore | None = None) -> FastAPI:
    """Create the local, read-only dashboard application."""
    if store is None:
        client = GitHubClient(create_token_provider(settings))

        def collect() -> DashboardSnapshot:
            return collect_snapshot(client, settings.organization, datetime.now(UTC))

        store = SnapshotStore(lambda: asyncio.to_thread(collect))

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        await store.refresh()
        yield

    application = FastAPI(title="R0S PR Command Center", lifespan=lifespan)
    application.state.snapshot_store = store
    application.mount(
        "/static",
        StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")),
        name="static",
    )

    @application.get("/", response_class=HTMLResponse)
    async def dashboard(
        check_state: str | None = Query(default=None),
        required_state: str | None = Query(default=None),
        review: str | None = Query(default=None),
        merge_blocked: bool | None = Query(default=None),
    ) -> HTMLResponse:
        snapshot = store.current
        if snapshot is None:
            raise HTTPException(503, "snapshot unavailable")
        selected = DashboardFilter(check_state, required_state, review, merge_blocked)
        return HTMLResponse(render_dashboard(snapshot, selected))

    @application.post("/refresh")
    async def refresh() -> RedirectResponse:
        try:
            await store.refresh()
        except RefreshInProgress as error:
            raise HTTPException(409, str(error)) from error
        return RedirectResponse("/", status_code=303)

    @application.get("/prs/{owner}/{repo}/{number}", response_class=HTMLResponse)
    async def detail(owner: str, repo: str, number: int) -> HTMLResponse:
        snapshot = store.current
        match = (
            next(
                (
                    pr
                    for pr in snapshot.pull_requests
                    if pr.repository == f"{owner}/{repo}" and pr.number == number
                ),
                None,
            )
            if snapshot
            else None
        )
        if match is None:
            raise HTTPException(404, "pull request not present in current snapshot")
        return HTMLResponse(render_pr_detail(match))

    @application.get("/api/snapshot")
    async def snapshot_json() -> JSONResponse:
        snapshot = store.current
        if snapshot is None:
            raise HTTPException(503, "snapshot unavailable")
        return JSONResponse(serialize_snapshot(snapshot))

    @application.get("/health")
    async def health() -> dict[str, object]:
        return {"status": "ok", "snapshot_available": store.current is not None}

    return application


def serialize_snapshot(snapshot: DashboardSnapshot) -> dict[str, object]:
    """Return only normalized snapshot fields; never expose settings or client state."""
    return {
        "organization": snapshot.organization,
        "queried_at": snapshot.queried_at.isoformat(),
        "repository_count": snapshot.repository_count,
        "pull_request_count": len(snapshot.pull_requests),
        "is_complete": snapshot.is_complete,
        "source_errors": [
            {
                "repository": item.repository,
                "pull_request_number": item.pull_request_number,
                "stage": item.stage,
                "message": item.message,
                "graphql_path": list(item.graphql_path),
                "graphql_locations": [list(point) for point in item.graphql_locations],
            }
            for item in snapshot.source_errors
        ],
        "pull_requests": [
            {
                "repository": pr.repository,
                "number": pr.number,
                "title": pr.title,
                "url": pr.url,
                "author": pr.author,
                "is_draft": pr.is_draft,
                "base_ref_name": pr.base_ref_name,
                "head_ref_name": pr.head_ref_name,
                "head_sha": pr.head_sha,
                "review_decision": pr.review_decision,
                "mergeable": pr.mergeable,
                "merge_state_status": pr.merge_state_status,
                "merge_blocked": pr.merge_blocked,
                "all_context_state": pr.all_context_state.value,
                "required_check_state": pr.required_check_state.value,
                "check_evidence_state": pr.check_evidence_state.value,
                "diagnostics": [
                    {"code": item.code, "message": item.message, "source": item.source}
                    for item in pr.diagnostics
                ],
                "contexts": [
                    {
                        "kind": item.kind,
                        "name": item.name,
                        "status": item.status,
                        "conclusion": item.conclusion,
                        "url": item.url,
                        "app_database_id": item.app_database_id,
                        "raw": dict(item.raw),
                    }
                    for item in pr.contexts
                ],
            }
            for pr in snapshot.pull_requests
        ],
    }


def run() -> None:
    """Start the local command-center server."""
    settings = Settings.from_environment(os.environ)
    uvicorn.run(create_app(settings), host="127.0.0.1", port=8000)
