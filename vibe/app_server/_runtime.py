from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
import stat
import threading
from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError

from vibe import __version__
from vibe.app_server._host import HostRequestHandler
from vibe.app_server._projection import project_agent_summaries, project_config_view
from vibe.app_server._session_backend_port import SessionBackendHost
from vibe.app_server._session_backend_services import SessionBackendServices
from vibe.app_server._session_model import (
    active_model_is_pinned,
    clear_session_active_model_override,
    config_active_model,
    set_session_active_model_override,
)
from vibe.app_server.client import AppServerClient
from vibe.app_server.client_tools import ClientToolHandler
from vibe.app_server.models import (
    AgentStatsSnapshot,
    ConfigIssue,
    ConnectorCounts,
    MCPState,
)
from vibe.app_server.protocol import (
    ClientCapabilities,
    ClientInfo,
    RuntimeSnapshot,
    SessionOptions,
    TransportKind,
)
from vibe.app_server.transport import JsonRpcTransport, memory_transport_pair
from vibe.core.agent_loop import AgentLoop, AgentRuntimePolicy
from vibe.core.agents.manager import AgentManager
from vibe.core.agents.models import AgentProfile
from vibe.core.config import (
    MissingAPIKeyError,
    SessionLoggingConfig,
    VibeConfigSchema,
    build_default_orchestrator,
)
from vibe.core.config.harness_files import HarnessFilesManager
from vibe.core.config.layers.overrides import OverridesLayer
from vibe.core.config.orchestrator import ConfigOrchestrator
from vibe.core.hooks.config import load_hooks_from_fs
from vibe.core.hooks.models import HookConfigResult
from vibe.core.local_runtime import build_launch_context
from vibe.core.paths import WORKTREES_DIR
from vibe.core.session import last_session_pointer
from vibe.core.session.session_id import extract_suffix, generate_session_id
from vibe.core.session.session_index import warm_session_index
from vibe.core.session.session_interop import resolve_legacy_session_reference
from vibe.core.session.session_lease import SessionLease
from vibe.core.session.session_loader import SessionLoader
from vibe.core.session.session_permissions import start_restrict_session_log_permissions
from vibe.core.system_prompt import ProjectContextProvider
from vibe.core.tools.permissions import PermissionStore
from vibe.core.tracing import setup_tracing
from vibe.core.types import AgentStats, LLMMessage, Role, SessionMetadata
from vibe.core.utils import get_windows_bash_path, is_windows
from vibe.observability.logging import logger, set_config_log_level
from vibe.utils.cache_store import FileSystemCacheStore
from vibe.utils.paths import is_dangerous_directory

_SHORT_SESSION_ID_LENGTH = 8
type _CommandEnvironmentMode = Literal["unix", "git_bash", "powershell"]


def _command_environment_mode() -> _CommandEnvironmentMode:
    if not is_windows():
        return "unix"
    if get_windows_bash_path() is not None:
        return "git_bash"
    return "powershell"


def _build_project_context_section(
    config: VibeConfigSchema, harness_files: HarnessFilesManager, cwd: Path
) -> str:
    """Replicate the legacy system prompt's project-context block.

    Includes the absolute working directory, git status (branch, main
    branch, porcelain status, recent commits), and any extra working
    directories — the same information ``build_system_prompt`` injects for
    the legacy backend.
    """
    from string import Template

    from vibe.core.prompts import UtilityPrompt

    is_dangerous, reason = is_dangerous_directory(cwd)
    if is_dangerous:
        template = UtilityPrompt.DANGEROUS_DIRECTORY.read()
        return Template(template).safe_substitute(
            reason=reason.lower(), abs_path=cwd.resolve()
        )

    context = ProjectContextProvider(
        config=config.project_context, root_path=cwd
    ).get_full_context()

    cwd_resolved = cwd.resolve()
    extra_roots = [
        root for root in harness_files.project_roots if root.resolve() != cwd_resolved
    ]
    if extra_roots:
        dirs_lines = "\n".join(f" - {d}" for d in extra_roots)
        context = (
            f"{context}\n\nAdditional working directories (treated with the same "
            f"file-access permissions as the primary working directory):\n" + dirs_lines
        )
    return context


def _agent_profile_prompt(
    profile: AgentProfile,
) -> tuple[str | None, ConfigIssue | None]:
    """The prompt text an agent profile asks for, or why it cannot have it.

    Only a prompt id the profile itself declares is resolved as a file. The id
    the config carries otherwise is a GrowthBook variant the SDK owns, and
    reading a bundled Vibe prompt of the same name would quietly serve the
    legacy text instead.
    """
    from vibe.core.prompts import MissingPromptFileError, load_system_prompt

    prompt_id = profile.overrides.get("system_prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        return None, None
    try:
        return load_system_prompt(prompt_id), None
    except (MissingPromptFileError, ValueError) as error:
        logger.warning("Agent %r: %s", profile.name, error)
        return None, ConfigIssue(
            file=str(profile.source_path or profile.name),
            message=f"Agent '{profile.name}': {error}",
        )










if TYPE_CHECKING:
    from vibe.app_server.server import AppServer






@dataclass(frozen=True, slots=True)
class NewSessionIntent:
    pass


@dataclass(frozen=True, slots=True)
class ContinueSessionIntent:
    pass


@dataclass(frozen=True, slots=True)
class ResumeSessionIntent:
    session_id: str

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ValueError("A session ID is required to resume a session")


type LocalSessionIntent = NewSessionIntent | ContinueSessionIntent | ResumeSessionIntent


@dataclass(frozen=True, slots=True)
class ClientDescriptor:
    info: ClientInfo
    capabilities: ClientCapabilities = field(default_factory=ClientCapabilities)


def _default_client() -> ClientDescriptor:
    return ClientDescriptor(info=ClientInfo(name="vibe_client", version=__version__))


@dataclass(frozen=True, slots=True)
class LocalHarnessOptions:
    client: ClientDescriptor = field(default_factory=_default_client)
    session_options: SessionOptions = field(
        default_factory=lambda: SessionOptions(cwd=str(Path.cwd().resolve()))
    )
    session: LocalSessionIntent = field(default_factory=NewSessionIntent)
    client_tool_handler: ClientToolHandler | None = None


class RuntimeSessionNotFoundError(RuntimeError):
    pass


class RuntimeAuthenticationError(RuntimeError):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"Authentication is required for provider: {provider}")


class RuntimeConfigurationError(RuntimeError):
    pass


class RuntimeUnfinishedMigrationError(RuntimeError):
    def __init__(self, session_id: str, source_backend: str) -> None:
        self.session_id = session_id
        self.source_backend = source_backend
        super().__init__(
            f"The {source_backend} session has unfinished recoverable work: "
            f"{session_id}"
        )


class RuntimeInvalidMigrationSourceError(RuntimeError):
    def __init__(self, session_id: str, source_backend: str, message: str) -> None:
        self.session_id = session_id
        self.source_backend = source_backend
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RootOpenRequest:
    options: SessionOptions
    client_info: ClientInfo
    session_id: str | None = None
    continue_latest: bool = False
    client_capabilities: ClientCapabilities = field(default_factory=ClientCapabilities)

    def __post_init__(self) -> None:
        if self.session_id is not None and self.continue_latest:
            raise ValueError("Cannot resume a session and continue the latest")
        if self.options.cwd == "":
            # An empty cwd would silently resolve to the server process cwd,
            # making a directory the caller never named trustable.
            raise ValueError("Session cwd must not be empty")


@dataclass(frozen=True, slots=True)
class _AgentLoopBlueprint:
    config_orchestrator: ConfigOrchestrator[VibeConfigSchema]
    agent_name: str
    policy: AgentRuntimePolicy
    cwd: Path
    harness_files: HarnessFilesManager
    is_subagent: bool = False
    parent_session_id: str | None = None
    session_id: str | None = None
    session_dir: Path | None = None
    session_lease: SessionLease | None = None

    def build(self) -> AgentLoop:
        return AgentLoop(
            config_orchestrator=self.config_orchestrator,
            agent_name=self.agent_name,
            max_turns=self.policy.max_turns,
            max_price=self.policy.max_price,
            max_tokens=self.policy.max_tokens,
            max_session_tokens=self.policy.max_session_tokens,
            enable_streaming=self.policy.enable_streaming,
            launch_context=self.policy.launch_context,
            is_subagent=self.is_subagent,
            defer_heavy_init=True,
            headless=self.policy.headless,
            hook_config_result=self.policy.hook_config_result,
            permission_store=self.policy.permission_store,
            cache_store=self.policy.cache_store,
            force_bypass_tool_permissions=self.policy.force_bypass_tool_permissions,
            local_managed_shell_runtime_enabled=(
                self.policy.local_managed_shell_runtime_enabled
            ),
            auto_title_enabled=self.policy.auto_title_enabled,
            parent_session_id=self.parent_session_id,
            cwd=self.cwd,
            harness_files=self.harness_files,
            session_id=self.session_id,
            session_dir=self.session_dir,
            session_lease=self.session_lease,
        )


@dataclass(frozen=True, slots=True)
class _SessionConfig:
    config_orchestrator: ConfigOrchestrator[VibeConfigSchema]
    harness_files: HarnessFilesManager


@dataclass(frozen=True, slots=True)
class _RootRuntimeBlueprint:
    config_orchestrator: ConfigOrchestrator[VibeConfigSchema]
    harness_files: HarnessFilesManager
    options: SessionOptions
    client_info: ClientInfo
    client_capabilities: ClientCapabilities
    hook_config_result: HookConfigResult
    cache_store: FileSystemCacheStore

    @property
    def cwd(self) -> Path:
        return Path(self.options.cwd or Path.cwd()).expanduser().resolve()

    @property
    def config(self) -> VibeConfigSchema:
        return self.config_orchestrator.config

    def build(
        self,
        *,
        parent_session_id: str | None = None,
        session_id: str | None = None,
        session_dir: Path | None = None,
        session_lease: SessionLease | None = None,
    ) -> AgentLoop:
        policy = AgentRuntimePolicy(
            max_turns=self.options.max_turns,
            max_price=self.options.max_price,
            max_tokens=None,
            max_session_tokens=self.options.max_session_tokens,
            enable_streaming=True,
            launch_context=build_launch_context(
                agent_entrypoint=self.client_info.entrypoint,
                agent_version=__version__,
                client_name=self.client_info.name,
                client_version=self.client_info.version,
                terminal_emulator=self.client_info.terminal_emulator,
            ),
            headless=self.options.headless,
            hook_config_result=self.hook_config_result,
            permission_store=PermissionStore(),
            cache_store=self.cache_store,
            force_bypass_tool_permissions=self.options.auto_approve,
            local_managed_shell_runtime_enabled=(
                "terminal" not in self.client_capabilities.client_tools
            ),
            # The legacy AgentLoop generates background titles for CLI and Desktop.
            # Other clients retain the preview, and config can disable generation.
            auto_title_enabled=(
                self.client_info.entrypoint in {"cli", "desktop"}
                and (self.config.session_logging.auto_title or "first_message") != "off"
            ),
        )
        return _AgentLoopBlueprint(
            config_orchestrator=self.config_orchestrator.copy(),
            agent_name=self.options.agent or self.config.resolve_default_agent(),
            policy=policy,
            parent_session_id=parent_session_id,
            cwd=self.cwd,
            harness_files=self.harness_files,
            session_id=session_id,
            session_dir=session_dir,
            session_lease=session_lease,
        ).build()


# The harness always binds a session to a concrete on-disk store: there is no
# in-memory backend, and a ``None`` root silently falls back to the configured save
# dir. One root per process, because ``configure_storage`` refuses to move the root
# while a session is bound to it. Every app-server on the process holds a lease, so
# the last one out removes the tree: a stop is not the end of the process, and ACP
# keeps opening sessions on it. A later session gets a fresh root, which
# ``configure_storage`` accepts because nothing is bound by then.




def _reopen_and_retry(
    func: Callable[[str], None], path: str, exc: BaseException
) -> None:
    # The Harness checks plugin packages out as read-only trees under the same
    # storage root the sessions live in, and nothing can be unlinked from one until
    # its directory is writable again.
    if not isinstance(exc, PermissionError):
        raise exc
    parent = Path(path).parent
    parent.chmod(parent.stat().st_mode | stat.S_IRWXU)
    func(path)


@dataclass(frozen=True, slots=True)
class HarnessServer:
    _server: AppServer
    _transport: JsonRpcTransport
    _reconnectable: bool = False

    async def serve(self) -> None:
        await self._server.serve_connection(
            self._transport, close_on_disconnect=not self._reconnectable
        )

    def connect_client(self) -> AppServerClient:
        if not self._reconnectable:
            raise RuntimeError("This app-server transport cannot reconnect")
        client_transport, server_transport = memory_transport_pair()
        return AppServerClient(
            client_transport,
            run_peer=lambda: self._server.serve_connection(
                server_transport, close_on_disconnect=False
            ),
        )


class AgentRuntimeFactory:
    def resolve_latest(self, source: AgentLoop, cwd: Path) -> str:
        _require_session_logging(source.config)
        return _find_session_to_continue(source.config, cwd=cwd)

    async def resume_root(self, source: AgentLoop, session_id: str) -> None:
        """Resume a stored session by rebinding the existing loop in place.

        The existing MCP connections, tool registry, git context, and config
        are all reused — only session-scoped state (ID, messages, stats,
        session logger) is swapped. This avoids the cold-rebuild overhead of
        creating a fresh AgentLoop on every resume.

        The rebind runs before waiting for deferred init so the UI can render
        the resumed transcript immediately. ``finish_resume_root`` must be
        called afterward to await readiness and hydrate experiments.
        """
        session_id = await asyncio.to_thread(
            _resolve_resume_session_id, source.config, session_id
        )
        lease = await asyncio.to_thread(
            _acquire_session_lease, source.config, session_id
        )
        previous_model = source.config.get_active_model().alias
        previous_session_pinned = source.session_logger.active_model is not None
        try:
            session_path, loaded_messages, metadata = await asyncio.to_thread(
                _load_session, source.config, session_id
            )
            active_model = config_active_model(metadata)
            await _restore_session_active_model(
                source.config_orchestrator,
                active_model,
                clear_existing=previous_session_pinned,
            )
            # ``_load_session`` already parsed metadata.json into ``metadata``;
            # parse that dict instead of re-reading the file from disk.
            session_metadata = SessionMetadata.model_validate(metadata)
            stats = _build_stats(source, metadata)
            # Rebind before waiting for deferred init so the UI can render the
            # resumed transcript immediately. The init thread's
            # ``update_system_prompt`` inserts at position 0 (see
            # ``MessageList.update_system_prompt``), so it lands correctly on top
            # of the resumed messages whenever it completes — same pattern as
            # ``resume_blueprint``.
            source.rebind_to_session(
                session_id,
                session_path,
                loaded_messages,
                session_metadata=session_metadata,
                parent_session_id=_parent_session_id(metadata),
                stats=stats,
            )
            if source.config.get_active_model().alias != previous_model:
                await source.reload_with_initial_messages()
        except BaseException:
            if lease is not None:
                await asyncio.to_thread(lease.release)
            raise
        source.replace_session_lease(lease)

    async def finish_resume_root(self, source: AgentLoop, session_id: str) -> None:
        """Finish a resume by awaiting deferred local initialization."""
        try:
            await source._await_deferred_init()
        except Exception:
            logger.exception(
                "Deferred init failed after resuming session_id=%s", session_id
            )

    async def resume_blueprint(
        self,
        blueprint: _RootRuntimeBlueprint,
        session_id: str,
        session_lease: SessionLease | None = None,
    ) -> AgentLoop:
        session_path, loaded_messages, metadata = await asyncio.to_thread(
            _load_session, blueprint.config, session_id
        )
        await _restore_session_active_model(
            blueprint.config_orchestrator, config_active_model(metadata)
        )
        replacement = blueprint.build(
            parent_session_id=_parent_session_id(metadata),
            session_id=session_id,
            session_dir=session_path,
            session_lease=session_lease,
        )
        # Set messages and stats immediately so the UI can render the stored
        # transcript while the runtime (git, MCP) warms up in the background.
        # MessageList.update_system_prompt() inserts at position 0 when the
        # background thread eventually sets the system prompt, so no system
        # message needs to be present here.
        try:
            replacement.messages.reset_preserving_system(loaded_messages)
            _apply_stored_stats(replacement, metadata)
            # The background thread updates the system prompt once init finishes,
            # same as a fresh session start.
        except BaseException:
            await close_agent_loop(replacement)
            raise
        return replacement

    async def create_child(
        self,
        parent: AgentLoop,
        agent_name: str,
        *,
        session_id: str | None = None,
        session_dir: Path | None = None,
    ) -> AgentLoop:
        parent_session_dir = parent.session_logger.session_dir
        orchestrator = parent.config_orchestrator.copy()
        session_logging = SessionLoggingConfig(
            save_dir=(
                str(parent_session_dir / "agents")
                if parent_session_dir is not None
                else ""
            ),
            session_prefix=agent_name,
            enabled=parent_session_dir is not None,
        )
        failures = await orchestrator.set_field(
            "/session_logging",
            session_logging.model_dump(mode="json"),
            reason="configure child session logging",
            target_layer=OverridesLayer.NAME,
        )
        if failures:
            raise RuntimeConfigurationError(
                "Failed to configure child session logging"
            ) from failures[0]
        child_session_id = session_id or generate_session_id()
        lease = await asyncio.to_thread(
            _acquire_session_lease, parent.config, child_session_id
        )
        try:
            return self._create_like(
                parent,
                config_orchestrator=orchestrator,
                agent_name=agent_name,
                is_subagent=True,
                parent_session_id=parent.session_id,
                session_id=child_session_id,
                session_dir=session_dir,
                session_lease=lease,
                share_permissions=True,
            )
        except BaseException:
            if lease is not None:
                await asyncio.to_thread(lease.release)
            raise

    async def resume_child(
        self, parent: AgentLoop, agent_name: str, session_id: str, session_dir: Path
    ) -> AgentLoop:
        loaded_messages, metadata = await asyncio.to_thread(
            SessionLoader.load_session, session_dir
        )
        child = await self.create_child(
            parent, agent_name, session_id=session_id, session_dir=session_dir
        )
        # Eager message setting: background thread inserts system prompt at position 0
        # when _complete_init finishes, same pattern as resume_blueprint.
        try:
            child.messages.reset_preserving_system(loaded_messages)
            _apply_stored_stats(child, metadata)
        except BaseException:
            await close_agent_loop(child)
            raise
        return child

    async def fork(self, source: AgentLoop, message_id: str | None) -> AgentLoop:
        session_id = generate_session_id(suffix=extract_suffix(source.session_id))
        lease = await asyncio.to_thread(
            _acquire_session_lease, source.config, session_id
        )
        forked: AgentLoop | None = None
        try:
            forked = self._create_like(
                source,
                agent_name=source.agent_profile.name,
                parent_session_id=source.session_id,
                session_id=session_id,
                session_lease=lease,
            )
            await forked.wait_until_ready()
            forked.messages.extend(_messages_for_fork(source, message_id))
            await forked.session_logger.save_interaction(
                forked.messages,
                forked.stats,
                forked.config,
                forked.tool_manager,
                forked.agent_profile,
            )
        except BaseException:
            if forked is not None:
                await close_agent_loop(forked)
            elif lease is not None:
                await asyncio.to_thread(lease.release)
            raise
        return forked

    @staticmethod
    def _create_like(
        source: AgentLoop,
        *,
        config_orchestrator: ConfigOrchestrator[VibeConfigSchema] | None = None,
        agent_name: str,
        is_subagent: bool = False,
        parent_session_id: str | None = None,
        session_id: str | None = None,
        session_dir: Path | None = None,
        session_lease: SessionLease | None = None,
        share_permissions: bool = False,
    ) -> AgentLoop:
        policy = source.runtime_policy
        if not share_permissions:
            policy = replace(policy, permission_store=PermissionStore())
        if is_subagent:
            policy = replace(policy, enable_streaming=False)
        replacement = _AgentLoopBlueprint(
            config_orchestrator=(
                config_orchestrator or source.config_orchestrator.copy()
            ),
            agent_name=agent_name,
            policy=policy,
            is_subagent=is_subagent,
            parent_session_id=parent_session_id,
            cwd=source.cwd,
            harness_files=source.harness_files,
            session_id=session_id,
            session_dir=session_dir,
            session_lease=session_lease,
        ).build()
        return replacement


class HarnessProcess:
    def __init__(
        self,
        harness_files: HarnessFilesManager | None = None,
    ) -> None:
        self.runtime_factory = AgentRuntimeFactory()
        self.cache_store = FileSystemCacheStore()
        self.harness_files = harness_files or HarnessFilesManager(
            sources=("user", "project")
        )
        self._configuration_lock = threading.Lock()
        self._configured = False
        self._staged_roots: dict[str, AgentLoop] = {}
        self._staged_roots_lock = asyncio.Lock()
        self._closed = False
        self.harness_selection_source = "legacy"
        self.host_handler = HostRequestHandler(
            self.harness_files, harness_selection_source=self.harness_selection_source
        )

    def create_session_backend_host(
        self, services: SessionBackendServices
    ) -> SessionBackendHost:
        from vibe.app_server._legacy_session_runtime import (
            create_legacy_session_backend_host,
        )

        return create_legacy_session_backend_host(
            open_root=self.open_root,
            runtime_factory=self.runtime_factory,
            host_handler=self.host_handler,
            stage_root=self.stage_root,
            services=services,
        )

    async def stage_root(self, root: AgentLoop) -> None:
        superseded: AgentLoop | None = None
        async with self._staged_roots_lock:
            if self._closed:
                superseded = root
            else:
                superseded = self._staged_roots.get(root.session_id)
                self._staged_roots[root.session_id] = root
        if superseded is not None and superseded is not root:
            await close_agent_loop(superseded)
        if self._closed:
            if superseded is root:
                await close_agent_loop(root)
            raise RuntimeError("The app-server harness process is closed")

    async def close(self) -> None:
        async with self._staged_roots_lock:
            if self._closed:
                return
            self._closed = True
            staged = list(self._staged_roots.values())
            self._staged_roots.clear()
        errors: list[BaseException] = []
        for root in staged:
            try:
                await close_agent_loop(root)
            except BaseException as exc:
                errors.append(exc)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise BaseExceptionGroup("Failed to close staged session runtimes", errors)

    async def build_session_runtime(self, options: SessionOptions) -> RuntimeSnapshot:
        session_config = await self._build_session_config(options)
        return build_runtime_snapshot(
            options, session_config.config_orchestrator, session_config.harness_files
        )


    async def _build_session_config(self, options: SessionOptions) -> _SessionConfig:
        cwd = Path(options.cwd or Path.cwd()).expanduser().resolve()
        workspace_roots = [
            Path(root).expanduser().resolve() for root in options.workspace_roots
        ]
        # The session cwd is deliberately absent from workspace_roots here:
        # a listed cwd becomes a session root, and ``project_roots`` returns
        # the listed roots even when the tree is untrusted, which would load
        # that tree's AGENTS.md past the trust gate. The same invariant is
        # enforced by the AGENTS.md hook handler (see
        # ``_agents_md_hooks._session_files``); the durable home would be
        # ``for_session`` itself ignoring a listed root equal to the cwd.
        harness_files = self.harness_files.for_session(
            cwd, workspace_roots=workspace_roots
        )
        if options.trust_workspace:
            harness_files.trust_store.trust_for_session(cwd)
        overrides = _session_config_overrides(options)
        config_orchestrator = await build_default_orchestrator(
            overrides, harness_files=harness_files
        )
        # Every session crosses this config build, and the unified harness
        # never constructs the legacy agent loop, so the sweep starts here.
        start_restrict_session_log_permissions(
            config_orchestrator.config.session_logging
        )
        return _SessionConfig(
            config_orchestrator=config_orchestrator, harness_files=harness_files
        )

    async def build_root_blueprint(
        self,
        options: SessionOptions,
        client_info: ClientInfo,
        client_capabilities: ClientCapabilities | None = None,
    ) -> _RootRuntimeBlueprint:
        session_config = await self._build_session_config(options)
        config_orchestrator = session_config.config_orchestrator
        harness_files = session_config.harness_files
        hook_config_result = await asyncio.to_thread(
            load_hooks_from_fs, harness_files=harness_files
        )
        await asyncio.to_thread(self._configure_process, config_orchestrator.config)
        return _RootRuntimeBlueprint(
            config_orchestrator=config_orchestrator,
            harness_files=harness_files,
            options=options,
            client_info=client_info,
            client_capabilities=client_capabilities or ClientCapabilities(),
            hook_config_result=hook_config_result,
            cache_store=self.cache_store,
        )

    async def open_root(self, request: RootOpenRequest) -> AgentLoop:
        try:
            if request.session_id is not None:
                staged = await self._claim_staged_root(request.session_id)
                if staged is not None:
                    return staged
            blueprint = await self.build_root_blueprint(
                request.options, request.client_info, request.client_capabilities
            )
            session_id = request.session_id
            if request.continue_latest:
                session_id = _find_session_to_continue(
                    blueprint.config, cwd=blueprint.cwd
                )
            if session_id is not None:
                session_id = await asyncio.to_thread(
                    _resolve_resume_session_id, blueprint.config, session_id
                )
                lease = await asyncio.to_thread(
                    _acquire_session_lease, blueprint.config, session_id
                )
                try:
                    return await self.runtime_factory.resume_blueprint(
                        blueprint, session_id, lease
                    )
                except BaseException:
                    if lease is not None:
                        await asyncio.to_thread(lease.release)
                    raise
            session_id = generate_session_id()
            lease = await asyncio.to_thread(
                _acquire_session_lease, blueprint.config, session_id
            )
            try:
                return blueprint.build(session_id=session_id, session_lease=lease)
            except BaseException:
                if lease is not None:
                    await asyncio.to_thread(lease.release)
                raise
        except MissingAPIKeyError as exc:
            raise RuntimeAuthenticationError(exc.provider_name) from exc
        except (ValidationError, ValueError) as exc:
            raise RuntimeConfigurationError(str(exc)) from exc





    async def _claim_staged_root(self, session_id: str) -> AgentLoop | None:
        async with self._staged_roots_lock:
            if self._closed:
                raise RuntimeError("The app-server harness process is closed")
            return self._staged_roots.pop(session_id, None)

    def _configure_process(self, config: VibeConfigSchema) -> None:
        with self._configuration_lock:
            if self._configured:
                return
            setup_tracing(config)
            warm_session_index(config.session_logging)
            set_config_log_level(config.log_level)
            self._configured = True


def build_runtime_snapshot(
    options: SessionOptions,
    config_orchestrator: ConfigOrchestrator[VibeConfigSchema],
    harness_files: HarnessFilesManager,
    *,
    issues: Sequence[ConfigIssue] = (),
) -> RuntimeSnapshot:
    """Project the local legacy runtime without Unified Harness state."""
    config = config_orchestrator.config
    agents = AgentManager(
        config_orchestrator,
        options.agent or config.resolve_default_agent(),
        harness_files=harness_files,
    )
    active_model = config.get_active_model()
    active, available = project_agent_summaries(
        agents.active_profile, agents.available_agents.values()
    )
    return RuntimeSnapshot(
        config=project_config_view(
            config,
            active_model_pinned=active_model_is_pinned(config_orchestrator),
            image_fallback=True,
        ),
        active_agent=active,
        agents=available,
        skills=[],
        tools=[],
        stats=AgentStatsSnapshot(
            input_price_per_million=active_model.input_price,
            output_price_per_million=active_model.output_price,
            cached_input_price_per_million=active_model.cached_input_price,
        ),
        context_window=active_model.auto_compact_threshold,
        issues=list(issues),
        hooks_count=0,
        connectors=ConnectorCounts(),
        mcp=MCPState(),
        bypass_tool_permissions=options.auto_approve or config.bypass_tool_permissions,
        experimental_harness=False,
    )


async def create_harness_server(
    transport: JsonRpcTransport,
    *,
    transport_kind: TransportKind,
    process: HarnessProcess | None = None,
) -> HarnessServer:
    """Build a local-only server over ``transport``."""
    from vibe.app_server.server import AppServer

    process = process or HarnessProcess()
    return HarnessServer(
        _server=AppServer(
            transport,
            transport_kind=transport_kind,
            host_handler=process.host_handler,
            session_backend_host_factory=process.create_session_backend_host,
        ),
        _transport=transport,
        _reconnectable=transport_kind == "in_process",
    )


def _session_config_overrides(options: SessionOptions) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if options.enabled_tools is not None:
        overrides["enabled_tools"] = options.enabled_tools
    if options.disabled_tools:
        overrides["disabled_tools"] = options.disabled_tools
    return overrides


def _require_session_logging(config: VibeConfigSchema) -> None:
    if config.session_logging.enabled:
        return
    raise RuntimeSessionNotFoundError(
        "Session logging is disabled. Enable it in config to use --continue or --resume"
    )


def _find_session_to_continue(config: VibeConfigSchema, *, cwd: Path) -> str:
    cwd = cwd.resolve()
    pointer_session_id = last_session_pointer.load(config.session_logging)
    if pointer_session_id is not None:
        session = SessionLoader.find_session_by_id(
            pointer_session_id, config.session_logging, working_directory=cwd
        )
        if session is not None:
            return pointer_session_id

    session = SessionLoader.find_latest_session(
        config.session_logging, working_directory=cwd
    )
    if session is not None:
        _, metadata = SessionLoader.load_session(session)
        session_id = metadata.get("session_id")
        if isinstance(session_id, str) and session_id:
            return session_id
        raise RuntimeSessionNotFoundError(f"Saved session has no session ID: {session}")

    message = (
        f"No previous sessions found in {config.session_logging.save_dir} for cwd={cwd}"
    )
    if cwd.is_relative_to(WORKTREES_DIR.path.resolve()):
        message = (
            f"{message}. This worktree has no sessions yet; start a new one or "
            "use --resume <ID> to continue an existing session here"
        )
    raise RuntimeSessionNotFoundError(message)


def _load_session(
    config: VibeConfigSchema, session_id: str
) -> tuple[Path, list[LLMMessage], dict[str, object]]:
    session_path = SessionLoader.find_session_by_id(session_id, config.session_logging)
    if session_path is None:
        raise RuntimeSessionNotFoundError(session_id)
    loaded_messages, metadata = SessionLoader.load_session(session_path)
    return session_path, loaded_messages, metadata


def _resolve_resume_session_id(config: VibeConfigSchema, session_id: str) -> str:
    legacy = resolve_legacy_session_reference(session_id, config.session_logging)
    return legacy.session_id if legacy is not None else session_id


def _acquire_session_lease(
    config: VibeConfigSchema, session_id: str
) -> SessionLease | None:
    if not config.session_logging.enabled:
        return None
    return SessionLease(Path(config.session_logging.save_dir), session_id).acquire()


async def _restore_session_active_model(
    orchestrator: ConfigOrchestrator[VibeConfigSchema],
    active_model: str | None,
    *,
    clear_existing: bool = False,
) -> None:
    if active_model is not None:
        failures = await set_session_active_model_override(
            orchestrator, active_model, reason="restore session active model"
        )
    elif clear_existing:
        failures = await clear_session_active_model_override(
            orchestrator, reason="clear previous session active model"
        )
    else:
        return
    if failures:
        raise RuntimeConfigurationError(
            f"Failed to restore session active model: {failures[0]}"
        )


def _parent_session_id(metadata: dict[str, object]) -> str | None:
    value = metadata.get("parent_session_id")
    return value if isinstance(value, str) else None


def _build_stats(loop: AgentLoop, metadata: dict[str, object]) -> AgentStats | None:
    if not isinstance(raw_stats := metadata.get("stats"), dict):
        return None
    stats = AgentStats.model_validate(raw_stats)
    if stats.cached_input_price_per_million is None:
        try:
            stats.cached_input_price_per_million = (
                loop.config.get_active_model().cached_input_price
            )
        except ValueError:
            pass
    return stats


def _apply_stored_stats(loop: AgentLoop, metadata: dict[str, object]) -> None:
    stats = _build_stats(loop, metadata)
    if stats is not None:
        loop.stats = stats


def _messages_for_fork(source: AgentLoop, message_id: str | None) -> list[LLMMessage]:
    messages = [
        message for message in source.messages if message.role is not Role.system
    ]
    if message_id is None:
        return [message.model_copy(deep=True) for message in messages]

    anchor = next(
        (
            index
            for index, message in enumerate(messages)
            if message.message_id == message_id
        ),
        None,
    )
    if anchor is None:
        raise ValueError(f"Cannot fork from unknown message_id: {message_id}")
    if messages[anchor].role is not Role.user:
        raise ValueError("Fork from message_id is only supported for user messages")

    end = next(
        (
            index
            for index, message in enumerate(messages[anchor + 1 :], start=anchor + 1)
            if message.role is Role.user
        ),
        len(messages),
    )
    return [message.model_copy(deep=True) for message in messages[:end]]


async def close_agent_loop(agent_loop: AgentLoop) -> None:
    await agent_loop.aclose()
