from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibe.core.config._defaults import (
        AUTO_THEME,
        DEFAULT_API_RETRY_MAX_ELAPSED_TIME,
        DEFAULT_API_TIMEOUT,
        DEFAULT_AUTO_COMPACT_THRESHOLD,
        DEFAULT_THEME,
        FALLBACK_THEME,
    )
    from vibe.core.config.default_orchestrator import (
        build_default_orchestrator,
        build_user_config_orchestrator,
    )
    from vibe.core.config.layer import (
        ConfigLayer,
        ConfigLayerError,
        ConfigPatchApplicationError,
        EmptyLayerError,
        LayerImplementationError,
        LayerNotLoadedError,
        RawConfig,
        TrustResolutionError,
        UntrustedLayerError,
    )
    from vibe.core.config.layers.agent_profile import AgentProfileLayer
    from vibe.core.config.layers.default import DefaultConfigLayer
    from vibe.core.config.layers.discovered import DiscoveredConfigLayer
    from vibe.core.config.models import (
        THINKING_LEVELS,
        ConnectorConfig,
        MCPHttp,
        MCPOAuth,
        MCPServer,
        MCPStaticAuth,
        MCPStdio,
        MCPStreamableHttp,
        MissingAPIKeyError,
        ModelConfig,
        ProjectContextConfig,
        ProviderConfig,
        SessionLoggingConfig,
        ThinkingLevel,
    )
    from vibe.core.config.patch import (
        AddOperationPatch,
        ConfigPatch,
        PatchOp,
        RemoveOperationPatch,
        ReplaceOperationPatch,
    )
    from vibe.core.config.schema import (
        ConfigDefinitionError,
        ConfigFragment,
        ConfigSchema,
        DuplicateMergeMetadataError,
        MergeFieldMetadata,
        WithConcatMerge,
        WithConflictMerge,
        WithDeepMerge,
        WithReplaceMerge,
        WithShallowMerge,
        WithUnionMerge,
    )
    from vibe.core.config.types import (
        MISSING_BACKING_STORE_DATA_FINGERPRINT,
        ConfigChangeCallback,
        ConfigChangeEvent,
        LayerConfigSnapshot,
    )
    from vibe.core.config.vibe_schema import (
        DEFAULT_ACTIVE_MODEL_CONFIG,
        DEFAULT_MODELS,
        DEFAULT_PROVIDERS,
        VibeConfigSchema,
        create_default_config,
        get_persisted_config,
        load_dotenv_values,
        resolve_api_key,
    )
    from vibe.core.prompts import MissingPromptFileError

    type VibeConfigSchemaType = type[VibeConfigSchema]

__all__ = [
    "AUTO_THEME",
    "DEFAULT_ACTIVE_MODEL_CONFIG",
    "DEFAULT_API_RETRY_MAX_ELAPSED_TIME",
    "DEFAULT_API_TIMEOUT",
    "DEFAULT_AUTO_COMPACT_THRESHOLD",
    "DEFAULT_MODELS",
    "DEFAULT_PROVIDERS",
    "DEFAULT_THEME",
    "FALLBACK_THEME",
    "MISSING_BACKING_STORE_DATA_FINGERPRINT",
    "THINKING_LEVELS",
    "AddOperationPatch",
    "AgentProfileLayer",
    "ConfigChangeCallback",
    "ConfigChangeEvent",
    "ConfigDefinitionError",
    "ConfigFragment",
    "ConfigLayer",
    "ConfigLayerError",
    "ConfigPatch",
    "ConfigPatchApplicationError",
    "ConfigSchema",
    "ConnectorConfig",
    "DefaultConfigLayer",
    "DiscoveredConfigLayer",
    "DuplicateMergeMetadataError",
    "EmptyLayerError",
    "LayerConfigSnapshot",
    "LayerImplementationError",
    "LayerNotLoadedError",
    "MCPHttp",
    "MCPOAuth",
    "MCPServer",
    "MCPStaticAuth",
    "MCPStdio",
    "MCPStreamableHttp",
    "MergeFieldMetadata",
    "MissingAPIKeyError",
    "MissingPromptFileError",
    "ModelConfig",
    "PatchOp",
    "ProjectContextConfig",
    "ProviderConfig",
    "RawConfig",
    "RemoveOperationPatch",
    "ReplaceOperationPatch",
    "SessionLoggingConfig",
    "ThinkingLevel",
    "TrustResolutionError",
    "UntrustedLayerError",
    "VibeConfigSchema",
    "VibeConfigSchemaType",
    "WithConcatMerge",
    "WithConflictMerge",
    "WithDeepMerge",
    "WithReplaceMerge",
    "WithShallowMerge",
    "WithUnionMerge",
    "build_default_orchestrator",
    "build_user_config_orchestrator",
    "create_default_config",
    "get_persisted_config",
    "load_dotenv_values",
    "resolve_api_key",
]

_MAPPING: dict[str, tuple[str, str]] = {
    "AUTO_THEME": ("vibe.core.config._defaults", "AUTO_THEME"),
    "DEFAULT_API_RETRY_MAX_ELAPSED_TIME": (
        "vibe.core.config._defaults",
        "DEFAULT_API_RETRY_MAX_ELAPSED_TIME",
    ),
    "DEFAULT_API_TIMEOUT": ("vibe.core.config._defaults", "DEFAULT_API_TIMEOUT"),
    "DEFAULT_AUTO_COMPACT_THRESHOLD": (
        "vibe.core.config._defaults",
        "DEFAULT_AUTO_COMPACT_THRESHOLD",
    ),
    "DEFAULT_THEME": ("vibe.core.config._defaults", "DEFAULT_THEME"),
    "FALLBACK_THEME": ("vibe.core.config._defaults", "FALLBACK_THEME"),
    "build_default_orchestrator": (
        "vibe.core.config.default_orchestrator",
        "build_default_orchestrator",
    ),
    "build_user_config_orchestrator": (
        "vibe.core.config.default_orchestrator",
        "build_user_config_orchestrator",
    ),
    "ConfigLayer": ("vibe.core.config.layer", "ConfigLayer"),
    "ConfigLayerError": ("vibe.core.config.layer", "ConfigLayerError"),
    "ConfigPatchApplicationError": (
        "vibe.core.config.layer",
        "ConfigPatchApplicationError",
    ),
    "EmptyLayerError": ("vibe.core.config.layer", "EmptyLayerError"),
    "LayerImplementationError": ("vibe.core.config.layer", "LayerImplementationError"),
    "LayerNotLoadedError": ("vibe.core.config.layer", "LayerNotLoadedError"),
    "RawConfig": ("vibe.core.config.layer", "RawConfig"),
    "TrustResolutionError": ("vibe.core.config.layer", "TrustResolutionError"),
    "UntrustedLayerError": ("vibe.core.config.layer", "UntrustedLayerError"),
    "AgentProfileLayer": ("vibe.core.config.layers.agent_profile", "AgentProfileLayer"),
    "DefaultConfigLayer": ("vibe.core.config.layers.default", "DefaultConfigLayer"),
    "DiscoveredConfigLayer": (
        "vibe.core.config.layers.discovered",
        "DiscoveredConfigLayer",
    ),
    "THINKING_LEVELS": ("vibe.core.config.models", "THINKING_LEVELS"),
    "ConnectorConfig": ("vibe.core.config.models", "ConnectorConfig"),
    "MCPHttp": ("vibe.core.config.models", "MCPHttp"),
    "MCPOAuth": ("vibe.core.config.models", "MCPOAuth"),
    "MCPServer": ("vibe.core.config.models", "MCPServer"),
    "MCPStaticAuth": ("vibe.core.config.models", "MCPStaticAuth"),
    "MCPStdio": ("vibe.core.config.models", "MCPStdio"),
    "MCPStreamableHttp": ("vibe.core.config.models", "MCPStreamableHttp"),
    "MissingAPIKeyError": ("vibe.core.config.models", "MissingAPIKeyError"),
    "ModelConfig": ("vibe.core.config.models", "ModelConfig"),
    "ProjectContextConfig": ("vibe.core.config.models", "ProjectContextConfig"),
    "ProviderConfig": ("vibe.core.config.models", "ProviderConfig"),
    "SessionLoggingConfig": ("vibe.core.config.models", "SessionLoggingConfig"),
    "ThinkingLevel": ("vibe.core.config.models", "ThinkingLevel"),
    "AddOperationPatch": ("vibe.core.config.patch", "AddOperationPatch"),
    "ConfigPatch": ("vibe.core.config.patch", "ConfigPatch"),
    "PatchOp": ("vibe.core.config.patch", "PatchOp"),
    "RemoveOperationPatch": ("vibe.core.config.patch", "RemoveOperationPatch"),
    "ReplaceOperationPatch": ("vibe.core.config.patch", "ReplaceOperationPatch"),
    "ConfigDefinitionError": ("vibe.core.config.schema", "ConfigDefinitionError"),
    "ConfigFragment": ("vibe.core.config.schema", "ConfigFragment"),
    "ConfigSchema": ("vibe.core.config.schema", "ConfigSchema"),
    "DuplicateMergeMetadataError": (
        "vibe.core.config.schema",
        "DuplicateMergeMetadataError",
    ),
    "MergeFieldMetadata": ("vibe.core.config.schema", "MergeFieldMetadata"),
    "WithConcatMerge": ("vibe.core.config.schema", "WithConcatMerge"),
    "WithConflictMerge": ("vibe.core.config.schema", "WithConflictMerge"),
    "WithDeepMerge": ("vibe.core.config.schema", "WithDeepMerge"),
    "WithReplaceMerge": ("vibe.core.config.schema", "WithReplaceMerge"),
    "WithShallowMerge": ("vibe.core.config.schema", "WithShallowMerge"),
    "WithUnionMerge": ("vibe.core.config.schema", "WithUnionMerge"),
    "MISSING_BACKING_STORE_DATA_FINGERPRINT": (
        "vibe.core.config.types",
        "MISSING_BACKING_STORE_DATA_FINGERPRINT",
    ),
    "ConfigChangeCallback": ("vibe.core.config.types", "ConfigChangeCallback"),
    "ConfigChangeEvent": ("vibe.core.config.types", "ConfigChangeEvent"),
    "LayerConfigSnapshot": ("vibe.core.config.types", "LayerConfigSnapshot"),
    "DEFAULT_ACTIVE_MODEL_CONFIG": (
        "vibe.core.config.vibe_schema",
        "DEFAULT_ACTIVE_MODEL_CONFIG",
    ),
    "DEFAULT_MODELS": ("vibe.core.config.vibe_schema", "DEFAULT_MODELS"),
    "DEFAULT_PROVIDERS": ("vibe.core.config.vibe_schema", "DEFAULT_PROVIDERS"),
    "VibeConfigSchema": ("vibe.core.config.vibe_schema", "VibeConfigSchema"),
    "create_default_config": ("vibe.core.config.vibe_schema", "create_default_config"),
    "get_persisted_config": ("vibe.core.config.vibe_schema", "get_persisted_config"),
    "load_dotenv_values": ("vibe.core.config.vibe_schema", "load_dotenv_values"),
    "resolve_api_key": ("vibe.core.config.vibe_schema", "resolve_api_key"),
    "MissingPromptFileError": ("vibe.core.prompts", "MissingPromptFileError"),
}


def __getattr__(name: str) -> object:
    if name == "VibeConfigSchemaType":
        from vibe.core.config.vibe_schema import VibeConfigSchema

        return type[VibeConfigSchema]
    if name in _MAPPING:
        import importlib

        module_name, attr_name = _MAPPING[name]
        module = importlib.import_module(module_name)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
