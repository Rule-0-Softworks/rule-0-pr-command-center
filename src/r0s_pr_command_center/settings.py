from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    github_token: str = field(repr=False)
    organization: str = "Rule-0-Softworks"

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> Settings:
        token = environ.get("GITHUB_TOKEN") or environ.get("GH_TOKEN")
        if not token:
            raise RuntimeError("Set human-managed GITHUB_TOKEN or GH_TOKEN before startup")
        return cls(
            github_token=token,
            organization=environ.get("R0S_GITHUB_ORG", "Rule-0-Softworks"),
        )
