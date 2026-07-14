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
    ):
        assert required in text
