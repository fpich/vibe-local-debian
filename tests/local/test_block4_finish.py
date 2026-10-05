from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_product_only_subsystems_are_removed() -> None:
    for relative in (
        "vibe/core/teleport",
        "vibe/core/vibe_code_project",
        "vibe/core/telemetry",
        "vibe/observability/sentry.py",
        "vibe/cli/voice_manager",
        "vibe/cli/narrator_manager",
        "vibe/cli/update_notifier",
        "vibe/cli/vscode_extension_promo",
        "vibe/cli/textual_ui/recording",
        "vibe/cli/textual_ui/widgets/voice_app.py",
        "vibe/cli/textual_ui/widgets/narrator_status.py",
        "vibe/cli/textual_ui/widgets/teleport_message.py",
        "vibe/cli/textual_ui/widgets/vibe_code_project",
        "vibe/setup/update_prompt",
        "vibe/utils/audio.py",
    ):
        assert not (REPO_ROOT / relative).exists(), relative


def test_tui_has_no_removed_product_imports() -> None:
    source = (REPO_ROOT / "vibe/cli/textual_ui/app.py").read_text()
    for removed in (
        "build_audio_request_metadata",
        "voice_manager",
        "narrator_manager",
        "teleport_message",
        "vibe_code_project",
        "feedback_bar",
    ):
        assert removed not in source


def test_local_runtime_has_no_remote_product_references() -> None:
    sources = "\n".join(
        p.read_text(errors="ignore") for p in (REPO_ROOT / "vibe").rglob("*.py")
    )
    for removed in (
        "vibe.core.teleport",
        "vibe.core.vibe_code_project",
        "vibe.observability.sentry",
        "vibe.cli.update_notifier",
        "vibe.cli.voice_manager",
        "vibe.cli.narrator_manager",
        "_TELEPORT_AVAILABLE",
        "_is_git_executable_available",
    ):
        assert removed not in sources
