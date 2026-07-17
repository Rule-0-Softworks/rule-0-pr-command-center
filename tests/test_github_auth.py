from __future__ import annotations

import base64
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from email.message import Message
from pathlib import Path
from time import sleep
from types import TracebackType
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from r0s_pr_command_center.github_auth import (
    INSTALLATION_PERMISSIONS,
    GitHubAppTokenProvider,
    GitHubAuthError,
    StaticTokenProvider,
    create_token_provider,
)
from r0s_pr_command_center.settings import GitHubAuthMode, Settings


class Response(io.BytesIO):
    def __enter__(self) -> Response:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
FIXED_NOW = datetime(2026, 7, 17, 17, 0, tzinfo=UTC)


def success_body(expires_at: datetime = FIXED_NOW + timedelta(hours=1)) -> bytes:
    return json.dumps(
        {
            "token": "installation-secret",
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "permissions": {
                "administration": "read",
                "checks": "read",
                "contents": "read",
                "metadata": "read",
                "pull_requests": "read",
            },
        }
    ).encode()


def test_app_provider_requests_and_caches_installation_token(tmp_path: Path) -> None:
    key_path = tmp_path / "app.pem"
    key_path.write_bytes(TEST_PRIVATE_KEY)
    calls: list[Request] = []

    def opener(request: Request, timeout: float) -> Response:
        calls.append(request)
        return Response(success_body())

    provider = GitHubAppTokenProvider(
        "Iv1.example", 123, key_path, opener=opener, now=lambda: FIXED_NOW
    )

    assert provider() == "installation-secret"
    assert provider() == "installation-secret"
    assert len(calls) == 1
    assert calls[0].full_url.endswith("/app/installations/123/access_tokens")
    assert calls[0].headers["Authorization"].startswith("Bearer ")
    assert isinstance(calls[0].data, bytes)
    assert json.loads(calls[0].data) == {
        "permissions": {
            "administration": "read",
            "checks": "read",
            "contents": "read",
            "metadata": "read",
            "pull_requests": "read",
        }
    }
    assert "installation-secret" not in repr(provider)


def test_app_provider_refreshes_near_expiry_token(tmp_path: Path) -> None:
    key_path = tmp_path / "app.pem"
    key_path.write_bytes(TEST_PRIVATE_KEY)
    calls = 0

    def opener(request: Request, timeout: float) -> Response:
        nonlocal calls
        calls += 1
        return Response(success_body(FIXED_NOW + timedelta(minutes=6 - calls)))

    provider = GitHubAppTokenProvider(
        "Iv1.example", 123, key_path, opener=opener, now=lambda: FIXED_NOW
    )

    assert provider() == "installation-secret"
    assert provider() == "installation-secret"
    assert calls == 2


def test_app_provider_serializes_concurrent_refreshes(tmp_path: Path) -> None:
    key_path = tmp_path / "app.pem"
    key_path.write_bytes(TEST_PRIVATE_KEY)
    calls = 0
    calls_lock = threading.Lock()

    def opener(request: Request, timeout: float) -> Response:
        nonlocal calls
        with calls_lock:
            calls += 1
        sleep(0.02)
        return Response(success_body())

    provider = GitHubAppTokenProvider(
        "Iv1.example", 123, key_path, opener=opener, now=lambda: FIXED_NOW
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: provider(), range(2)))

    assert results == ["installation-secret", "installation-secret"]
    assert calls == 1


def test_app_provider_jwt_claims_use_rs256_and_short_expiry(tmp_path: Path) -> None:
    key_path = tmp_path / "app.pem"
    key_path.write_bytes(TEST_PRIVATE_KEY)
    captured: list[Request] = []

    def opener(request: Request, timeout: float) -> Response:
        captured.append(request)
        return Response(success_body())

    GitHubAppTokenProvider("Iv1.example", 123, key_path, opener=opener, now=lambda: FIXED_NOW)()
    encoded = captured[0].headers["Authorization"].removeprefix("Bearer ")
    header = jwt.get_unverified_header(encoded)
    claims = jwt.decode(encoded, options={"verify_signature": False})

    assert header["alg"] == "RS256"
    assert claims["iss"] == "Iv1.example"
    assert claims["iat"] <= int((FIXED_NOW - timedelta(seconds=60)).timestamp())
    assert claims["exp"] <= int((FIXED_NOW + timedelta(minutes=10)).timestamp())


@pytest.mark.parametrize(
    "response_body",
    [
        {"access_token": "installation-secret"},
        {"token": " ", "expires_at": "2026-07-17T18:00:00Z", "permissions": {}},
        {
            "token": "installation-secret",
            "expires_at": "not-a-date",
            "permissions": {},
        },
        {
            "token": "installation-secret",
            "expires_at": "2026-07-17T18:00:00Z",
            "permissions": {"contents": "write"},
        },
    ],
)
def test_app_provider_rejects_malformed_or_write_capable_responses(
    tmp_path: Path, response_body: dict[str, object]
) -> None:
    key_path = tmp_path / "app.pem"
    key_path.write_bytes(TEST_PRIVATE_KEY)

    def opener(request: Request, timeout: float) -> Response:
        return Response(json.dumps(response_body).encode())

    provider = GitHubAppTokenProvider(
        "Iv1.example", 123, key_path, opener=opener, now=lambda: FIXED_NOW
    )
    with pytest.raises(GitHubAuthError) as raised:
        provider()

    assert "installation-secret" not in str(raised.value)
    assert base64.b64encode(TEST_PRIVATE_KEY).decode() not in str(raised.value)


@pytest.mark.parametrize(
    "response_body",
    [
        [],
        {"token": "installation-secret", "expires_at": "2026-07-17T18:00:00Z"},
        {
            "token": "installation-secret",
            "expires_at": "2026-07-17T18:00:00",
            "permissions": INSTALLATION_PERMISSIONS,
        },
    ],
)
def test_app_provider_rejects_invalid_response_shapes(
    tmp_path: Path, response_body: object
) -> None:
    key_path = tmp_path / "app.pem"
    key_path.write_bytes(TEST_PRIVATE_KEY)

    def opener(request: Request, timeout: float) -> Response:
        return Response(json.dumps(response_body).encode())

    with pytest.raises(GitHubAuthError):
        GitHubAppTokenProvider("Iv1.example", 123, key_path, opener=opener, now=lambda: FIXED_NOW)()


def test_app_provider_redacts_transport_failures(tmp_path: Path) -> None:
    key_path = tmp_path / "app.pem"
    key_path.write_bytes(TEST_PRIVATE_KEY)

    def opener(request: Request, timeout: float) -> Response:
        raise HTTPError(request.full_url, 403, "Forbidden", Message(), io.BytesIO(b"denied"))

    with pytest.raises(GitHubAuthError) as raised:
        GitHubAppTokenProvider("Iv1.example", 123, key_path, opener=opener, now=lambda: FIXED_NOW)()

    assert "Iv1.example" not in str(raised.value)


@pytest.mark.parametrize("token", [None, "", "   "])
def test_token_provider_rejects_blank_tokens_without_exposing_secret(token: str | None) -> None:
    with pytest.raises(GitHubAuthError) as raised:
        create_token_provider(Settings(github_token=token))

    assert not token or token not in str(raised.value)


def test_token_provider_factory_supports_static_token() -> None:
    provider = create_token_provider(Settings(github_token="fine-grained-secret"))

    assert isinstance(provider, StaticTokenProvider)
    assert provider() == "fine-grained-secret"


def test_token_provider_factory_requires_complete_app_settings() -> None:
    settings = Settings(github_auth_mode=GitHubAuthMode.APP)

    with pytest.raises(GitHubAuthError, match="GitHub App"):
        create_token_provider(settings)


def test_token_provider_factory_builds_complete_app_provider(tmp_path: Path) -> None:
    provider = create_token_provider(
        Settings(
            github_auth_mode=GitHubAuthMode.APP,
            github_app_client_id="Iv1.example",
            github_app_installation_id=123,
            github_app_private_key_path=tmp_path / "app.pem",
        )
    )

    assert isinstance(provider, GitHubAppTokenProvider)


def test_token_provider_factory_rejects_unsupported_mode() -> None:
    settings = Settings(github_auth_mode=cast(GitHubAuthMode, "unsupported"))

    with pytest.raises(GitHubAuthError, match="Unsupported"):
        create_token_provider(settings)
