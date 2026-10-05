from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalGroup
from textual.reactive import reactive
from textual.widgets import Static

from vibe import __version__
from vibe.app_server.config import ConfigView
from vibe.cli.textual_ui.widgets.banner.petit_chat import PetitChat
from vibe.cli.textual_ui.widgets.no_markup_static import NoMarkupStatic
from vibe.cli.textual_ui.widgets.spinner_text import SpinnerText


def _pluralize(count: int, singular: str) -> str:
    return f"{count} {singular}{'s' if count != 1 else ''}"


@dataclass
class BannerState:
    active_model: str = ""
    model_pending: bool = False
    models_count: int = 0
    skills_count: int = 0
    hooks_count: int = 0


class Banner(Static):
    """Local-only startup banner.

    The original banner also surfaced MCP, connector, account-plan and unified
    harness state. Those integrations no longer exist in vibe-local-debian, so
    the banner only reports state that is meaningful to the coding agent.
    """

    state = reactive(BannerState(), init=False)

    def __init__(
        self,
        config: ConfigView | None,
        skills_count: int,
        *,
        hooks_count: int = 0,
        model_pending: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.can_focus = False
        self._initial_state = self._build_state(
            config=config,
            skills_count=skills_count,
            hooks_count=hooks_count,
            model_pending=model_pending,
        )
        self._animated = not (config is None or config.disable_welcome_banner_animation)

    def compose(self) -> ComposeResult:
        with VerticalGroup(id="banner-container"):
            yield PetitChat(animate=self._animated)
            with Vertical(id="banner-info"):
                with Horizontal(classes="banner-line"):
                    yield NoMarkupStatic("vibe-local-debian", id="banner-brand")
                    yield NoMarkupStatic(" ", classes="banner-spacer")
                    yield NoMarkupStatic(f"v{__version__} · ", classes="banner-meta")
                    yield SpinnerText(id="banner-model")
                with Horizontal(classes="banner-line"):
                    yield NoMarkupStatic("", id="banner-meta-counts")
                with Horizontal(classes="banner-line"):
                    yield NoMarkupStatic("Type ", classes="banner-meta")
                    yield NoMarkupStatic("/help", classes="banner-cmd")
                    yield NoMarkupStatic(" for more information", classes="banner-meta")

    def on_mount(self) -> None:
        self.state = self._initial_state

    def watch_state(self) -> None:
        if not self.is_attached:
            return
        model = self.query_one("#banner-model", SpinnerText)
        counts = self.query_one("#banner-meta-counts", NoMarkupStatic)
        model.set_pending(self.state.model_pending, resolved=self.state.active_model)
        counts.update(self._format_meta_counts())

    def freeze_animation(self) -> None:
        if self._animated:
            self.query_one(PetitChat).freeze_animation()

    def set_state(
        self,
        config: ConfigView | None,
        skills_count: int,
        *,
        hooks_count: int = 0,
        model_pending: bool = False,
    ) -> None:
        self.state = self._build_state(
            config=config,
            skills_count=skills_count,
            hooks_count=hooks_count,
            model_pending=model_pending,
        )

    @staticmethod
    def _build_state(
        config: ConfigView | None,
        skills_count: int,
        *,
        hooks_count: int = 0,
        model_pending: bool = False,
    ) -> BannerState:
        if config is None:
            return BannerState()
        active_model = config.active_model
        return BannerState(
            active_model=f"{active_model.display_name}[{active_model.thinking}]",
            model_pending=model_pending,
            models_count=len(config.models),
            skills_count=skills_count,
            hooks_count=hooks_count,
        )

    def _format_meta_counts(self) -> str:
        if self.state.models_count == 0:
            return ""
        parts = [
            _pluralize(self.state.models_count, "model"),
            _pluralize(self.state.skills_count, "skill"),
        ]
        if self.state.hooks_count > 0:
            parts.append(_pluralize(self.state.hooks_count, "hook"))
        return " · ".join(parts)
