from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
import stat
import threading
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

from pydantic import JsonValue, ValidationError

from vibe import __version__
from vibe.app_server._host import HostRequestHandler
from vibe.app_server._projection import (
    project_config_view,
    project_skill_summaries,
    project_unified_agent_summaries,
)
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
from vibe.app_server.connector_catalog import (
    ConnectorCatalogError,
    ConnectorCatalogService,
)
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
    SessionMCPHttpServer,
    SessionMCPServer,
    SessionMCPStdioServer,
    SessionOptions,
    TransportKind,
)
from vibe.app_server.transport import JsonRpcTransport, memory_transport_pair
from vibe.core.agent_loop import AgentLoop, AgentRuntimePolicy
from vibe.core.agents.manager import AgentManager
from vibe.core.agents.models import AgentProfile
from vibe.core.config import (
    MCPHttp,
    MCPServer,
    MCPStaticAuth,
    MCPStdio,
    MCPStreamableHttp,
    MissingAPIKeyError,
    SessionLoggingConfig,
    VibeConfigSchema,
    build_default_orchestrator,
    resolve_api_key,
)
from vibe.core.config.harness_files import HarnessFilesManager
from vibe.core.config.layers.growthbook import GrowthbookLayer
from vibe.core.config.layers.overrides import OverridesLayer
from vibe.core.config.orchestrator import ConfigOrchestrator
from vibe.core.experiments.cache import load_cached_eval_response
from vibe.core.experiments.manager import config_variants_from_response
from vibe.core.experiments.models import EvalResponse
from vibe.core.hooks.config import load_hooks_file, load_hooks_from_fs
from vibe.core.hooks.models import HookConfigResult
from vibe.core.paths import VIBE_HOME, WORKTREES_DIR
from vibe.core.session import last_session_pointer
from vibe.core.session.session_id import extract_suffix, generate_session_id
from vibe.core.session.session_index import warm_session_index
from vibe.core.session.session_interop import resolve_legacy_session_reference
from vibe.core.session.session_lease import SessionLease
from vibe.core.session.session_loader import SessionLoader
from vibe.core.session.session_permissions import start_restrict_session_log_permissions
from vibe.core.system_prompt import ProjectContextProvider
from vibe.core.telemetry.build_metadata import build_launch_context
from vibe.core.tools.models import ToolPermission
from vibe.core.tools.permissions import PermissionStore
from vibe.core.tracing import setup_tracing
from vibe.core.types import AgentStats, LLMMessage, Role, SessionMetadata
from vibe.core.utils import get_windows_bash_path, is_windows
from vibe.core.utils.matching import name_matches
from vibe.observability.logging import logger, set_config_log_level
from vibe.utils.cache_store import FileSystemCacheStore
from vibe.utils.http import get_server_url_from_api_base
from vibe.utils.paths import is_dangerous_directory

_SHORT_SESSION_ID_LENGTH = 8
_PUBLIC_MISTRAL_API_ORIGIN = ("https", "api.mistral.ai", 443)
type _CommandEnvironmentMode = Literal["unix", "git_bash", "powershell"]


def _command_environment_mode() -> _CommandEnvironmentMode:
    if not is_windows():
        return "unix"
    if get_windows_bash_path() is not None:
        return "git_bash"
    return "powershell"


def _is_public_mistral_api(api_base: str) -> bool:
    parsed = urlsplit(api_base)
    try:
        port = parsed.port
    except ValueError:
        return False
    effective_port = 443 if port is None and parsed.scheme.lower() == "https" else port
    origin = (parsed.scheme.lower(), (parsed.hostname or "").lower(), effective_port)
    return origin == _PUBLIC_MISTRAL_API_ORIGIN


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
    from vibe.app_server._account import AccountGateway
    from vibe.app_server._identity import IdentityGateway
    from vibe.app_server._mcp_auth import MCPAuthenticationService
    from vibe.app_server._plugin_mcp import PluginMCPCatalog
    from vibe.app_server._session_backend_port import ResolvedMCPCatalog
    from vibe.app_server.server import AppServer
    from vibe.core.tools.connectors.connector_registry import ConnectorRegistry
    from vibe.core.tools.mcp.registry import MCPRegistry


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
class _ImportedSession:
    session_id: str
    cwd: str | None
    root_session_id: str
    parent_session_id: str | None
    messages: list[LLMMessage]
    provenance: dict[str, JsonValue]
    active_model: str | None = None


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
    experiment_state: EvalResponse | None = None
    await_experiment_model: bool = False
    mcp_registry: MCPRegistry | None = None
    connector_registry: ConnectorRegistry | None = None

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
            mcp_registry=self.mcp_registry,
            connector_registry=self.connector_registry,
            cache_store=self.policy.cache_store,
            force_bypass_tool_permissions=self.policy.force_bypass_tool_permissions,
            local_managed_shell_runtime_enabled=(
                self.policy.local_managed_shell_runtime_enabled
            ),
            auto_title_enabled=self.policy.auto_title_enabled,
            experiment_state=self.experiment_state,
            await_experiment_model=self.await_experiment_model,
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
    mcp_registry: MCPRegistry | None = None
    connector_registry: ConnectorRegistry | None = None

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
        cached = load_cached_eval_response(self.config)
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
            experiment_state=cached,
            await_experiment_model=cached is None and session_id is None,
            mcp_registry=self.mcp_registry,
            connector_registry=self.connector_registry,
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
        """Finish a resume: await deferred init, then hydrate experiments.

        Called after the ``session/resume`` RPC response is sent so the client
        can render the transcript while MCP/connector init completes in the
        background. Both steps are best-effort: the rebind already committed, so
        a deferred-init or hydration failure must not abort the caller before it
        emits ``runtime/updated`` — the degraded state (e.g. MCP discovery
        errors) is carried in the runtime snapshot instead.

        Init-duration recording lives in ``wait_until_ready`` via
        ``_ensure_init_duration_recorded``, not here.
        """
        try:
            await source._await_deferred_init()
        except Exception:
            logger.exception(
                "Deferred init failed after resuming session_id=%s", session_id
            )
        try:
            await source.hydrate_experiments_from_session()
        except Exception:
            logger.exception(
                "Failed to hydrate experiments after resuming session_id=%s", session_id
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
            # refresh_prompt=False: deferred init hasn't completed yet (git, MCP),
            # so refresh_system_prompt() — gated by @requires_init — would block.
            # The background thread updates the system prompt once init finishes,
            # same as a fresh session start.
            await replacement.hydrate_experiments_from_session(refresh_prompt=False)
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
            # refresh_prompt=False for the same reason as resume_blueprint: the child's
            # deferred init hasn't run yet, so @requires_init would block here.
            await child.hydrate_experiments_from_session(refresh_prompt=False)
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
            experiment_state=source.experiment_manager.export_state(),
            mcp_registry=(
                source.mcp_registry.clone_configuration()
                if source.mcp_registry is not None
                else None
            ),
            connector_registry=(
                source.connector_registry.clone_configuration()
                if source.connector_registry is not None
                else None
            ),
        ).build()
        return replacement


class HarnessProcess:
    def __init__(self, harness_files: HarnessFilesManager | None = None) -> None:
        from vibe.app_server._mcp_auth import MCPAuthenticationService
        from vibe.app_server.mcp_catalog import MCPCatalogService
        from vibe.app_server.plugin_catalog import PluginCatalogService

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
        self.host_handler = HostRequestHandler(self.harness_files)
        self.mcp_authentication = MCPAuthenticationService()
        self.mcp_catalog = MCPCatalogService(
            self.mcp_authentication,
            sessionless_catalog_factory=self.build_sessionless_mcp_catalog,
        )
        self.connector_catalog = ConnectorCatalogService(
            implicit_source_enabled=False,
            sessionless_catalog_factory=self.build_sessionless_mcp_catalog,
        )
        self.plugin_catalog = PluginCatalogService()

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
            mcp_catalog_service=self.mcp_catalog,
            connector_catalog_service=self.connector_catalog,
            account_gateway=services.account_gateway(),
            identity_gateway=services.identity_gateway(),
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

    async def build_sessionless_mcp_catalog(
        self,
    ) -> ConfigOrchestrator[VibeConfigSchema]:
        session_config = await self._build_session_config(SessionOptions())
        return session_config.config_orchestrator

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
        await _apply_cached_experiment_variants(config_orchestrator)
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
            mcp_registry=await self._build_legacy_mcp_registry(config_orchestrator),
            connector_registry=await self._build_connector_registry(
                config_orchestrator
            ),
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

    async def _build_legacy_mcp_registry(
        self, orchestrator: ConfigOrchestrator[VibeConfigSchema]
    ) -> MCPRegistry:
        from vibe.app_server._legacy_session_backend import (
            configure_legacy_mcp_registry,
        )
        from vibe.core.tools.mcp.registry import MCPRegistry

        # Bound in the registry's name, not the orchestrator's: this is the
        # blueprint's orchestrator and the session's loop is handed a copy of
        # it, so nothing holds this one once the blueprint has been consumed,
        # while the registry it arms here goes on resolving through the
        # binding. The registry is how long that binding is needed for.
        registry = MCPRegistry()
        configuration = await self.mcp_catalog.resolve_catalog(
            orchestrator, owner=registry
        )
        cache_root = (
            Path(orchestrator.config.session_logging.save_dir)
            .expanduser()
            .resolve()
            .parent
            / "mcp-descriptors"
            / "legacy"
        )
        configure_legacy_mcp_registry(
            registry,
            configuration,
            self.mcp_authentication,
            descriptor_cache_root=cache_root,
        )
        return registry

    async def _build_connector_registry(
        self, orchestrator: ConfigOrchestrator[VibeConfigSchema]
    ) -> ConnectorRegistry | None:
        from vibe.core.tools.connectors.connector_registry import (
            ConnectorAuthAction,
            ConnectorCatalogEntry,
            ConnectorRegistry,
            ConnectorToolDefinition,
        )

        provider = orchestrator.config.get_mistral_provider()
        if provider is None:
            return None
        api_key_env = provider.api_key_env_var or "MISTRAL_API_KEY"
        api_key = resolve_api_key(api_key_env)
        if not api_key:
            return None
        server_url = get_server_url_from_api_base(provider.api_base)
        try:
            catalog = await self.connector_catalog.resolve_catalog(orchestrator)
        except ConnectorCatalogError:
            logger.warning("Connector catalog is unavailable during session startup")
            catalog = None
        entries = (
            tuple(
                ConnectorCatalogEntry(
                    connector_id=connector.raw_id,
                    alias=connector.alias,
                    display_name=connector.display_name,
                    ready=connector.ready,
                    auth_action=(
                        ConnectorAuthAction(connector.auth_action)
                        if connector.auth_action != "unknown"
                        else ConnectorAuthAction.NONE
                    ),
                    tools=tuple(
                        ConnectorToolDefinition(
                            name=tool.raw_name,
                            description=tool.description,
                            input_schema=dict(tool.input_schema),
                        )
                        for tool in connector.tools
                    ),
                    diagnostic="; ".join(connector.diagnostics) or None,
                )
                for connector in catalog.connectors
            )
            if catalog is not None
            else ()
        )
        return ConnectorRegistry(
            api_key=api_key, server_url=server_url, catalog_entries=entries
        )

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


async def create_harness_server(
    transport: JsonRpcTransport,
    *,
    transport_kind: TransportKind,
    process: HarnessProcess | None = None,
    account_gateway: AccountGateway | None = None,
    identity_gateway: IdentityGateway | None = None,
) -> HarnessServer:
    """Build a server over ``transport``.

    ``account_gateway``/``identity_gateway`` reach the platform API and are left
    unset in production, where ``AppServer`` builds the HTTP ones. They exist so
    a test can drive the account and identity surfaces over either backend
    without a network.
    """
    from vibe.app_server.server import AppServer

    process = process or HarnessProcess()
    return HarnessServer(
        _server=AppServer(
            transport,
            transport_kind=transport_kind,
            host_handler=process.host_handler,
            session_backend_host_factory=process.create_session_backend_host,
            mcp_catalog_service=process.mcp_catalog,
            connector_catalog_service=process.connector_catalog,
            plugin_catalog_service=process.plugin_catalog,
            account_gateway=account_gateway,
            identity_gateway=identity_gateway,
        ),
        _transport=transport,
        _reconnectable=transport_kind == "in_process",
    )


def _hook_config_issues(result: HookConfigResult) -> list[ConfigIssue]:
    """Project hooks.toml parse/duplicate diagnostics onto the session's issues.

    ``load_hooks_from_fs`` skips an invalid or conflicting file's hooks and records why
    on ``result.issues``. Surfacing them as session notices (rather than dropping them
    silently) matches the legacy loop, which projects ``hook_config_issues``, and the
    design's failure table ("CLI logs a diagnostic; that file's hooks are skipped").
    """
    return [
        ConfigIssue(file=str(issue.file), message=issue.message)
        for issue in result.issues
    ]


def _user_hook_names(harness_files: HarnessFilesManager) -> set[str]:
    """Names of hooks that come from ``~/.vibe/hooks.toml``, after project-first dedup.

    ``load_hooks_from_fs`` merges project and user files (project first) and drops the
    origin, so recover it here: a surviving hook is user-owned only when it is declared in
    the user file and by no project file.
    """
    user_file = (VIBE_HOME.path / "hooks.toml").resolve()
    project_names: set[str] = set()
    user_names: set[str] = set()
    for path in harness_files.hook_files:
        names = {hook.name for hook in load_hooks_file(path).hooks}
        if path.resolve() == user_file:
            user_names |= names
        else:
            project_names |= names
    return user_names - project_names


def _foreign_hook_definitions(
    result: HookConfigResult, *, harness_files: HarnessFilesManager, cwd: Path
) -> list[Any]:
    """Map discovered project/user hook declarations to harness hook definitions.

    Consumes ``result.hooks`` (the parsed ``[[hooks]]`` from ``hooks.toml``), the
    same field the legacy loop uses -- not ``result.runtime_hooks``, which only the
    plugin loader populates.

    ``source`` scopes the binding id (``f"{source}:{name}"``). A user hook is labelled
    ``"user"`` and a project hook the session cwd, so a persisted project binding cannot be
    matched by a same-named user hook on a resume where project trust has since been lost.
    """
    from mistralai_vibe_local_harness.vibe import ForeignHookDefinition

    user_names = _user_hook_names(harness_files)
    cwd_source = str(cwd)

    return [
        ForeignHookDefinition(
            name=hook.name,
            point=hook.type.value,
            command=hook.command,
            source="user" if hook.name in user_names else cwd_source,
            match=hook.match,
            order=index,
            timeout_s=hook.timeout if hook.timeout is not None else 60.0,
            strict=hook.strict,
        )
        for index, hook in enumerate(result.hooks)
    ]


def build_runtime_snapshot(
    options: SessionOptions,
    config_orchestrator: ConfigOrchestrator[VibeConfigSchema],
    harness_files: HarnessFilesManager,
    *,
    issues: Sequence[ConfigIssue] = (),
) -> RuntimeSnapshot:
    config = config_orchestrator.config
    agents = AgentManager(
        config_orchestrator,
        options.agent or config.resolve_default_agent(),
        harness_files=harness_files,
    )
    active_model = config.get_active_model()
    active, available = project_unified_agent_summaries(
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
        skills=project_skill_summaries(()),
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
    )


def merge_plugin_mcp_into_catalog(
    catalog: ResolvedMCPCatalog,
    plugin_mcp: PluginMCPCatalog,
    *,
    authentication: MCPAuthenticationService,
) -> ResolvedMCPCatalog:
    """Merge plugin-owned MCP servers the harness can run into a config catalog.

    A plugin source whose name a configured server already owns is skipped, so
    the harness runs the config entry. The plugin server's name never reaches
    the merged catalog, and ``plugin_owned_names`` reflects that.
    """
    from vibe.app_server._session_backend_port import (
        ResolvedMCPCatalog as _ResolvedMCPCatalog,
        ResolvedMCPServerConfig,
    )
    from vibe.core.config import MCPStdio

    configured_names = frozenset(server.name for server in catalog.servers)
    plugin_servers: list[ResolvedMCPServerConfig] = []
    for source in plugin_mcp.sources():
        if source.name in configured_names:
            continue
        server = source.entry.server
        reference = authentication.reference_for(server, owner="plugin")
        if isinstance(server, MCPStdio):
            argv = server.argv()
            plugin_servers.append(
                ResolvedMCPServerConfig(
                    name=source.name,
                    transport="stdio",
                    url=None,
                    command=argv[0] if argv else None,
                    args=tuple(argv[1:]),
                    cwd=(
                        Path(server.cwd).expanduser().resolve() if server.cwd else None
                    ),
                    env=server.env,
                    authorization=reference,
                    prompt=server.prompt,
                    startup_timeout_s=server.startup_timeout_sec,
                    tool_timeout_s=server.tool_timeout_sec,
                    sampling_enabled=server.sampling_enabled,
                    disabled=server.disabled,
                    disabled_tools=frozenset(server.disabled_tools),
                )
            )
        else:
            plugin_servers.append(
                ResolvedMCPServerConfig(
                    name=source.name,
                    transport=server.transport,
                    url=server.url,
                    command=None,
                    args=(),
                    cwd=None,
                    env={},
                    authorization=reference,
                    prompt=server.prompt,
                    startup_timeout_s=server.startup_timeout_sec,
                    tool_timeout_s=server.tool_timeout_sec,
                    sampling_enabled=server.sampling_enabled,
                    disabled=server.disabled,
                    disabled_tools=frozenset(server.disabled_tools),
                )
            )
    if not plugin_servers:
        return catalog
    all_servers = (*catalog.servers, *plugin_servers)
    payload = [
        {
            "name": server.name,
            "transport": server.transport,
            "url": server.url,
            "command": server.command,
            "args": list(server.args),
            "cwd": str(server.cwd) if server.cwd is not None else None,
            "env": dict(server.env),
            "authorization": {
                "server_name": server.authorization.server_name,
                "server_fingerprint": server.authorization.server_fingerprint,
                "kind": server.authorization.kind,
                "owner": server.authorization.owner,
            },
            "prompt": server.prompt,
            "startup_timeout_s": server.startup_timeout_s,
            "tool_timeout_s": server.tool_timeout_s,
            "sampling_enabled": server.sampling_enabled,
            "disabled": server.disabled,
            "disabled_tools": sorted(server.disabled_tools),
        }
        for server in all_servers
    ]
    revision = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return _ResolvedMCPCatalog(revision=revision, servers=all_servers)


def plugin_owned_names(catalog: ResolvedMCPCatalog) -> frozenset[str]:
    """Names in a merged catalog that a plugin owns, not a config entry.

    Derived from the catalog the harness was actually configured with, so a
    name a configured server won is absent here even though a plugin source
    declared it. This is the set the authorization adapter needs to route
    ``owner`` on references the harness sends back.
    """
    return frozenset(
        server.name
        for server in catalog.servers
        if server.authorization.owner == "plugin"
    )


_RUST_BUILTIN_TOOL_SOURCES: dict[str, frozenset[str]] = {
    "file_system.read_file": frozenset({"read_file"}),
    "file_system.write_file": frozenset({"write_file"}),
    "file_system.search_replace": frozenset({"edit"}),
    "file_system.bash": frozenset({"bash", "powershell", "git_bash"}),
    "skill.read": frozenset({"skill"}),
}

_RUST_MODE_BY_PERMISSION: dict[ToolPermission, Literal["allow", "ask", "deny"]] = {
    ToolPermission.ALWAYS: "allow",
    ToolPermission.ASK: "ask",
    ToolPermission.NEVER: "deny",
}

_PERMISSION_STRICTNESS: tuple[ToolPermission, ...] = (
    ToolPermission.NEVER,
    ToolPermission.ASK,
    ToolPermission.ALWAYS,
)


def rust_agent_tool_ceiling(
    available_tools: set[str],
    permission_of: Callable[[str], ToolPermission],
    overrides: Mapping[str, Any],
) -> dict[str, Literal["allow", "ask", "deny"]]:
    # A ceiling, never a grant: the Runtime keeps the stricter of this and the mode
    # the parent holds, so the worst a wrong answer here does is deny a child
    # something it was allowed. ``allowlist``/``denylist`` are not carried as patterns
    # -- they are per-call path and command policy only Vibe's live resolver can
    # answer, and the child runs under that resolver holding the parent's
    # configuration rather than a snapshot of the profile's. They still change the
    # answer: a profile that would hand the child an unconditional ``allow`` while
    # relying on a list to keep that grant narrow is capped at ``ask`` instead, so
    # the calls the list was there to restrain reach the user (see
    # ``agent_ceiling_downgrades``).
    narrowed = _profile_tools(available_tools, overrides)
    per_tool = overrides.get("tools")
    per_tool = per_tool if isinstance(per_tool, Mapping) else {}

    def permission(name: str) -> ToolPermission:
        resolved = _declared_permission(per_tool.get(name), name, permission_of)
        if resolved is ToolPermission.ALWAYS and _list_narrowed(per_tool.get(name)):
            return ToolPermission.ASK
        return resolved

    # The ceiling encodes what the profile *permits* (allow/ask/deny), not what the
    # session's approval mode would do. The Runtime takes the stricter of this and
    # the parent's mode, so ``allow`` here is safe: under PROMPT the parent's
    # ``ask`` is stricter and the resolver still runs; under BYPASS the parent's
    # ``allow`` lets the child bypass -- the user's explicit choice, not something
    # a plugin profile can grant on its own. A ceiling never classifies.
    ceiling: dict[str, Literal["allow", "ask", "deny"]] = {}
    for builtin, sources in _RUST_BUILTIN_TOOL_SOURCES.items():
        present = sources & narrowed
        if not present:
            ceiling[builtin] = "deny"
        else:
            permissions = {permission(name) for name in present}
            strictest = next(
                perm for perm in _PERMISSION_STRICTNESS if perm in permissions
            )
            ceiling[builtin] = _RUST_MODE_BY_PERMISSION[strictest]
    ceiling["process.start"] = ceiling["file_system.bash"]
    for builtin in ("process.output", "process.write", "process.list", "process.stop"):
        ceiling[builtin] = "allow"
    return ceiling


def agent_ceiling_downgrades(
    available_tools: set[str],
    permission_of: Callable[[str], ToolPermission],
    overrides: Mapping[str, Any],
) -> tuple[str, ...]:
    """Tools whose profile narrowing ``rust_agent_tool_ceiling`` cannot express.

    A ceiling says allow, ask, or deny per tool. It cannot say "bash, but only
    these commands", and the resolver that can runs against the parent's
    configuration rather than the child's profile. A profile that grants a tool
    outright while relying on a list to keep the grant narrow is therefore capped
    at ``ask``. Returned so a caller can tell the user which tools that happened
    to, and that their narrowing is approximated rather than enforced.
    """
    per_tool = overrides.get("tools")
    if not isinstance(per_tool, Mapping):
        return ()
    return tuple(
        sorted(
            name
            for name in _profile_tools(available_tools, overrides)
            if _list_narrowed(per_tool.get(name))
            and _declared_permission(per_tool.get(name), name, permission_of)
            is ToolPermission.ALWAYS
        )
    )


def _profile_tools(available_tools: set[str], overrides: Mapping[str, Any]) -> set[str]:
    enabled = _glob_patterns(overrides.get("enabled_tools"))
    disabled = _glob_patterns(overrides.get("disabled_tools"))
    return {
        name
        for name in available_tools
        if (not enabled or name_matches(name, enabled))
        and not (disabled and name_matches(name, disabled))
    }


def _declared_permission(
    entry: Any, name: str, permission_of: Callable[[str], ToolPermission]
) -> ToolPermission:
    declared = entry.get("permission") if isinstance(entry, Mapping) else None
    if not isinstance(declared, str):
        return permission_of(name)
    try:
        return ToolPermission(declared)
    except ValueError:
        return permission_of(name)


def _list_narrowed(entry: Any) -> bool:
    if not isinstance(entry, Mapping):
        return False
    return any(
        isinstance(entry.get(key), list) and entry.get(key)
        for key in ("allowlist", "denylist")
    )


def _glob_patterns(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, str)]


def _project_session_mcp_server(server: SessionMCPServer) -> MCPServer:
    match server:
        case SessionMCPHttpServer(transport="http"):
            return MCPHttp(
                transport="http",
                name=server.name,
                url=server.url,
                auth=MCPStaticAuth(headers=server.headers),
            )
        case SessionMCPHttpServer(transport="streamable-http"):
            return MCPStreamableHttp(
                transport="streamable-http",
                name=server.name,
                url=server.url,
                auth=MCPStaticAuth(headers=server.headers),
            )
        case SessionMCPStdioServer():
            return MCPStdio(
                transport="stdio",
                name=server.name,
                # The session protocol already separates the executable from its args.
                command=[server.command],
                args=server.args,
                env=server.env,
                cwd=server.cwd,
            )
        case _:
            raise TypeError(f"Unsupported session MCP server: {type(server).__name__}")


async def _apply_cached_experiment_variants(
    config_orchestrator: ConfigOrchestrator[VibeConfigSchema],
) -> None:
    """Apply the last cached experiment variants to config before first render."""
    cached = load_cached_eval_response(config_orchestrator.config)
    if cached is None:
        return
    variants = config_variants_from_response(cached)
    if not variants:
        return
    try:
        layer = config_orchestrator.get_layer(GrowthbookLayer.NAME)
    except KeyError:
        return
    if isinstance(layer, GrowthbookLayer):
        layer.set_variants(variants)
        await config_orchestrator.reload()


def _session_config_overrides(options: SessionOptions) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if options.enabled_tools is not None:
        overrides["enabled_tools"] = options.enabled_tools
    if options.disabled_tools:
        overrides["disabled_tools"] = options.disabled_tools
    if options.mcp_servers:
        overrides["mcp_servers"] = [
            _project_session_mcp_server(server).model_dump(
                mode="json", exclude_none=True
            )
            for server in options.mcp_servers
        ]
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
    if legacy is not None:
        return legacy.session_id
    return session_id


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
    errors: list[BaseException] = []
    for cleanup in (agent_loop.aclose, agent_loop.telemetry_client.aclose):
        try:
            await cleanup()
        except BaseException as exc:
            errors.append(exc)
    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise BaseExceptionGroup("Failed to close agent runtime", errors)
