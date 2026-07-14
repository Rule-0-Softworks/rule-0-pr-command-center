import pytest

from r0s_pr_command_center.settings import Settings


def test_github_token_takes_precedence_without_exposing_it() -> None:
    settings = Settings.from_environment(
        {
            "GITHUB_TOKEN": "primary",
            "GH_TOKEN": "fallback",
            "R0S_GITHUB_ORG": "Rule-0-Softworks",
        }
    )
    assert settings.github_token == "primary"
    assert settings.organization == "Rule-0-Softworks"
    assert "primary" not in repr(settings)


def test_missing_credential_fails_with_non_secret_guidance() -> None:
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN or GH_TOKEN"):
        Settings.from_environment({})
