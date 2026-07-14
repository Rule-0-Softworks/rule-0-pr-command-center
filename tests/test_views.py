from r0s_pr_command_center.views import DashboardFilter, count_facets, filter_prs, render_dashboard


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
