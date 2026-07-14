import tomllib
from importlib import import_module
from pathlib import Path

from fastapi import FastAPI


def test_workspace_packages_are_importable() -> None:
    assert import_module("r0s_pr_command_center") is not None
    assert import_module("r0s_pr_read_model") is not None


def test_serve_entry_point_exposes_a_fastapi_application() -> None:
    application_module = import_module("r0s_pr_command_center.app")

    assert isinstance(application_module.app, FastAPI)
    assert callable(application_module.run)


def test_workspace_metadata_matches_the_scaffold_contract() -> None:
    root = Path(__file__).parents[1]
    with (root / "pyproject.toml").open("rb") as file:
        workspace = tomllib.load(file)
    with (root / "packages" / "github-pr-read-model" / "pyproject.toml").open("rb") as file:
        read_model = tomllib.load(file)

    assert workspace["project"]["version"] == "0.1.0"
    assert workspace["project"]["description"] == (
        "Read-only command center for Rule-0-Softworks pull requests"
    )
    assert "readme" not in workspace["project"]
    assert "authors" not in workspace["project"]
    assert workspace["project"]["scripts"]["serve"] == "r0s_pr_command_center.app:run"
    assert workspace["tool"]["pytest"]["ini_options"] == {
        "testpaths": ["tests", "packages/github-pr-read-model/tests"],
        "addopts": "-ra --strict-config --strict-markers",
    }
    assert workspace["tool"]["ty"]["environment"]["root"] == [
        "./src",
        "./packages/github-pr-read-model/src",
    ]

    assert read_model["project"]["version"] == "0.1.0"
    assert read_model["project"]["description"] == "GitHub PR collection and classification model"
    assert read_model["project"]["dependencies"] == []
