from __future__ import annotations

import pytest

from vibe.core.tools.base import BaseToolState, ToolPermission
from vibe.core.tools.builtins.experimental_bash import (
    ExperimentalBash,
    ExperimentalBashArgs,
    ExperimentalBashToolConfig,
)
from vibe.core.utils import is_windows

pytestmark = pytest.mark.skipif(is_windows(), reason="managed bash is POSIX-only")


def _make_tool() -> ExperimentalBash:
    return ExperimentalBash(
        config_getter=lambda: ExperimentalBashToolConfig(), state=BaseToolState()
    )


NETWORK_COMMANDS = [
    "curl http://example.com",
    "wget http://example.com",
    "scp file host:/tmp",
    "rsync -a src/ host::dst/",
    "ping -c 1 example.com",
    "ssh user@example.com",
]


@pytest.mark.parametrize("command", NETWORK_COMMANDS)
def test_network_commands_are_not_auto_approved(command: str) -> None:
    result = _make_tool().resolve_permission(ExperimentalBashArgs(command=command))
    assert result is None or result.permission is not ToolPermission.ALWAYS


def test_sensitive_command_is_not_auto_approved() -> None:
    result = _make_tool().resolve_permission(
        ExperimentalBashArgs(command="sudo apt-get install build-essential")
    )
    assert result is None or result.permission is not ToolPermission.ALWAYS


def test_allowlisted_read_only_command_is_auto_approved() -> None:
    result = _make_tool().resolve_permission(ExperimentalBashArgs(command="ls -la"))
    assert result is not None
    assert result.permission is ToolPermission.ALWAYS
