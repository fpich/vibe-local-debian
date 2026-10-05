from __future__ import annotations

import os
from pathlib import Path
import runpy
import subprocess

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ci/inject-sentry-dsn.sh"
_PYTHON_TARGET = Path("vibe/observability/sentry.py")
_CLI_DSN = "http://cli@127.0.0.1:9/42"
_ACP_DSN = "http://acp@127.0.0.1:9/43"


@pytest.fixture
def release_tree(tmp_path: Path) -> Path:
    python_target = tmp_path / _PYTHON_TARGET
    python_target.parent.mkdir(parents=True)
    python_target.write_text("_CLI_SENTRY_DSN = None\n_ACP_SENTRY_DSN = None\n")
    return tmp_path


def _inject(
    root: Path, cli: str = "", acp: str = "", *, required: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=root,
        env={
            **os.environ,
            "CLI_SENTRY_DSN": cli,
            "ACP_SENTRY_DSN": acp,
            "REQUIRE_SENTRY_DSN": str(required).lower(),
        },
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_release_injects_dsns_into_python(release_tree: Path) -> None:
    result = _inject(release_tree, _CLI_DSN, _ACP_DSN, required=True)

    assert result.returncode == 0, result.stderr
    python_values = runpy.run_path(str(release_tree / _PYTHON_TARGET))
    assert python_values["_CLI_SENTRY_DSN"] == _CLI_DSN
    assert python_values["_ACP_SENTRY_DSN"] == _ACP_DSN

    assert not list(release_tree.rglob("*.bak"))


def test_optional_missing_dsns_leave_sources_unchanged(release_tree: Path) -> None:
    result = _inject(release_tree)

    assert result.returncode == 0, result.stderr
    python_values = runpy.run_path(str(release_tree / _PYTHON_TARGET))
    assert python_values["_CLI_SENTRY_DSN"] is None
    assert python_values["_ACP_SENTRY_DSN"] is None


@pytest.mark.parametrize("cli,acp", [("", _ACP_DSN), (_CLI_DSN, "")])
def test_release_requires_both_dsns(release_tree: Path, cli: str, acp: str) -> None:
    result = _inject(release_tree, cli, acp, required=True)

    assert result.returncode != 0
    assert "is required but its value is not set" in result.stderr
