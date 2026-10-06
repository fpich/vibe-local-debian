"""Shared pytest configuration and helpers for the test suite.

The suite relies on in-memory fakes (``FakeBackend``, ``FakeConfigOrchestrator``)
so no model provider or network access is needed. Autouse fixtures keep tests
hermetic: throwaway working directory, isolated Vibe home, disabled OS keyring,
and isolated git configuration.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Generator
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from typing import Any

import pytest
import tomli_w

from tests.stubs.app_server import create_test_app_server_session
from tests.stubs.fake_backend import FakeBackend
from tests.stubs.fake_config_orchestrator import FakeConfigOrchestrator
from vibe.cli.textual_ui.app import StartupOptions, VibeApp
from vibe.cli.theme import resolve_auto_theme
from vibe.core.agent_loop import AgentLoop
from vibe.core.agents.models import BuiltinAgentName
from vibe.core.config import (
    ModelConfig,
    SessionLoggingConfig,
    VibeConfigSchema,
    VibeConfigSchemaType,
)
from vibe.core.config.harness_files import (
    HarnessFilesManager,
    init_harness_files_manager,
    reset_harness_files_manager,
)
from vibe.core.config.orchestrator import ConfigOrchestrator
from vibe.core.llm.types import BackendLike
from vibe.core.utils.concurrency import run_sync
from vibe.utils.platform import resolve_windows_shell


def get_base_config() -> dict[str, Any]:
    return {
        "active_model": "devstral-latest",
        "models": [
            {"name": "local", "provider": "llama-cpp", "alias": "devstral-latest"}
        ],
        "enable_telemetry": False,
    }


@pytest.fixture(autouse=True)
def tmp_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    tmp_working_directory = tmp_path_factory.mktemp("test_cwd")
    monkeypatch.chdir(tmp_working_directory)
    return tmp_working_directory


@pytest.fixture(autouse=True)
def config_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    tmp_path = tmp_path_factory.mktemp("vibe")
    config_dir = tmp_path / ".vibe"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.toml"
    config_file.write_text(tomli_w.dumps(get_base_config()), encoding="utf-8")
    monkeypatch.setattr("vibe.utils.paths._DEFAULT_VIBE_HOME", config_dir)
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("vibe.core.paths._agents_home._DEFAULT_AGENTS_HOME", agents_dir)
    return config_dir


@pytest.fixture(autouse=True)
def _reset_trusted_folders_manager(config_dir: Path) -> None:
    from vibe.core.trusted_folders import trusted_folders_manager

    trusted_folders_manager._file_path = config_dir / "trusted_folders.toml"
    trusted_folders_manager._trusted = []
    trusted_folders_manager._untrusted = []
    trusted_folders_manager._session_trusted = []


@pytest.fixture(autouse=True)
def _init_harness_files_manager():
    reset_harness_files_manager()
    init_harness_files_manager("user", "project")
    yield
    reset_harness_files_manager()


@pytest.fixture(autouse=True)
def _scratchpad_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Generator[Path]:
    scratchpad_root = tmp_path_factory.mktemp("scratchpad")
    _counter = 0

    def _fake_mkdtemp(prefix: str = "") -> str:
        nonlocal _counter
        _counter += 1
        d = scratchpad_root / f"{prefix}{_counter}"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    monkeypatch.setattr(
        "vibe.core.scratchpad.tempfile", SimpleNamespace(mkdtemp=_fake_mkdtemp)
    )
    yield scratchpad_root


@pytest.fixture(autouse=True)
def _mock_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "mock")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "mock")


@pytest.fixture(autouse=True)
def _mock_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("SHELL", "/bin/sh")
    if not hasattr(os, "getuid"):
        monkeypatch.setattr(os, "getuid", lambda: 0, raising=False)
    resolve_auto_theme.cache_clear()
    monkeypatch.setattr("vibe.cli._theme_detection.detect_terminal_dark", lambda: None)
    monkeypatch.setattr(
        "vibe.cli._theme_detection.detect_system_preferred_dark", lambda: None
    )


@pytest.fixture(autouse=True)
def _reset_windows_shell_cache() -> None:
    resolve_windows_shell.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_git_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GCM_INTERACTIVE", "never")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")


@pytest.fixture(autouse=True)
def _disable_auto_title_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(messages: Any, *, config: Any, previous_title: Any = None) -> None:
        return None

    monkeypatch.setattr("vibe.core.session.title_model.generate_session_title", _noop)


@pytest.fixture(autouse=True)
def _disable_input_grace_periods(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vibe.cli.textual_ui.widgets.approval_app._INPUT_GRACE_PERIOD_S", 0
    )
    monkeypatch.setattr(
        "vibe.cli.textual_ui.widgets.question_app._INPUT_GRACE_PERIOD_S", 0
    )
    monkeypatch.setattr("vibe.cli.textual_ui.app._DEFAULT_TYPING_DEBOUNCE_MS", 0)
    monkeypatch.delenv("VIBE_TYPING_GRACE_PERIOD_MS", raising=False)


@pytest.fixture
def mock_prompts_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    project = tmp_path / "project" / ".vibe" / "prompts"
    user = tmp_path / "home" / ".vibe" / "prompts"
    project.mkdir(parents=True)
    user.mkdir(parents=True)

    class _MockManager(HarnessFilesManager):
        @property
        def project_prompts_dirs(self) -> list[Path]:
            return [project]

        @property
        def user_prompts_dirs(self) -> list[Path]:
            return [user]

    monkeypatch.setattr(
        "vibe.core.prompts.get_harness_files_manager",
        lambda: _MockManager(sources=("user",)),
    )
    return project, user


def make_test_models(auto_compact_threshold: int) -> list[ModelConfig]:
    from vibe.core.config import DEFAULT_MODELS

    return [
        m.model_copy(update={"auto_compact_threshold": auto_compact_threshold})
        for m in DEFAULT_MODELS
    ]


def set_agent_config(agent: AgentLoop, config: VibeConfigSchema) -> None:
    orchestrator = agent.config_orchestrator
    match orchestrator:
        case ConfigOrchestrator() | FakeConfigOrchestrator():
            orchestrator._config = config
        case _:
            raise TypeError(f"unexpected orchestrator {orchestrator!r}")


def stub_config_reload(
    monkeypatch: pytest.MonkeyPatch, config: VibeConfigSchema
) -> None:
    async def _reload(self: Any) -> None:
        self._config = config

    monkeypatch.setattr(ConfigOrchestrator, "reload", _reload)
    monkeypatch.setattr(FakeConfigOrchestrator, "reload", _reload)


def _prepare_test_config_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    session_logging = kwargs.pop("session_logging", None)
    kwargs["session_logging"] = (
        SessionLoggingConfig(enabled=False)
        if session_logging is None
        else session_logging
    )
    if models := kwargs.get("models"):
        if isinstance(models, dict):
            kwargs.setdefault("active_model", next(iter(models)))
        else:
            kwargs.setdefault("active_model", models[0].alias)
    kwargs.setdefault("enable_telemetry", False)
    kwargs.setdefault("system_prompt_id", "tests")
    kwargs.setdefault("include_project_context", False)
    kwargs.setdefault("include_prompt_detail", False)
    return kwargs


async def wait_until(
    pilot: Any, predicate: Callable[[], bool], timeout: float = 2.0
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await pilot.pause(0.05)
    return predicate()


def build_test_vibe_config(
    config_cls: VibeConfigSchemaType = VibeConfigSchema, **kwargs
) -> VibeConfigSchema:
    return config_cls(**_prepare_test_config_kwargs(kwargs))


def build_test_vibe_config_schema(**kwargs) -> VibeConfigSchema:
    return VibeConfigSchema(**_prepare_test_config_kwargs(kwargs))


type ConfigBuilder = Callable[..., VibeConfigSchema]


@pytest.fixture(params=[build_test_vibe_config_schema], ids=["vibe_config_schema"])
def build_config(request: pytest.FixtureRequest) -> ConfigBuilder:
    return request.param


type ConfigLoader = Callable[[], VibeConfigSchema]


def _load_vibe_config_schema() -> VibeConfigSchema:
    return run_sync(build_default_orchestrator()).config


@pytest.fixture(params=[_load_vibe_config_schema], ids=["vibe_config_schema"])
def load_config(request: pytest.FixtureRequest) -> ConfigLoader:
    return request.param


type OrchestratorLoader[C: VibeConfigSchema] = Callable[[C], ConfigOrchestrator[C]]


async def _load_orchestrator(
    config: VibeConfigSchema,
) -> ConfigOrchestrator[VibeConfigSchema]:
    return FakeConfigOrchestrator(config)


@pytest.fixture
def load_orchestrator() -> OrchestratorLoader[VibeConfigSchema]:
    def load(config: VibeConfigSchema) -> ConfigOrchestrator[VibeConfigSchema]:
        return run_sync(_load_orchestrator(config))

    return load


def build_test_agent_loop(
    *,
    config: VibeConfigSchema | None = None,
    agent_name: str = BuiltinAgentName.ASK,
    backend: BackendLike | None = None,
    enable_streaming: bool = False,
    **kwargs,
) -> AgentLoop:
    resolved_config = config or build_test_vibe_config()
    orchestrator = run_sync(_load_orchestrator(resolved_config))
    return AgentLoop(
        config_orchestrator=orchestrator,
        agent_name=agent_name,
        backend=backend or FakeBackend(),
        enable_streaming=enable_streaming,
        **kwargs,
    )


def build_test_vibe_app(
    *,
    config: VibeConfigSchema | None = None,
    agent_loop: AgentLoop | None = None,
    **kwargs,
) -> VibeApp:
    app_config = config or build_test_vibe_config()
    resolved_agent_loop = agent_loop or build_test_agent_loop(config=app_config)
    history_file = kwargs.pop("history_file", Path(".vibehistory"))
    startup = kwargs.pop("startup", None) or StartupOptions(
        initial_prompt=kwargs.pop("initial_prompt", None)
    )
    app_server = kwargs.pop("app_server", None)
    app_server_source = (
        app_server
        if app_server is not None
        else lambda: create_test_app_server_session(resolved_agent_loop)
    )
    return VibeApp(
        history_file=history_file,
        app_server=app_server_source,
        startup=startup,
        **kwargs,
    )


@pytest.fixture
def vibe_app() -> VibeApp:
    return build_test_vibe_app()


@pytest.fixture
def agent_loop() -> AgentLoop:
    return build_test_agent_loop()


@pytest.fixture
def vibe_config() -> VibeConfigSchema:
    return build_test_vibe_config()


@pytest.fixture(params=[VibeConfigSchema], ids=["vibe_config_schema"])
def config_cls(request: pytest.FixtureRequest) -> VibeConfigSchemaType:
    return request.param


@pytest.fixture
def make_config(config_cls: VibeConfigSchemaType) -> Callable[..., VibeConfigSchema]:
    def _make(**kwargs: Any) -> VibeConfigSchema:
        return build_test_vibe_config(config_cls=config_cls, **kwargs)

    return _make


@pytest.fixture
def make_orchestrator() -> Callable[
    [], Awaitable[ConfigOrchestrator[VibeConfigSchema]]
]:
    from vibe.core.config import build_default_orchestrator

    async def _make() -> ConfigOrchestrator[VibeConfigSchema]:
        return await build_default_orchestrator()

    return _make


from vibe.core.config import build_default_orchestrator
