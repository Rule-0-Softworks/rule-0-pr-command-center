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


def test_app_mode_reads_non_secret_identifiers_and_hides_key_path() -> None:
    from r0s_pr_command_center.settings import GitHubAuthMode

    settings = Settings.from_environment(
        {
            "R0S_GITHUB_AUTH_MODE": "app",
            "R0S_GITHUB_APP_CLIENT_ID": "Iv1.example",
            "R0S_GITHUB_APP_INSTALLATION_ID": "123",
            "R0S_GITHUB_APP_PRIVATE_KEY_PATH": "C:/secure/r0s-app.pem",
        }
    )

    assert settings.github_auth_mode is GitHubAuthMode.APP
    assert settings.github_app_installation_id == 123
    assert "C:/secure/r0s-app.pem" not in repr(settings)


@pytest.mark.parametrize(
    "missing",
    [
        "R0S_GITHUB_APP_CLIENT_ID",
        "R0S_GITHUB_APP_INSTALLATION_ID",
        "R0S_GITHUB_APP_PRIVATE_KEY_PATH",
    ],
)
def test_app_mode_requires_all_credentials(missing: str) -> None:
    environ = {
        "R0S_GITHUB_AUTH_MODE": "app",
        "R0S_GITHUB_APP_CLIENT_ID": "Iv1.example",
        "R0S_GITHUB_APP_INSTALLATION_ID": "123",
        "R0S_GITHUB_APP_PRIVATE_KEY_PATH": "C:/secure/r0s-app.pem",
    }
    del environ[missing]

    with pytest.raises(RuntimeError, match="GitHub App mode requires"):
        Settings.from_environment(environ)
