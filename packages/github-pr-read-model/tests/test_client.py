import io
import urllib.error
from email.message import Message
from types import TracebackType
from urllib.request import Request

import pytest
from r0s_pr_read_model.client import GitHubClient, GitHubError


class Response(io.BytesIO):
    def __enter__(self) -> "Response":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


def test_graphql_sends_auth_without_returning_token() -> None:
    seen: dict[str, str] = {}

    def opener(request: Request, timeout: float) -> Response:
        seen["authorization"] = request.headers["Authorization"]
        return Response(b'{"data":{"organization":{"login":"Rule-0-Softworks"}}}')

    result = GitHubClient("secret-value", opener=opener).graphql("query { viewer { login } }", {})
    assert result.data["organization"]["login"] == "Rule-0-Softworks"
    assert seen["authorization"] == "Bearer secret-value"
    assert "secret-value" not in repr(result)


def test_client_resolves_callable_token_once_per_request() -> None:
    calls = 0

    def token() -> str:
        nonlocal calls
        calls += 1
        return "rotating-secret"

    def opener(request: Request, timeout: float) -> Response:
        return Response(b'{"data":{"viewer":{"login":"operator"}}}')

    result = GitHubClient(token, opener=opener).graphql("query { viewer { login } }", {})

    assert result.data["viewer"]["login"] == "operator"
    assert calls == 1


def test_http_error_never_contains_token() -> None:
    def opener(request: Request, timeout: float) -> Response:
        raise urllib.error.HTTPError(
            request.full_url, 403, "Forbidden", Message(), io.BytesIO(b"denied")
        )

    with pytest.raises(GitHubError) as raised:
        GitHubClient("secret-value", opener=opener).graphql("query X { viewer { login } }", {})
    assert "secret-value" not in str(raised.value)


def test_callable_token_is_redacted_from_errors() -> None:
    def opener(request: Request, timeout: float) -> Response:
        raise urllib.error.HTTPError(
            request.full_url, 403, "rotating-secret rejected", Message(), io.BytesIO(b"denied")
        )

    with pytest.raises(GitHubError) as raised:
        GitHubClient(lambda: "rotating-secret", opener=opener).graphql(
            "query X { viewer { login } }", {}
        )

    assert "rotating-secret" not in str(raised.value)


def test_graphql_partial_data_preserves_redacted_issue_metadata() -> None:
    def opener(request: Request, timeout: float) -> Response:
        return Response(
            b'{"data":{"repository":{"name":"example"}},"errors":[{'
            b'"message":"secret-value denied",'
            b'"path":["repository","pullRequests","nodes",0,"commits"],'
            b'"locations":[{"line":12,"column":9}]}]}'
        )

    result = GitHubClient("secret-value", opener=opener).graphql("query X { viewer { login } }", {})

    assert result.data["repository"]["name"] == "example"
    assert result.errors[0].message == "[REDACTED] denied"
    assert result.errors[0].path == ("repository", "pullRequests", "nodes", 0, "commits")
    assert result.errors[0].locations == ((12, 9),)


def test_graphql_issue_discards_boolean_location_coordinates() -> None:
    def opener(request: Request, timeout: float) -> Response:
        return Response(
            b'{"data":{},"errors":[{"message":"denied","locations":['
            b'{"line":true,"column":9},{"line":12,"column":false},{"line":4,"column":2}]}]}'
        )

    result = GitHubClient("secret-value", opener=opener).graphql("query X { viewer { login } }", {})

    assert result.errors[0].locations == ((4, 2),)


def test_graphql_issue_discards_path_with_boolean_segment() -> None:
    def opener(request: Request, timeout: float) -> Response:
        return Response(
            b'{"data":{},"errors":[{"message":"denied","path":["repository",true,"pullRequests"]}]}'
        )

    result = GitHubClient("secret-value", opener=opener).graphql("query X { viewer { login } }", {})

    assert result.errors[0].path == ()
