from __future__ import annotations

from collections.abc import Callable, MutableMapping
import os
from pathlib import Path
import tomllib
from typing import Annotated, Any, Self

from dotenv import dotenv_values
from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    PrivateAttr,
    model_validator,
)

from vibe.core.agents.models import BuiltinAgentName
from vibe.core.config._defaults import (
    DEFAULT_API_CONNECT_TIMEOUT,
    DEFAULT_API_POOL_TIMEOUT,
    DEFAULT_API_RETRY_MAX_ELAPSED_TIME,
    DEFAULT_API_TIMEOUT,
    DEFAULT_API_WRITE_TIMEOUT,
    DEFAULT_AUTO_COMPACT_THRESHOLD,
    DEFAULT_THEME,
)

# DEFAULT_LOG_LEVEL is not imported here to avoid a circular dependency
# (vibe_schema.py imports from vibe.observability.logging). The constant
# lives in vibe.config_values.
from vibe.core.config.harness_files import get_harness_files_manager
from vibe.core.config.layers.admin import AdminConfigLayer
from vibe.core.config.models import (
    MissingAPIKeyError,
    ModelConfig,
    ProjectContextConfig,
    ProviderConfig,
    SessionLoggingConfig,
    normalize_model_configs,
    serialize_model_configs,
)
from vibe.core.config.schema import (
    ConfigSchema,
    WithConcatMerge,
    WithDeepMerge,
    WithReplaceMerge,
    WithShallowMerge,
    WithUnionMerge,
)
from vibe.core.paths import GLOBAL_ENV_FILE
from vibe.core.prompts import (
    SystemPrompt,
    UtilityPrompt,
    load_prompt,
    load_system_prompt,
)
from vibe.core.types import Backend
from vibe.core.utils.matching import name_matches
from vibe.observability.logging import logger
from vibe.utils.api_keys import resolve_api_key

# Every shell tool scopes a grant with ``build_session_pattern``, which appends
# " *" to mean "any arguments". Allowlists are matched by prefix equality rather
# than as globs, so the wildcard has to come back off before it is persisted or
# the stored entry matches nothing and the next session prompts again. Windows
# spells the shell ``powershell``/``git_bash``, so keying this on ``bash`` alone
# left permanent approvals silently inert there.
_SESSION_PATTERN_WILDCARD_TOOLS = frozenset({"bash", "git_bash", "powershell"})


def _strip_session_pattern_wildcard(pattern: str) -> str:
    if pattern.endswith(" *"):
        return pattern[:-2]
    return pattern


def load_dotenv_values(
    env_path: Path = GLOBAL_ENV_FILE.path,
    environ: MutableMapping[str, str] = os.environ,
) -> None:
    # We allow FIFO path to support some environment management solutions (e.g. https://developer.1password.com/docs/environments/local-env-file/)
    if not env_path.is_file() and not env_path.is_fifo():
        return

    env_vars = dotenv_values(env_path)
    for key, value in env_vars.items():
        if not value:
            continue
        if environ.get(key):
            # An explicit non-empty process/shell value wins over the .env file.
            continue
        environ[key] = value


DEFAULT_PROVIDERS = [
    ProviderConfig(
        name="llamacpp",
        api_base="http://127.0.0.1:8080/v1",
        api_key_env_var="",
        backend=Backend.GENERIC,
    )
]

DEFAULT_ACTIVE_MODEL_CONFIG = ModelConfig(
    name="worker",
    provider="llamacpp",
    alias="local",
    display_name="Local llama.cpp",
    input_price=0.0,
    output_price=0.0,
    cached_input_price=0.0,
)

DEFAULT_MODELS = [DEFAULT_ACTIVE_MODEL_CONFIG]

# Sentinel ``active_model`` value meaning "not pinned": the config resolves it to
# the default model (see ``get_active_model``). Kept distinct from pinning the
# alias that happens to be the current default, which is a deliberate choice.
UNPINNED_ACTIVE_MODEL = ""


def get_persisted_config() -> dict[str, Any]:
    file = get_harness_files_manager().config_file
    if file is None:
        return {}
    try:
        with file.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        raise RuntimeError(f"Invalid TOML in {file}: {e}") from e
    except OSError as e:
        raise RuntimeError(f"Cannot read {file}: {e}") from e


def _unique_by(key: str) -> Callable[[list[Any]], list[Any]]:
    def check(items: list[Any]) -> list[Any]:
        seen: set[str] = set()
        for item in items:
            value = getattr(item, key)
            if value in seen:
                raise ValueError(f"Duplicate {key} {value!r}; must be unique")
            seen.add(value)
        return items

    return check


def _non_empty(items: list[Any]) -> list[Any]:
    if not items:
        raise ValueError(
            "No models are configured. Define at least one model under [[models]]."
        )
    return items


def _expand_paths(v: Any) -> list[Path]:
    if not v:
        return []
    return [Path(p).expanduser().resolve() for p in v]


def _normalize_tool_configs(v: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(v, dict):
        return {}
    return {name: cfg if isinstance(cfg, dict) else {} for name, cfg in v.items()}


_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def _normalize_log_level(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    normalized = value.strip().upper()
    if normalized not in _LOG_LEVELS:
        raise ValueError(
            f"Invalid log level {value!r}; expected one of {sorted(_LOG_LEVELS)}"
        )
    return normalized


class VibeConfigSchema(ConfigSchema):
    _validation_warnings: list[str] = PrivateAttr(default_factory=list)

    @property
    def validation_warnings(self) -> tuple[str, ...]:
        return tuple(self._validation_warnings)

    @classmethod
    def validate_merged(cls, data: dict[str, Any], *, origins: dict[str, str]) -> Self:
        config = super().validate_merged(data, origins=origins)
        # Model validators run before origins are assigned.
        if (
            config.origin_of("allowed_models") == AdminConfigLayer.NAME
            and config.allowed_models
            and not config.available_models()
        ):
            raise ValueError(
                "Admin allowed_models matches none of the configured models."
            )
        if config.origin_of("auto_compact_threshold") != AdminConfigLayer.NAME:
            return config

        models = {
            alias: model.model_copy(
                update={"auto_compact_threshold": config.auto_compact_threshold}
            )
            for alias, model in config.models.items()
        }
        object.__setattr__(config, "models", models)
        return config

    # Models
    active_model: Annotated[str, WithReplaceMerge()] = UNPINNED_ACTIVE_MODEL
    providers: Annotated[list[ProviderConfig], WithUnionMerge(merge_key="name")] = (
        Field(default_factory=lambda: list(DEFAULT_PROVIDERS))
    )
    models: Annotated[
        dict[str, ModelConfig],
        # Keyed by alias internally so per-model patches can deep-merge.
        # Sparse default-model overrides are completed by DefaultConfigLayer at
        # merge time; here we only normalize the list / alias map into the map shape.
        WithDeepMerge(),
        BeforeValidator(normalize_model_configs),
        AfterValidator(_non_empty),
    ] = Field(default_factory=lambda: normalize_model_configs(DEFAULT_MODELS))
    allowed_models: Annotated[list[str], WithReplaceMerge()] = Field(
        default_factory=list,
        description=(
            "An explicit list of model names/patterns to allow. If set, only these"
            " models are selectable. An empty list allows all configured models."
            " Supports glob patterns (e.g., 'mistral-*') and regex with 're:' prefix."
        ),
    )
    compaction_model: Annotated[ModelConfig | None, WithShallowMerge()] = None
    utility_model: Annotated[ModelConfig | None, WithShallowMerge()] = Field(
        default=None,
        description=(
            "Optional model for background utility completions such as session "
            "titles and worktree names. Defaults to the active local model."
        ),
    )
    vision_model: Annotated[ModelConfig | None, WithShallowMerge()] = Field(
        default=None,
        description=(
            "Vision-capable model that describes attached images for an active"
            " model that cannot see them. Only needed to override the default,"
            " which is any vision-capable model on the active model's own"
            " provider; set this to reach a different provider."
        ),
    )
    auto_compact_threshold: Annotated[int, WithReplaceMerge()] = Field(
        default=DEFAULT_AUTO_COMPACT_THRESHOLD,
        description=(
            "Fallback token count before automatic compaction for models that "
            "do not define their own threshold."
        ),
    )

    # Tools
    tools: Annotated[
        dict[str, dict[str, Any]],
        WithDeepMerge(),
        BeforeValidator(_normalize_tool_configs),
    ] = Field(default_factory=dict)
    tool_paths: Annotated[
        list[Path], WithConcatMerge(), BeforeValidator(_expand_paths)
    ] = Field(
        default_factory=list,
        description=(
            "Additional directories or files to explore for custom tools. "
            "Paths may be absolute or relative to the current working directory. "
            "Directories are shallow-searched for tool definition files, "
            "while files are loaded directly if valid."
        ),
    )
    enabled_tools: Annotated[list[str], WithReplaceMerge()] = Field(
        default_factory=list,
        description=(
            "An explicit list of tool names/patterns to enable. If set, only these"
            " tools will be active. Supports glob patterns (e.g., 'serena_*') and"
            " regex with 're:' prefix (e.g., 're:^serena_.*')."
        ),
    )
    disabled_tools: Annotated[list[str], WithConcatMerge()] = Field(
        default_factory=list,
        description=(
            "A list of tool names/patterns to disable after 'enabled_tools' filtering. "
            "Supports glob patterns and regex with 're:' prefix."
        ),
    )

    # Agents
    agent_paths: Annotated[list[Path], WithConcatMerge()] = Field(
        default_factory=list,
        description=(
            "Additional directories to search for custom agent profiles. "
            "Each path may be absolute or relative to the current working directory."
        ),
    )
    enabled_agents: Annotated[list[str], WithConcatMerge()] = Field(
        default_factory=list,
        description=(
            "An explicit list of agent names/patterns to enable. If set, only these"
            " agents will be available. Supports glob patterns (e.g., 'custom-*')"
            " and regex with 're:' prefix."
        ),
    )
    disabled_agents: Annotated[list[str], WithConcatMerge()] = Field(
        default_factory=list,
        description=(
            "A list of agent names/patterns to disable. Ignored if 'enabled_agents'"
            " is set. Supports glob patterns and regex with 're:' prefix."
        ),
    )
    installed_agents: Annotated[list[str], WithConcatMerge()] = Field(
        default_factory=list,
        description=(
            "A list of opt-in builtin agent names that have been explicitly installed."
        ),
    )
    default_agent: Annotated[str, WithReplaceMerge()] = Field(
        default=BuiltinAgentName.ACCEPT_EDITS,
        description=(
            "Agent profile to use when no --agent flag is passed. "
            "Builtin: ask, plan, accept-edits, smart-approve, auto-approve. "
            "Applies in both interactive and programmatic (-p/--prompt) mode."
        ),
    )

    # Skills
    skill_paths: Annotated[
        list[Path], WithConcatMerge(), BeforeValidator(_expand_paths)
    ] = Field(
        default_factory=list,
        description=(
            "Additional directories to search for skills. "
            "Each path may be absolute or relative to the current working directory."
        ),
    )
    enabled_skills: Annotated[list[str], WithConcatMerge()] = Field(
        default_factory=list,
        description=(
            "An explicit list of skill names/patterns to enable. If set, only these"
            " skills will be active. Supports glob patterns (e.g., 'search-*') and"
            " regex with 're:' prefix."
        ),
    )
    disabled_skills: Annotated[list[str], WithConcatMerge()] = Field(
        default_factory=list,
        description=(
            "A list of skill names/patterns to disable. Ignored if 'enabled_skills'"
            " is set. Supports glob patterns and regex with 're:' prefix."
        ),
    )

    # Top-level scalars
    theme: Annotated[str, WithReplaceMerge()] = DEFAULT_THEME
    applied_migrations: Annotated[list[str], WithConcatMerge()] = Field(
        default_factory=list
    )
    disable_welcome_banner_animation: Annotated[bool, WithReplaceMerge()] = False
    show_greeting: Annotated[bool, WithReplaceMerge()] = Field(
        default=True,
        description="Show greeting at startup (Mistral providers only, once per 24h).",
    )
    autocopy_to_clipboard: Annotated[bool, WithReplaceMerge()] = True
    file_watcher_for_autocomplete: Annotated[bool, WithReplaceMerge()] = True
    ask_confirmation_on_exit: Annotated[bool, WithReplaceMerge()] = True
    displayed_workdir: Annotated[str, WithReplaceMerge()] = ""
    context_warnings: Annotated[bool, WithReplaceMerge()] = False
    show_thinking_nodes: Annotated[bool, WithReplaceMerge()] = False
    show_subagent_status_list: Annotated[bool, WithReplaceMerge()] = Field(
        default=True,
        description=(
            "Show the subagent status list and read-only transcript views in the "
            "interactive prompt."
        ),
    )
    worktree_limit: Annotated[int, WithReplaceMerge()] = Field(
        default=15,
        ge=0,
        le=100,
        description="Maximum number of recent managed worktrees kept locally.",
    )
    bypass_tool_permissions: Annotated[bool, WithReplaceMerge()] = False
    raise_on_compaction_failure: Annotated[bool, WithReplaceMerge()] = False
    system_prompt_id: Annotated[str, WithReplaceMerge()] = SystemPrompt.CLI
    managed_shell_tools_enabled: Annotated[bool, WithReplaceMerge()] = False
    compaction_prompt_id: Annotated[str, WithReplaceMerge()] = UtilityPrompt.COMPACT
    include_commit_signature: Annotated[bool, WithReplaceMerge()] = False
    include_model_info: Annotated[bool, WithReplaceMerge()] = True
    include_project_context: Annotated[bool, WithReplaceMerge()] = True
    include_prompt_detail: Annotated[bool, WithReplaceMerge()] = True
    enable_notifications: Annotated[bool, WithReplaceMerge()] = True
    experimental_enable_tab_status: Annotated[bool, WithReplaceMerge()] = True
    enable_system_trust_store: Annotated[bool, WithReplaceMerge()] = False
    api_timeout: Annotated[float, WithReplaceMerge()] = DEFAULT_API_TIMEOUT
    api_retry_max_elapsed_time: Annotated[float, WithReplaceMerge()] = (
        DEFAULT_API_RETRY_MAX_ELAPSED_TIME
    )
    api_connect_timeout: Annotated[float, WithReplaceMerge()] = (
        DEFAULT_API_CONNECT_TIMEOUT
    )
    api_write_timeout: Annotated[float, WithReplaceMerge()] = DEFAULT_API_WRITE_TIMEOUT
    api_pool_timeout: Annotated[float, WithReplaceMerge()] = DEFAULT_API_POOL_TIMEOUT
    log_level: Annotated[
        str | None, WithReplaceMerge(), BeforeValidator(_normalize_log_level)
    ] = None

    # Nested configs: a bag of independent settings, so a layer overrides only
    # the keys it names. Shallow rather than deep on purpose -- these are flat
    # scalars today, and deep merging would silently extend per-key merging to
    # the first dict-valued setting anyone adds, where a user could then shadow
    # an inherited key but never remove it.
    project_context: Annotated[ProjectContextConfig, WithShallowMerge()] = Field(
        default_factory=ProjectContextConfig
    )
    session_logging: Annotated[SessionLoggingConfig, WithShallowMerge()] = Field(
        default_factory=SessionLoggingConfig
    )

    def smart_approve_offered(self) -> bool:
        """Smart approval is a deterministic local agent mode, not an experiment."""
        return True

    def resolve_default_agent(self) -> str:
        return self.default_agent

    def resolve_default_model_alias(self) -> str:
        available = self.available_models()
        if DEFAULT_ACTIVE_MODEL_CONFIG.alias in available or not available:
            return DEFAULT_ACTIVE_MODEL_CONFIG.alias
        return next(iter(available))

    def available_models(self) -> dict[str, ModelConfig]:
        if not self.allowed_models:
            return self.models
        allowed = {
            alias: model
            for alias, model in self.models.items()
            if name_matches(model.name, self.allowed_models)
        }
        # Any configured allowlist is a security boundary in the local fork.
        # If it matches nothing, return an empty set rather than silently
        # widening access back to every configured model (including cloud
        # defaults that may still exist during the cleanup).
        return allowed

    def get_active_model(self) -> ModelConfig:
        if self.active_model and self.active_model not in self.models:
            raise ValueError(
                f"Active model '{self.active_model}' not found in configuration."
            )
        # An allowlist-excluded pin never runs: fall back to the default allowed model.
        available = self.available_models()
        alias = (
            self.active_model
            if self.active_model in available
            else self.resolve_default_model_alias()
        )
        if model := available.get(alias):
            return model
        raise ValueError(
            f"Active model '{self.active_model}' not found in configuration."
        )

    def get_provider_for_model(self, model: ModelConfig) -> ProviderConfig:
        if provider := next(
            (p for p in self.providers if p.name == model.provider), None
        ):
            return provider
        raise ValueError(
            f"Provider '{model.provider}' for model '{model.name}' not found in configuration."
        )

    def get_compaction_model(self) -> ModelConfig:
        if self.compaction_model is not None:
            return self.compaction_model
        return self.get_active_model()

    def get_vision_fallback_model(self) -> ModelConfig | None:
        try:
            active = self.get_active_model()
        except ValueError:
            return self.vision_model
        # Describing an image the model is about to receive anyway only loses
        # detail.
        if active.supports_images:
            return None
        if self.vision_model is not None:
            return self.vision_model
        # Same provider means same key and same endpoint, so a blind model
        # picks up vision with no config and no image leaves where the session
        # was already talking. Crossing providers stays the user's call.
        return next(
            (
                model
                for model in self.available_models().values()
                if model.supports_images and model.provider == active.provider
            ),
            None,
        )

    def get_active_provider(self) -> ProviderConfig:
        return self.get_provider_for_model(self.get_active_model())

    def require_active_provider_api_key(self) -> None:
        try:
            provider = self.get_active_provider()
        except ValueError:
            return
        api_key_env = provider.api_key_env_var
        if api_key_env and not resolve_api_key(api_key_env):
            raise MissingAPIKeyError(api_key_env, provider.name)

    def build_tool_allowlist_update(
        self,
        tool_name: str,
        patterns: list[str],
        *,
        current_allowlist: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Extend a tool's allowlist in memory and return the persist payload.

        Returns ``None`` when every pattern is already allowlisted. Callers
        persist the returned payload; the in-memory config is kept current so
        repeated calls merge from fresh state.
        """
        if tool_name in _SESSION_PATTERN_WILDCARD_TOOLS:
            patterns = [_strip_session_pattern_wildcard(p) for p in patterns]
        allowlist: list[str] = list(
            current_allowlist
            if current_allowlist is not None
            else self.tools.get(tool_name, {}).get("allowlist", [])
        )
        new_patterns = [p for p in patterns if p not in allowlist]
        if not new_patterns:
            return None
        merged = sorted(allowlist + new_patterns)
        self.tools.setdefault(tool_name, {})["allowlist"] = merged
        return {"tools": {tool_name: {"allowlist": merged}}}

    @property
    def system_prompt(self) -> str:
        return load_system_prompt(self.system_prompt_id)

    @property
    def compaction_prompt(self) -> str:
        return load_prompt(
            self.compaction_prompt_id,
            setting_name="compaction_prompt_id",
            builtins={"compact": UtilityPrompt.COMPACT.path},
        )

    @model_validator(mode="after")
    def _apply_global_auto_compact_threshold(self) -> VibeConfigSchema:
        models = {
            alias: (
                model
                if "auto_compact_threshold" in model.model_fields_set
                else model.model_copy(
                    update={"auto_compact_threshold": self.auto_compact_threshold}
                )
            )
            for alias, model in self.models.items()
        }
        object.__setattr__(self, "models", models)
        return self

    @model_validator(mode="after")
    def _apply_active_model_fallback(self) -> VibeConfigSchema:
        # The empty string is the "unpinned/default" sentinel: it is always valid
        # and resolves to a configured model at read time (get_active_model).
        if self.active_model and self.active_model not in self.models:
            unknown = self.active_model
            fallback = self.resolve_default_model_alias()
            logger.warning(
                "Active model '%s' is not in your configured models; "
                "falling back to default model '%s'.",
                unknown,
                fallback,
            )
            self._validation_warnings.append(
                f"Active model '{unknown}' is not in your configured models "
                f"— falling back to default model '{fallback}'."
            )
            object.__setattr__(self, "active_model", UNPINNED_ACTIVE_MODEL)
        return self

    @model_validator(mode="after")
    def _warn_unmatched_allowed_models(self) -> VibeConfigSchema:
        for pattern in self.allowed_models:
            if not (pattern or "").strip():
                continue
            if any(
                name_matches(model.name, [pattern]) for model in self.models.values()
            ):
                continue
            logger.warning(
                "Allowed model '%s' matches none of your configured models.", pattern
            )
            self._validation_warnings.append(
                f"Allowed model '{pattern}' matches none of your configured models."
            )
        return self

    @model_validator(mode="after")
    def _warn_disallowed_active_model(self) -> VibeConfigSchema:
        if not self.active_model or self.active_model in self.available_models():
            return self
        fallback = self.resolve_default_model_alias()
        logger.warning(
            "Active model '%s' is excluded by allowed_models; "
            "falling back to default model '%s'.",
            self.active_model,
            fallback,
        )
        self._validation_warnings.append(
            f"Active model '{self.active_model}' is excluded by allowed_models "
            f"— falling back to default model '{fallback}'."
        )
        return self

    @model_validator(mode="after")
    def _check_compaction_model_provider(self) -> VibeConfigSchema:
        if self.compaction_model is None:
            return self

        compaction_provider = self.get_provider_for_model(self.compaction_model)
        try:
            active_provider = self.get_provider_for_model(self.get_active_model())
        except ValueError:
            return self
        if active_provider.name != compaction_provider.name:
            # Cross-provider compaction is intentional on local multi-worker
            # setups: the summary runs on the secondary worker (thinking off)
            # while token usage stays accounted through the loop. Warn instead
            # of raising so the deliberate offload is not blocked.
            logger.warning(
                "Compaction model '%s' runs on provider '%s' while the active "
                "model uses provider '%s'.",
                self.compaction_model.alias,
                compaction_provider.name,
                active_provider.name,
            )
            self._validation_warnings.append(
                f"Compaction model '{self.compaction_model.alias}' runs on provider "
                f"'{compaction_provider.name}' instead of the active model's "
                f"'{active_provider.name}' — prompts will not share a cache."
            )
        return self

    @model_validator(mode="after")
    def _check_vision_model(self) -> VibeConfigSchema:
        if self.vision_model is None:
            return self
        if not self.vision_model.supports_images:
            raise ValueError(
                f"Vision model '{self.vision_model.alias}' must set "
                "supports_images = true."
            )
        # Deliberately no same-provider check, unlike `compaction_model`:
        # crossing providers is the whole point of setting this, and the
        # description is a standalone completion on its own backend.
        self.get_provider_for_model(self.vision_model)
        return self

    @model_validator(mode="after")
    def _check_system_prompt(self) -> VibeConfigSchema:
        _ = self.system_prompt
        return self

    @model_validator(mode="after")
    def _check_compaction_prompt(self) -> VibeConfigSchema:
        _ = self.compaction_prompt
        return self


def create_default_config() -> dict[str, Any]:
    from vibe.core.tools.manager import ToolManager

    config_dict = VibeConfigSchema.model_construct().model_dump(
        mode="json", exclude_none=True
    )
    if isinstance(config_dict.get("models"), dict):
        config_dict["models"] = serialize_model_configs(config_dict["models"])
    if tool_defaults := ToolManager.discover_tool_defaults():
        config_dict["tools"] = tool_defaults
    return config_dict
