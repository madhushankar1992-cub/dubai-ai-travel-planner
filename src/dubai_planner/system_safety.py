"""Hard boundary for every first-party filesystem write."""

import os
import tempfile
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def workspace_write_path(path: Path | str, *, purpose: str = "write") -> Path:
    """Resolve a write target and reject escapes from the repository.

    Pytest's own per-test temporary directories are allowed only while pytest is
    actively running. Application and CLI writes remain workspace-confined.
    """
    candidate = Path(path).expanduser().resolve(strict=False)
    root = WORKSPACE_ROOT.resolve(strict=True)
    if candidate != root and candidate.is_relative_to(root):
        return candidate

    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    pytest_active = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    pytest_temp = candidate.is_relative_to(temp_root) and any(
        part.casefold().startswith(("pytest-", "pytest-of-")) for part in candidate.parts
    )
    if pytest_active and pytest_temp:
        return candidate
    raise ValueError(f"{purpose} path must stay inside the project workspace")
