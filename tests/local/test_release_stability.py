from __future__ import annotations

import ast
from pathlib import Path
import re
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_release_version_is_consistent() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    package_source = (REPO_ROOT / "vibe/__init__.py").read_text()
    lock = (REPO_ROOT / "uv.lock").read_text()

    version = project["project"]["version"]
    assert version == "1.2.1"
    assert f'__version__ = "{version}"' in package_source
    assert f'name = "mistral-vibe"\nversion = "{version}"' in lock


def test_project_metadata_points_to_the_fork() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    urls = project["project"]["urls"]
    assert all("fpich/vibe-local-debian" in value for value in urls.values())
    assert project["project"]["description"].startswith("Local-first")


def test_installer_always_installs_local_checkout() -> None:
    source = (REPO_ROOT / "install.sh").read_text()
    assert 'uv tool install --force "$SCRIPT_DIR"' in source
    assert "uv tool upgrade mistral-vibe" not in source


def test_documentation_does_not_advertise_removed_surfaces() -> None:
    active_docs = "\n".join(
        path.read_text(errors="ignore")
        for path in (
            REPO_ROOT / "README.md",
            REPO_ROOT / "CONTRIBUTING.md",
            REPO_ROOT / "SECURITY.md",
            REPO_ROOT / "AGENTS.md",
            REPO_ROOT / "docs/README.md",
            REPO_ROOT / "docs/architecture.md",
            REPO_ROOT / "docs/configuration.md",
            REPO_ROOT / "docs/testing.md",
        )
    ).lower()
    forbidden_claims = (
        "vibe-acp",
        "uv run vibe-acp",
        "rust terminal",
        "unified harness runtime",
        "mistral_api_key is required",
    )
    for claim in forbidden_claims:
        assert claim not in active_docs


def test_archived_upstream_docs_are_not_in_active_index() -> None:
    index = (REPO_ROOT / "docs/README.md").read_text()
    for removed in ("acp-setup.md", "0016-rust-cli-delivery-surface.md"):
        assert f"]({removed})" not in index


def test_default_config_uses_only_generic_local_providers() -> None:
    config = tomllib.loads((REPO_ROOT / ".vibe/config.toml").read_text())
    assert config["active_model"] in {"worker1", "worker2"}
    assert config["allowed_models"] == ["worker*"]
    for provider in config["providers"]:
        assert provider["backend"] == "generic"
        assert provider["api_style"] == "openai"
        assert provider["api_key_env_var"] == ""
        assert provider["api_base"].startswith("http://") or provider[
            "api_base"
        ].startswith("https://")


def test_no_active_builtin_agent_injects_a_cloud_provider() -> None:
    source = (REPO_ROOT / "vibe/core/agents/models.py").read_text()
    tree = ast.parse(source)
    cloud_literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.search(r"api\.mistral\.ai|console\.mistral\.ai", node.value)
    ]
    assert cloud_literals == []


def test_runtime_contains_no_hardcoded_mistral_cloud_origin() -> None:
    sources = "\n".join(
        path.read_text(errors="ignore") for path in (REPO_ROOT / "vibe").rglob("*.py")
    ).lower()
    assert "api.mistral.ai" not in sources
    assert "console.mistral.ai" not in sources
