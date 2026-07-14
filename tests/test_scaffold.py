from importlib import import_module


def test_workspace_packages_are_importable() -> None:
    assert import_module("r0s_pr_command_center") is not None
    assert import_module("r0s_pr_read_model") is not None
