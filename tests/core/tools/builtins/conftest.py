from __future__ import annotations

from pathlib import Path

import pytest

from vibe.utils import paths


@pytest.fixture()
def on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "is_windows", lambda: True)


@pytest.fixture()
def tmp_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path
