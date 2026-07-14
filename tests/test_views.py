from r0s_pr_command_center.views import (
    DashboardFilter,
    count_facets,
    filter_prs,
    render_dashboard,
    render_pr_detail,
)


def test_filters_and_counts_use_the_same_snapshot(snapshot_factory) -> None:
    snapshot = snapshot_factory(states=("failing", "passing", "no_checks"))
    assert count_facets(snapshot)["checks"]["failing"] == 1
    assert count_facets(snapshot)["checks"]["passing"] == 1
    assert count_facets(snapshot)["checks"]["no_checks"] == 1
    assert count_facets(snapshot)["checks"]["pending"] == 0
    filtered = filter_prs(snapshot, DashboardFilter(check_state="failing"))
    assert [item.all_context_state.value for item in filtered] == ["failing"]


def test_dashboard_escapes_titles_and_exposes_expandable_diagnostics(snapshot_factory) -> None:
    snapshot = snapshot_factory(title='<script>alert("x")</script>', with_source_error=True)
    html = render_dashboard(snapshot, DashboardFilter())
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<details" in html
    assert "Completeness warning" in html


def test_pr_detail_labels_all_and_required_checks_separately(snapshot_factory) -> None:
    pr = snapshot_factory().pull_requests[0]

    html = render_pr_detail(pr)

    assert "All checks" in html
    assert "Required checks" in html
    assert html.index("All checks") < html.index("Required checks")


def test_dashboard_includes_post_refresh_control(snapshot_factory) -> None:
    html = render_dashboard(snapshot_factory(), DashboardFilter())

    assert "<form method='post' action='/refresh'>" in html
    assert "Refresh snapshot" in html


def test_pr_detail_shows_head_sha(snapshot_factory) -> None:
    pr = snapshot_factory().pull_requests[0]

    html = render_pr_detail(pr)

    assert "Head SHA" in html
    assert pr.head_sha in html
