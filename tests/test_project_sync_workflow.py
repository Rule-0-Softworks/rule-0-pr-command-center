from pathlib import Path


def test_manual_project_sync_workflow_discovers_and_deduplicates_open_pull_requests() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "sync-open-prs.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert 'schedule:\n    - cron: "45 * * * *"' in workflow
    assert '"/orgs/${owner}/repos?type=all&per_page=100"' in workflow
    assert "select(.archived == false)" in workflow
    assert '"/repos/${owner}/${repository}/pulls?state=open&per_page=100"' in workflow
    assert "projectV2(number: $projectNumber)" in workflow
    assert "items(first: 100, after: $endCursor)" in workflow
    assert "addProjectV2ItemById" in workflow
    assert 'project_pull_request_ids["${pull_request_id}"]' in workflow


def test_manual_project_sync_workflow_logs_only_safe_aggregate_totals() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "sync-open-prs.yml").read_text(encoding="utf-8")

    assert 'echo "Repositories checked: ${#repositories[@]}"' in workflow
    assert 'echo "Open PRs found: ${open_prs}"' in workflow
    assert 'echo "Existing Project items checked: ${existing_project_items}"' in workflow
    assert 'echo "New items added: ${new_items_added}"' in workflow
    assert 'echo "${repository}"' not in workflow
    assert 'echo "${pull_request_id}"' not in workflow
