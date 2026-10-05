from __future__ import annotations

from pathlib import Path
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_remote_runtime_subsystems_are_physically_removed() -> None:
    for relative in (
        "vibe/core/auth",
        "vibe/core/experiments",
        "vibe/core/tools/mcp",
        "vibe/core/tools/connectors",
        "vibe/core/tools/mcp_sampling.py",
        "vibe/core/tools/mcp_settings.py",
        "vibe/core/tools/remote.py",
        "vibe/core/skills/registry",
        "vibe/app_server/mcp_catalog.py",
        "vibe/app_server/connector_catalog.py",
        "vibe/app_server/_mcp_auth.py",
        "vibe/app_server/_mcp_authorization_bridge.py",
        "vibe/setup/auth",
        "vibe/setup/onboarding",
    ):
        assert not (REPO_ROOT / relative).exists(), relative


def test_runtime_dependencies_are_local_minimum() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    deps = "\n".join(project["project"]["dependencies"])
    for removed in (
        "mcp==",
        "google-auth",
        "googleapis-common-protos",
        "keyring",
        "cryptography==",
        "pyjwt",
        "requests==",
        "starlette",
        "uvicorn",
        "websockets",
        "beautifulsoup4",
        "markdownify",
    ):
        assert removed not in deps


def test_local_profile_contains_no_removed_remote_switches() -> None:
    config = tomllib.loads((REPO_ROOT / ".vibe/config.toml").read_text())
    for key in ("enable_connectors", "enable_otel", "otel_endpoint"):
        assert key not in config


def test_experiment_routing_is_removed_from_config() -> None:
    source = (REPO_ROOT / "vibe/core/config/vibe_schema.py").read_text()
    for removed in (
        "routed_default_model",
        "routed_model_config",
        "routed_extra_models",
        "ExperimentsConfig",
        "MCPServer",
        "ConnectorConfig",
    ):
        assert removed not in source


def test_remote_tool_registry_is_a_local_compatibility_noop() -> None:
    source = (REPO_ROOT / "vibe/core/tools/manager.py").read_text()
    assert "remote MCP registries are not part of Vibe Local" in source
    assert "remote connector registries are not part of Vibe Local" in source
    assert "from vibe.core.tools.remote import MCPTool" not in source
