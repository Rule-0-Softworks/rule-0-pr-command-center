from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class GitHubAuthMode(StrEnum):
    TOKEN = "token"
    APP = "app"


@dataclass(frozen=True)
class Settings:
    github_token: str | None = field(default=None, repr=False)
    github_auth_mode: GitHubAuthMode = GitHubAuthMode.TOKEN
    github_app_client_id: str | None = None
    github_app_installation_id: int | None = None
    github_app_private_key_path: Path | None = field(default=None, repr=False)
    organization: str = "Rule-0-Softworks"

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> Settings:
        raw_mode = environ.get("R0S_GITHUB_AUTH_MODE", GitHubAuthMode.TOKEN)
        try:
            mode = GitHubAuthMode(raw_mode)
        except ValueError as error:
            raise RuntimeError("R0S_GITHUB_AUTH_MODE must be token or app") from error

        organization = environ.get("R0S_GITHUB_ORG", "Rule-0-Softworks")
        if mode is GitHubAuthMode.TOKEN:
            token = environ.get("GITHUB_TOKEN") or environ.get("GH_TOKEN")
            if not token:
                raise RuntimeError("Set human-managed GITHUB_TOKEN or GH_TOKEN before startup")
            return cls(github_token=token, organization=organization)

        client_id = environ.get("R0S_GITHUB_APP_CLIENT_ID", "").strip()
        installation_id = environ.get("R0S_GITHUB_APP_INSTALLATION_ID", "").strip()
        private_key_path = environ.get("R0S_GITHUB_APP_PRIVATE_KEY_PATH", "").strip()
        if not client_id or not installation_id or not private_key_path:
            raise RuntimeError(
                "GitHub App mode requires R0S_GITHUB_APP_CLIENT_ID, "
                "R0S_GITHUB_APP_INSTALLATION_ID, and R0S_GITHUB_APP_PRIVATE_KEY_PATH"
            )
        try:
            parsed_installation_id = int(installation_id)
        except ValueError as error:
            raise RuntimeError("GitHub App mode requires an integer installation ID") from error
        return cls(
            github_auth_mode=mode,
            github_app_client_id=client_id,
            github_app_installation_id=parsed_installation_id,
            github_app_private_key_path=Path(private_key_path),
            organization=organization,
        )
