from __future__ import annotations

from pathlib import Path
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_native_and_acp_stacks_are_removed() -> None:
    for relative in (
        "vibe/cli-rust",
        "harness",
        "vibe/acp",
        "build_backend",
        "client-e2e",
        "vibe/_experimental_harness.py",
        "vibe/cli/_rust.py",
    ):
        assert not (REPO_ROOT / relative).exists(), relative


def test_cloud_and_network_agent_paths_are_removed() -> None:
    for relative in (
        "vibe/core/llm/backend/mistral.py",
        "vibe/core/tools/builtins/web_search.py",
        "vibe/core/tools/builtins/web_fetch.py",
        "vibe/core/plugins",
        "vibe/plugins",
    ):
        assert not (REPO_ROOT / relative).exists(), relative


def test_pyproject_is_python_only_and_drops_removed_runtime_dependencies() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    assert project["build-system"]["build-backend"] == "setuptools.build_meta"
    deps = "\n".join(project["project"]["dependencies"])
    for removed in (
        "agent-client-protocol",
        "maturin",
        "miniaudio",
        "mistralai",
        "opentelemetry",
        "sentry-sdk",
    ):
        assert removed not in deps


def test_local_defaults_are_closed() -> None:
    source = (REPO_ROOT / "vibe/core/config/vibe_schema.py").read_text()
    defaults = source[
        source.index("DEFAULT_PROVIDERS = [") : source.index("def get_persisted_config")
    ]
    assert "api.mistral.ai" not in defaults
    assert 'name="llamacpp"' in defaults
    assert "Backend.GENERIC" in defaults
    assert "enable_connectors" not in source
    assert "enable_telemetry" not in source


def test_cli_has_no_removed_feature_switches() -> None:
    entrypoint = (REPO_ROOT / "vibe/cli/entrypoint.py").read_text()
    for switch in (
        "--experimental-harness",
        "--legacy-harness",
        "--smart-approve",
        "--setup",
        "--check-upgrade",
    ):
        assert switch not in entrypoint
    assert 'sys.argv[1:2] == ["mcp"]' not in entrypoint


def test_tracing_is_local_and_sentry_is_removed() -> None:
    tracing = (REPO_ROOT / "vibe/core/tracing.py").read_text()
    assert "opentelemetry" not in tracing
    assert "mistralai" not in tracing
    assert not (REPO_ROOT / "vibe/observability/sentry.py").exists()
