from datetime import UTC, datetime

import pytest
from r0s_pr_read_model.models import (
    CheckContext,
    CheckState,
    DashboardSnapshot,
    Diagnostic,
    PullRequest,
    RequiredCheckState,
    SourceError,
)


@pytest.fixture
def snapshot_factory():
    def make(
        *,
        repository_count: int = 1,
        states: tuple[str, ...] = ("failing",),
        title: str = "Example PR",
        with_source_error: bool = False,
    ) -> DashboardSnapshot:
        pull_requests = tuple(
            PullRequest(
                repository="Rule-0-Softworks/example",
                number=index + 1,
                title=title,
                url=f"https://github.com/Rule-0-Softworks/example/pull/{index + 1}",
                author="dependabot" if index == 0 else "developer",
                is_draft=False,
                base_ref_name="main",
                head_ref_name=f"feature/{index + 1}",
                head_sha=f"{index + 1:040x}",
                review_decision=None,
                mergeable="MERGEABLE",
                merge_state_status="BLOCKED" if state == "failing" else "CLEAN",
                contexts=(
                    CheckContext(
                        "CheckRun",
                        "quality",
                        "COMPLETED",
                        "FAILURE" if state == "failing" else "SUCCESS",
                        None,
                        None,
                        {},
                    ),
                ),
                all_context_state=CheckState(state),
                required_check_state=RequiredCheckState.UNKNOWN,
                merge_blocked=state == "failing",
                diagnostics=(Diagnostic(f"checks.{state}", f"classified as {state}", "test"),),
            )
            for index, state in enumerate(states)
        )
        errors = (
            (SourceError("Rule-0-Softworks/denied", "pull_requests", "access denied"),)
            if with_source_error
            else ()
        )
        return DashboardSnapshot(
            "Rule-0-Softworks",
            datetime(2026, 7, 14, tzinfo=UTC),
            repository_count,
            pull_requests,
            errors,
        )

    return make
