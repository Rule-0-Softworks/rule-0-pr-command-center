from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import jwt

from .settings import GitHubAuthMode, Settings

TokenOpener = Callable[..., Any]
TokenClock = Callable[[], datetime]
INSTALLATION_PERMISSIONS = {
    "administration": "read",
    "checks": "read",
    "contents": "read",
    "metadata": "read",
    "pull_requests": "read",
    "statuses": "read",
}


class GitHubAuthError(RuntimeError):
    """A secret-safe authentication failure."""


class TokenProvider(Protocol):
    def __call__(self) -> str: ...


@dataclass(frozen=True)
class StaticTokenProvider:
    token: str = field(repr=False)

    def __call__(self) -> str:
        return self.token


@dataclass(frozen=True)
class InstallationToken:
    value: str = field(repr=False)
    expires_at: datetime


class GitHubAppTokenProvider:
    def __init__(
        self,
        client_id: str,
        installation_id: int,
        private_key_path: Path,
        *,
        opener: TokenOpener = urllib.request.urlopen,
        now: TokenClock = lambda: datetime.now(UTC),
    ) -> None:
        self._client_id = client_id
        self._installation_id = installation_id
        self._private_key_path = private_key_path
        self._opener = opener
        self._now = now
        self._lock = threading.Lock()
        self._cached: InstallationToken | None = None

    def __repr__(self) -> str:
        return "GitHubAppTokenProvider()"

    def __call__(self) -> str:
        with self._lock:
            now = self._now()
            if self._cached is not None and self._cached.expires_at - now > timedelta(minutes=5):
                return self._cached.value
            self._cached = self._exchange(now)
            return self._cached.value

    def _exchange(self, now: datetime) -> InstallationToken:
        try:
            private_key = self._private_key_path.read_bytes()
            payload = {
                "iat": int((now - timedelta(seconds=60)).timestamp()),
                "exp": int((now + timedelta(minutes=9)).timestamp()),
                "iss": self._client_id,
            }
            app_jwt = jwt.encode(payload, private_key, algorithm="RS256")
            request = urllib.request.Request(
                f"https://api.github.com/app/installations/{self._installation_id}/access_tokens",
                data=json.dumps({"permissions": INSTALLATION_PERMISSIONS}).encode(),
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "r0s-pr-command-center/0.1",
                },
                method="POST",
            )
            with self._opener(request, timeout=60) as response:
                result = json.load(response)
            return self._parse_installation_token(result)
        except (OSError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            raise GitHubAuthError("GitHub App installation-token exchange failed") from None
        except (ValueError, TypeError, json.JSONDecodeError, jwt.PyJWTError):
            raise GitHubAuthError("GitHub App authentication response was invalid") from None

    @staticmethod
    def _parse_installation_token(result: object) -> InstallationToken:
        if not isinstance(result, Mapping):
            raise ValueError
        token = result.get("token")
        expires_at = result.get("expires_at")
        permissions = result.get("permissions")
        if not isinstance(token, str) or not token.strip():
            raise ValueError
        if not isinstance(expires_at, str) or not isinstance(permissions, Mapping):
            raise ValueError
        if any(value in {"write", "admin"} for value in permissions.values()):
            raise ValueError
        if any(permissions.get(name) != level for name, level in INSTALLATION_PERMISSIONS.items()):
            raise ValueError
        parsed_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if parsed_expiry.tzinfo is None:
            raise ValueError
        return InstallationToken(token, parsed_expiry.astimezone(UTC))


def create_token_provider(settings: Settings) -> TokenProvider:
    if settings.github_auth_mode is GitHubAuthMode.TOKEN:
        if not settings.github_token or not settings.github_token.strip():
            raise GitHubAuthError("A nonblank GitHub token is required in token mode")
        return StaticTokenProvider(settings.github_token)
    if settings.github_auth_mode is GitHubAuthMode.APP:
        if (
            not settings.github_app_client_id
            or settings.github_app_installation_id is None
            or settings.github_app_private_key_path is None
        ):
            raise GitHubAuthError("GitHub App mode requires complete configuration")
        return GitHubAppTokenProvider(
            settings.github_app_client_id,
            settings.github_app_installation_id,
            settings.github_app_private_key_path,
        )
    raise GitHubAuthError("Unsupported GitHub authentication mode")
