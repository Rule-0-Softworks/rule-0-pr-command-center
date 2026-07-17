from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType


class CheckState(StrEnum):
    PASSING = "passing"
    FAILING = "failing"
    PENDING = "pending"
    NO_CHECKS = "no_checks"
    UNCLASSIFIED = "unclassified"
    UNKNOWN = "unknown"


class CheckEvidenceState(StrEnum):
    NO_ROLLUP = "no_rollup"
    EMPTY_ROLLUP = "empty_rollup"
    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"
    INCOMPLETE = "incomplete"


class RequiredCheckState(StrEnum):
    PASSING = "passing"
    FAILING = "failing"
    PENDING = "pending"
    UNKNOWN = "unknown"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    source: str


@dataclass(frozen=True)
class CheckContext:
    kind: str
    name: str
    status: str | None
    conclusion: str | None
    url: str | None
    app_database_id: int | None
    raw: Mapping[str, object] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", MappingProxyType(dict(self.raw)))


@dataclass(frozen=True)
class CheckEvidence:
    state: CheckEvidenceState
    contexts: tuple[CheckContext, ...]
    diagnostic: Diagnostic | None = None


@dataclass(frozen=True)
class RequiredCheck:
    context: str
    integration_id: int | None
    source: str


@dataclass(frozen=True)
class PullRequest:
    repository: str
    number: int
    title: str
    url: str
    author: str | None
    is_draft: bool
    base_ref_name: str
    head_ref_name: str
    head_sha: str
    review_decision: str | None
    mergeable: str
    merge_state_status: str
    contexts: tuple[CheckContext, ...]
    check_evidence_state: CheckEvidenceState = field(
        default=CheckEvidenceState.INCOMPLETE, kw_only=True
    )
    all_context_state: CheckState
    required_check_state: RequiredCheckState
    merge_blocked: bool
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class SourceError:
    repository: str | None
    stage: str
    message: str
    pull_request_number: int | None = None
    graphql_path: tuple[str | int, ...] = ()
    graphql_locations: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class DashboardSnapshot:
    organization: str
    queried_at: datetime
    repository_count: int
    pull_requests: tuple[PullRequest, ...]
    source_errors: tuple[SourceError, ...] = ()

    @property
    def is_complete(self) -> bool:
        return not self.source_errors
