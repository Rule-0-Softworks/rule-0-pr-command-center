from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphQLIssue:
    message: str
    path: tuple[str | int, ...] = ()
    locations: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class GraphQLResponse:
    data: dict[str, Any]
    errors: tuple[GraphQLIssue, ...] = ()


class GitHubClient:
    def __init__(self, token: str, *, opener: Callable[..., Any] = urllib.request.urlopen) -> None:
        self._token = token
        self._opener = opener

    def _json(self, request: urllib.request.Request) -> Any:
        try:
            with self._opener(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise GitHubError(
                f"GitHub HTTP {error.code} for {self._redact(request.full_url)}"
            ) from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            url = self._redact(request.full_url)
            raise GitHubError(f"GitHub request failed for {url}: {type(error).__name__}") from error

    def graphql(self, query: str, variables: Mapping[str, object]) -> GraphQLResponse:
        body = json.dumps({"query": query, "variables": dict(variables)}).encode()
        request = urllib.request.Request(
            "https://api.github.com/graphql",
            data=body,
            headers=self._headers("application/json"),
            method="POST",
        )
        result = self._json(request)
        issues = tuple(
            self._graphql_issue(item)
            for item in result.get("errors", ())
            if isinstance(item, Mapping)
        )
        return GraphQLResponse(dict(result.get("data") or {}), issues)

    def rest_json(self, path: str) -> Any:
        request = urllib.request.Request(
            f"https://api.github.com{path}",
            headers=self._headers("application/vnd.github+json"),
        )
        return self._json(request)

    def _headers(self, accept: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": accept,
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "r0s-pr-command-center/0.1",
        }

    def _redact(self, message: str) -> str:
        return message.replace(self._token, "[REDACTED]")

    def _graphql_issue(self, item: Mapping[str, object]) -> GraphQLIssue:
        path = item.get("path")
        locations = item.get("locations")
        parsed_path: tuple[str | int, ...] = ()
        if isinstance(path, list) and all(
            type(value) is str or type(value) is int for value in path
        ):
            parsed_path = cast(tuple[str | int, ...], tuple(path))

        parsed_locations: list[tuple[int, int]] = []
        if isinstance(locations, list):
            for location in locations:
                if not isinstance(location, Mapping):
                    continue
                location_data = cast(Mapping[str, object], location)
                line = location_data.get("line")
                column = location_data.get("column")
                if type(line) is int and type(column) is int:
                    parsed_locations.append((line, column))

        return GraphQLIssue(
            message=self._redact(str(item.get("message", "GraphQL error"))),
            path=parsed_path,
            locations=tuple(parsed_locations),
        )
