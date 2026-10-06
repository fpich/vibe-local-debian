from __future__ import annotations

from pathlib import Path

import pytest

from vibe.core.config import harness_files
from vibe.utils.paths import GlobalPath


@pytest.fixture(autouse=True)
def _harness_files_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "vibe-home"
    monkeypatch.setattr(
        "vibe.core.paths._vibe_home.VIBE_HOME", GlobalPath(lambda: home)
    )
    harness_files.init_harness_files_manager("user", "project")
    yield
    harness_files.reset_harness_files_manager()
