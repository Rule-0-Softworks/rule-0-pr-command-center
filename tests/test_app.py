from dataclasses import replace

from fastapi.testclient import TestClient
from r0s_pr_read_model.models import CheckEvidenceState, CheckState
from starlette.routing import Route

from r0s_pr_command_center.app import create_app
from r0s_pr_command_center.settings import Settings
from r0s_pr_command_center.snapshot_store import SnapshotStore


def test_dashboard_refresh_and_detail_are_read_only(snapshot_factory) -> None:
    snapshot = snapshot_factory(repository_count=36)
    app = create_app(Settings("secret"), SnapshotStore(lambda: snapshot))
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.post("/refresh", follow_redirects=False).status_code == 303
        pr = snapshot.pull_requests[0]
        detail = client.get(f"/prs/{pr.repository}/{pr.number}")
        assert detail.status_code == 200
        assert pr.title in detail.text
        assert client.post("/api/snapshot").status_code == 405


def test_partial_snapshot_is_visible_in_html_and_json(snapshot_factory) -> None:
    snapshot = snapshot_factory(with_source_error=True)
    app = create_app(Settings("secret"), SnapshotStore(lambda: snapshot))
    with TestClient(app) as client:
        assert "Completeness warning" in client.get("/").text
        assert client.get("/api/snapshot").json()["is_complete"] is False


def test_snapshot_json_exposes_partial_check_evidence(snapshot_factory) -> None:
    pr = replace(
        snapshot_factory().pull_requests[0],
        check_evidence_state=CheckEvidenceState.INCOMPLETE,
        all_context_state=CheckState.UNKNOWN,
    )
    snapshot = replace(snapshot_factory(with_source_error=True), pull_requests=(pr,))
    app = create_app(Settings("secret"), SnapshotStore(lambda: snapshot))

    with TestClient(app) as client:
        payload = client.get("/api/snapshot").json()

    assert payload["is_complete"] is False
    assert payload["pull_requests"][0]["check_evidence_state"] == "incomplete"
    assert payload["source_errors"] == [
        {
            "repository": "Rule-0-Softworks/denied",
            "pull_request_number": 42,
            "stage": "pull_requests",
            "message": "access denied",
            "graphql_path": ["repository", "pullRequests"],
            "graphql_locations": [[12, 9]],
        }
    ]


def test_route_inventory_has_no_github_write_surface(snapshot_factory) -> None:
    snapshot = snapshot_factory()
    app = create_app(Settings("secret"), SnapshotStore(lambda: snapshot))
    documentation = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    inventory = {
        (route.path, method)
        for route in app.routes
        if isinstance(route, Route) and route.path not in documentation
        for method in (getattr(route, "methods", None) or set())
    }
    assert {path for path, method in inventory if method == "POST"} == {"/refresh"}
    assert not ({"PUT", "PATCH", "DELETE"} & {method for _, method in inventory})
