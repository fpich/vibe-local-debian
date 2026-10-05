from __future__ import annotations

from vibe.app_server._model import ProtocolModel
from vibe.config_values import (
    THINKING_LEVELS as THINKING_LEVELS,
    ThinkingLevel as ThinkingLevel,
)


class ModelConfigView(ProtocolModel):
    name: str
    alias: str
    thinking: ThinkingLevel
    supports_images: bool
    display_name: str












class ProxySettingsView(ProtocolModel):
    values: dict[str, str | None]
    descriptions: dict[str, str]


class ConfigView(ProtocolModel):
    active_model: ModelConfigView
    # Whether the user has pinned a specific model, vs. the "default" (unpinned)
    active_model_pinned: bool
    # Wider than `active_model.supports_images`, which stays a per-model fact:
    # the backend may be able to show a model without vision something other
    # than the pixels.
    images_supported: bool = False
    # Cold-cache first launch
    default_model_alias: str
    default_agent: str = "accept-edits"
    theme: str
    log_level: str | None
    disable_welcome_banner_animation: bool
    show_greeting: bool
    autocopy_to_clipboard: bool
    file_watcher_for_autocomplete: bool
    ask_confirmation_on_exit: bool
    show_thinking_nodes: bool
    show_subagent_status_list: bool
    worktree_limit: int
    enable_notifications: bool
    experimental_enable_tab_status: bool
    # Consent gate for client-local sinks (the Rust client's crash reporter).
    # Datalake events stay server-gated; clients never decide that.
    models: list[ModelConfigView]
    validation_warnings: list[str]

    def model_display_name(self, alias: str) -> str:
        """User-facing name for a configured alias, or the alias when unknown."""
        return next(
            (model.display_name for model in self.models if model.alias == alias), alias
        )

    @property
    def default_model_display_name(self) -> str:
        return self.model_display_name(self.default_model_alias)
