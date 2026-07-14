import json
from pathlib import Path


def test_probe_fixture_preserves_context_identity_and_merge_queue() -> None:
    rules = json.loads((Path(__file__).parent / "fixtures/effective_rules.json").read_text())
    required = next(rule for rule in rules if rule["type"] == "required_status_checks")
    check = required["parameters"]["required_status_checks"][0]
    assert check == {"context": "Quality Gate", "integration_id": 15368}
    assert any(rule["type"] == "merge_queue" for rule in rules)
