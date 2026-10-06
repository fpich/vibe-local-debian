from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TOOLS = {
    "bash",
    "read_file",
    "write_file",
    "edit",
    "grep",
    "ask_user_question",
    "todo",
}


def test_local_profile_exposes_only_coding_tools() -> None:
    config = tomllib.loads((REPO_ROOT / ".vibe/config.toml").read_text())

    assert set(config["enabled_tools"]) == EXPECTED_TOOLS
    assert "web_fetch" not in config["enabled_tools"]
    assert "web_search" not in config["enabled_tools"]
    assert "task" not in config["enabled_tools"]
    assert config.get("enable_connectors", False) is False


def test_model_allowlist_source_has_no_allow_all_fallback() -> None:
    source = (REPO_ROOT / "vibe/core/config/vibe_schema.py").read_text()
    start = source.index("    def available_models(self)")
    end = source.index("\n    def get_active_model(self)", start)
    method = source[start:end]

    assert "return allowed or self.models" not in method
    assert "return allowed" in method


def test_installer_verifies_pinned_uv_installer() -> None:
    source = (REPO_ROOT / "install.sh").read_text()

    assert 'UV_INSTALLER_VERSION="0.11.26"' in source
    assert (
        'UV_INSTALLER_SHA256="92fa9085d24c214bb4445cc1da8c15ca9cca8cffb34726240fa08c5302e94ccc"'
        in source
    )
    assert "https://astral.sh/uv/${UV_INSTALLER_VERSION}/install.sh" in source
    assert "actual_sha256" in source
    assert "| bash" not in source


def test_uninstaller_refuses_home_directory(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["VIBE_HOME"] = str(tmp_path)

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "uninstall.sh")],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 4
    assert "suppression refusée" in result.stderr
    assert tmp_path.exists()


def test_uninstaller_can_cancel_safe_home(tmp_path: Path) -> None:
    vibe_home = tmp_path / ".vibe"
    vibe_home.mkdir()
    marker = vibe_home / "keep-me"
    marker.write_text("present")

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["VIBE_HOME"] = str(vibe_home)

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "uninstall.sh")],
        env=env,
        input="non\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Annulé." in result.stdout
    assert marker.read_text() == "present"
