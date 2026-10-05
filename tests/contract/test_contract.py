"""Contract tests for the local-only product.

These tests pin the behaviours the simplified local build must keep:
startup, worker backends, core coding tools (read/edit/write/grep/bash),
out-of-workspace permissions, session save/resume, compaction, and AGENTS.md
injection. They must keep passing through every simplification step (E2..E18);
a failure here means a step broke the product contract, not a test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.conftest import build_test_agent_loop, build_test_vibe_config
from vibe.core.agent_loop import AgentLoop
from vibe.core.agents.models import AgentProfile, AgentSafety
from vibe.core.compaction import CompactionManager
from vibe.core.config import ModelConfig, ProviderConfig, SessionLoggingConfig
from vibe.core.config.harness_files import HarnessFilesManager
from vibe.core.session.session_loader import SessionLoader
from vibe.core.session.session_logger import SessionLogger
from vibe.core.system_prompt import get_agents_md_section
from vibe.core.telemetry.send import TelemetryClient
from vibe.core.tools.base import BaseToolState, InvokeContext
from vibe.core.tools.builtins.bash import Bash, BashArgs, BashToolConfig
from vibe.core.tools.builtins.edit import Edit, EditArgs, EditConfig
from vibe.core.tools.builtins.grep import Grep, GrepArgs, GrepToolConfig
from vibe.core.tools.builtins.read_file import (
    ReadFile,
    ReadFileArgs,
    ReadFileConfig,
    ReadFileState,
)
from vibe.core.tools.builtins.write_file import (
    WriteFile,
    WriteFileArgs,
    WriteFileConfig,
)
from vibe.core.tools.manager import ToolManager
from vibe.core.trusted_folders import TrustedFoldersManager
from vibe.core.types import AgentStats, LLMChunk, LLMMessage, MessageList, Role

pytestmark = [pytest.mark.contract, pytest.mark.asyncio]

WORKER1 = ModelConfig(name="kat", provider="llamacpp-worker1", alias="worker1")
WORKER2 = ModelConfig(name="qwen3.5", provider="llamacpp-worker2", alias="worker2")


def _ctx(tool_call_id: str = "contract-call") -> InvokeContext:
    return InvokeContext(tool_call_id=tool_call_id)


async def _run(tool: Any, args: Any) -> Any:
    results = [result async for result in tool.invoke(_ctx(), **args.model_dump())]
    assert results, "tool produced no result"
    return results[-1]


def _make(tool_cls: Any, project: Path, config: Any) -> Any:
    return tool_cls(config_getter=lambda: config, state=BaseToolState(), cwd=project)


class TestStartup:
    async def test_agent_loop_starts(self) -> None:
        loop = build_test_agent_loop()
        assert isinstance(loop, AgentLoop)
        await loop.wait_until_ready()

    def test_config_defaults_are_local_only(self) -> None:
        config = build_test_vibe_config()
        assert config.enable_telemetry is False
        assert config.enable_otel is False
        assert config.enable_connectors is False
        assert config.enable_update_checks is False

    def test_worker_models_resolvable(self) -> None:
        config = build_test_vibe_config(
            models=[WORKER1, WORKER2],
            active_model="worker1",
            providers=[
                ProviderConfig(
                    name="llamacpp-worker1", api_base="http://127.0.0.1:8080/v1"
                ),
                ProviderConfig(
                    name="llamacpp-worker2", api_base="http://127.0.0.1:8081/v1"
                ),
            ],
        )
        model = config.get_active_model()
        assert model.alias == "worker1"
        assert model.provider == "llamacpp-worker1"
        provider = config.get_provider_for_model(model)
        assert provider.api_base == "http://127.0.0.1:8080/v1"
        worker2 = config.get_provider_for_model(config.models["worker2"])
        assert worker2.api_base == "http://127.0.0.1:8081/v1"

    def test_allowed_models_filters_workers(self) -> None:
        config = build_test_vibe_config(
            models=[WORKER1, WORKER2],
            active_model="worker2",
            allowed_models=["kat", "qwen3.5"],
        )
        available = config.available_models()
        assert set(available) == {"worker1", "worker2"}


class TestTools:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        project = tmp_path / "project"
        project.mkdir()
        return project

    async def test_read_file(self, project: Path) -> None:
        target = project / "hello.txt"
        target.write_text("line 1\nline 2\n")
        tool = _make(ReadFile, project, ReadFileConfig())
        result = await _run(tool, ReadFileArgs(file_path=str(target)))
        assert "line 1" in result.content

    async def test_write_file(self, project: Path) -> None:
        target = project / "new.txt"
        tool = _make(WriteFile, project, WriteFileConfig())
        await _run(tool, WriteFileArgs(file_path=str(target), content="abc"))
        assert target.read_text() == "abc"

    async def test_edit_file(self, project: Path) -> None:
        target = project / "edit.txt"
        target.write_text("alpha\nbeta\n")
        tool = _make(Edit, project, EditConfig())
        await _run(
            tool,
            EditArgs(file_path=str(target), old_string="alpha", new_string="gamma"),
        )
        assert target.read_text() == "gamma\nbeta\n"

    async def test_grep(self, project: Path) -> None:
        (project / "a.txt").write_text("needle here\n")
        (project / "b.txt").write_text("nothing\n")
        tool = _make(Grep, project, GrepToolConfig())
        result = await _run(tool, GrepArgs(pattern="needle", path=str(project)))
        assert "a.txt" in result.matches
        assert result.match_count >= 1

    async def test_bash(self, project: Path) -> None:
        tool = Bash(
            config_getter=lambda: BashToolConfig(), state=BaseToolState(), cwd=project
        )
        result = await _run(tool, BashArgs(command="echo contract-ok"))
        assert "contract-ok" in result.stdout


class TestWorkspacePermissions:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        project = tmp_path / "project"
        project.mkdir()
        return project

    @pytest.fixture
    def outside(self, tmp_path: Path) -> Path:
        outside = tmp_path / "outside"
        outside.mkdir()
        return outside

    def _tool(self, tool_cls: Any, config: Any, project: Path) -> Any:
        tool = _make(tool_cls, project, config)
        assert tool.workspace.cwd == project.resolve()
        return tool

    async def test_write_outside_workspace_asks(
        self, project: Path, outside: Path
    ) -> None:
        tool = self._tool(WriteFile, WriteFileConfig(), project)
        ctx = tool.resolve_permission(
            WriteFileArgs(file_path=str(outside / "escape.txt"), content="x")
        )
        assert ctx is not None
        assert ctx.permission.value == "ask"

    async def test_read_outside_workspace_asks(
        self, project: Path, outside: Path
    ) -> None:
        target = outside / "secret.txt"
        target.write_text("s")
        tool = self._tool(ReadFile, ReadFileConfig(), project)
        ctx = tool.resolve_permission(ReadFileArgs(file_path=str(target)))
        assert ctx is not None
        assert ctx.permission.value == "ask"

    async def test_edit_outside_workspace_asks(
        self, project: Path, outside: Path
    ) -> None:
        target = outside / "file.txt"
        target.write_text("a\n")
        tool = self._tool(Edit, EditConfig(), project)
        ctx = tool.resolve_permission(
            EditArgs(file_path=str(target), old_string="a", new_string="b")
        )
        assert ctx is not None
        assert ctx.permission.value == "ask"

    async def test_inside_workspace_does_not_ask(self, project: Path) -> None:
        tool = self._tool(WriteFile, WriteFileConfig(), project)
        ctx = tool.resolve_permission(
            WriteFileArgs(file_path=str(project / "ok.txt"), content="x")
        )
        assert ctx is None or ctx.permission.value != "ask"


class TestSessionResume:
    @pytest.fixture
    def session_config(self, tmp_path: Path) -> SessionLoggingConfig:
        return SessionLoggingConfig(enabled=True, save_dir=str(tmp_path / "sessions"))

    @pytest.fixture
    def tool_manager(self) -> Any:
        manager = MagicMock(spec=ToolManager)
        manager.available_tools = {}
        return manager

    @staticmethod
    def _agent_profile() -> AgentProfile:
        return AgentProfile(
            name="test-agent",
            display_name="Test Agent",
            description="A test agent",
            safety=AgentSafety.SAFE,
        )

    async def test_session_persists_and_resumes(
        self, session_config: SessionLoggingConfig, tmp_path: Path, tool_manager: Any
    ) -> None:
        cwd = tmp_path / "project"
        cwd.mkdir()
        logger = SessionLogger(session_config, "contract-session-1234", cwd=cwd)
        assert logger.session_dir is not None
        await logger.save_interaction(
            [
                LLMMessage(role=Role.user, content="hello"),
                LLMMessage(role=Role.assistant, content="hi"),
            ],
            stats=AgentStats(),
            config=build_test_vibe_config(),
            tool_manager=tool_manager,
            agent_profile=self._agent_profile(),
        )
        assert logger.persisted
        loaded = SessionLoader._read_validated_session(
            logger.session_dir, working_directory=cwd
        )
        assert loaded is not None
        messages_text = (logger.session_dir / "messages.jsonl").read_text()
        assert "hello" in messages_text

    async def test_find_latest_session(
        self, session_config: SessionLoggingConfig, tmp_path: Path, tool_manager: Any
    ) -> None:
        cwd = tmp_path / "project"
        cwd.mkdir()
        logger = SessionLogger(session_config, "contract-5678", cwd=cwd)
        await logger.save_interaction(
            [LLMMessage(role=Role.user, content="question")],
            stats=AgentStats(),
            config=build_test_vibe_config(),
            tool_manager=tool_manager,
            agent_profile=self._agent_profile(),
        )
        found = SessionLoader.find_latest_session(session_config, working_directory=cwd)
        assert found is not None
        assert found == logger.session_dir


class TestCompaction:
    @staticmethod
    def _manager(config: Any) -> CompactionManager:
        stats = AgentStats()

        async def complete(*, model: Any, messages: Any, **kwargs: Any) -> LLMChunk:
            return LLMChunk(
                message=LLMMessage(
                    role=Role.assistant, content="<summary>local summary</summary>"
                )
            )

        async def save() -> None:
            return None

        class _OfflineTelemetry(TelemetryClient):
            def __init__(self) -> None:
                pass

            def send_compaction_failed(self, **kwargs: Any) -> None:
                return None

        telemetry = _OfflineTelemetry()

        return CompactionManager(
            messages=MessageList([
                LLMMessage(role=Role.system, content="system prompt"),
                *(
                    LLMMessage(role=Role.user, content=f"message {i}")
                    for i in range(10)
                ),
            ]),
            stats_getter=lambda: stats,
            config_getter=lambda: config,
            complete=complete,
            available_tools=lambda: [],
            tool_choice=lambda: "auto",
            save=save,
            telemetry_client=telemetry,
            session_ids=lambda: ("contract-session", None),
        )

    async def test_compact_produces_summary_envelope(self) -> None:
        config = build_test_vibe_config(models=[WORKER1], active_model="worker1")
        manager = self._manager(config)
        summary = await manager.compact()
        assert summary == "local summary"
        assert manager._messages[-1].context_boundary == "compaction"
        assert "local summary" in (manager._messages[-1].content or "")


class TestAgentsMd:
    def test_section_includes_user_and_project_docs(self, tmp_path: Path) -> None:
        section = get_agents_md_section(
            user_doc="user-level instructions",
            project_docs=[(tmp_path, "project rules")],
        )
        assert section is not None
        assert "user-level instructions" in section
        assert "project rules" in section
        assert "AGENTS.md" in section

    def test_section_absent_without_docs(self) -> None:
        assert get_agents_md_section(user_doc="", project_docs=[]) is None

    async def test_read_file_injects_subdirectory_agents_md(
        self, tmp_path: Path
    ) -> None:
        project = tmp_path / "project"
        sub = project / "pkg"
        sub.mkdir(parents=True)
        (sub / "AGENTS.md").write_text("package-local rules")
        target = sub / "code.py"
        target.write_text("x = 1\n")
        trust_store = TrustedFoldersManager()
        trust_store.add_trusted(project)
        harness_files = HarnessFilesManager(
            sources=("project",), trust_store=trust_store, cwd=project
        ).for_session(project, workspace_roots=[project])
        tool = ReadFile(
            config_getter=lambda: ReadFileConfig(),
            state=ReadFileState(),
            cwd=project,
            harness_files=harness_files,
        )
        result = await _run(tool, ReadFileArgs(file_path=str(target)))
        extra = tool.get_result_extra(result)
        assert extra is not None
        assert "package-local rules" in extra
