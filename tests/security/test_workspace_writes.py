from pathlib import Path

import pytest

from dubai_planner.system_safety import WORKSPACE_ROOT, workspace_write_path


def test_workspace_write_path_accepts_workspace_target():
    target = WORKSPACE_ROOT / "runtime" / "safe.sqlite"
    assert workspace_write_path(target) == target.resolve(strict=False)


@pytest.mark.parametrize(
    "target",
    [
        Path.home() / "outside-project.sqlite",
        WORKSPACE_ROOT / ".." / "outside-project.sqlite",
        Path("C:/Windows/System32/outside-project.sqlite"),
    ],
)
def test_workspace_write_path_rejects_external_and_parent_escape(target, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with pytest.raises(ValueError, match="inside the project workspace"):
        workspace_write_path(target)


def test_workspace_write_path_rejects_symlink_escape(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    link = WORKSPACE_ROOT / ".tmp" / "outside-link"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(Path.home(), target_is_directory=True)
    except OSError:
        pytest.skip("Creating a Windows symlink is not available to this user")
    try:
        with pytest.raises(ValueError, match="inside the project workspace"):
            workspace_write_path(link / "escape.sqlite")
    finally:
        link.unlink(missing_ok=True)
