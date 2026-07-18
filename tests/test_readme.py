from pathlib import Path


def test_readme_documents_security_semantics_and_commands() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    for required in (
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "uv run serve",
        "127.0.0.1:8000",
        "All returned checks",
        "Required checks",
        "unknown",
        "read-only",
        "fine-grained",
        "GitHub App",
        "unavailable",
        "classic PATs are not supported",
        "R0S_GITHUB_AUTH_MODE",
        "R0S_GITHUB_APP_CLIENT_ID",
        "R0S_GITHUB_APP_INSTALLATION_ID",
        "R0S_GITHUB_APP_PRIVATE_KEY_PATH",
        "PyJWT[crypto]",
    ):
        assert required in text


def test_readme_badges_target_the_repository_owner() -> None:
    text = Path("README.md").read_text(encoding="utf-8")

    assert "https://github.com/Rule-0-Softworks/rule-0-pr-command-center" in text
    assert "https://codecov.io/gh/Rule-0-Softworks/rule-0-pr-command-center" in text
    assert "Rule0Softworks/rule-0-pr-command-center" not in text
