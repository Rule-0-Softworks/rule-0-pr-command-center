from dataclasses import replace

from r0s_pr_read_model.models import CheckState, RequiredCheckState
from r0s_pr_command_center.views import (
    DashboardFilter,
    count_facets,
    filter_prs,
    order_for_triage,
    render_dashboard,
    render_pr_detail,
    triage_bucket_counts,
)


def test_filters_and_counts_use_the_same_snapshot(snapshot_factory) -> None:
    snapshot = snapshot_factory(states=("failing", "passing", "no_checks"))
    assert count_facets(snapshot)["checks"]["failing"] == 1
    assert count_facets(snapshot)["checks"]["passing"] == 1
    assert count_facets(snapshot)["checks"]["no_checks"] == 1
    assert count_facets(snapshot)["checks"]["pending"] == 0
    filtered = filter_prs(snapshot, DashboardFilter(check_state="failing"))
    assert [item.all_context_state.value for item in filtered] == ["failing"]


def test_triage_order_prioritizes_attention_and_keeps_ties_stable(snapshot_factory) -> None:
    snapshot = snapshot_factory(states=("passing",) * 7)
    passing, failing, unknown, blocked, review, pending, same_tier = snapshot.pull_requests
    passing = replace(passing, required_check_state=RequiredCheckState.PASSING)
    blocked = replace(blocked, required_check_state=RequiredCheckState.PASSING)
    review = replace(review, required_check_state=RequiredCheckState.PASSING)
    pending = replace(pending, required_check_state=RequiredCheckState.PASSING)
    same_tier = replace(same_tier, required_check_state=RequiredCheckState.PASSING)

    ordered = order_for_triage(
        (
            passing,
            replace(
                failing,
                all_context_state=CheckState.FAILING,
                required_check_state=RequiredCheckState.PASSING,
            ),
            replace(unknown, required_check_state=RequiredCheckState.UNKNOWN),
            replace(blocked, merge_blocked=True),
            replace(review, review_decision="REVIEW_REQUIRED"),
            replace(pending, all_context_state=CheckState.PENDING),
            same_tier,
        )
    )

    assert [pr.number for pr in ordered] == [2, 3, 4, 5, 6, 1, 7]


def test_triage_bucket_counts_choose_the_highest_priority_state(snapshot_factory) -> None:
    snapshot = snapshot_factory(states=("passing",) * 3)
    passing, unknown, failing = snapshot.pull_requests
    configured = replace(
        snapshot,
        pull_requests=(
            replace(passing, required_check_state=RequiredCheckState.PASSING),
            replace(unknown, required_check_state=RequiredCheckState.UNKNOWN),
            replace(
                failing,
                all_context_state=CheckState.FAILING,
                required_check_state=RequiredCheckState.PASSING,
                merge_blocked=True,
            ),
        ),
    )

    assert triage_bucket_counts(configured) == {
        "failing": 1,
        "unknown_required": 1,
        "merge_blocked": 0,
        "review_required": 0,
        "pending": 0,
        "remaining": 1,
    }


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
