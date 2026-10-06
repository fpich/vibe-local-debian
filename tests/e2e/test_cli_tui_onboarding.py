from __future__ import annotations

from pathlib import Path
import time

import pexpect
import pytest

from tests.e2e.common import SpawnedVibeProcessFixture, strip_ansi, wait_for_main_screen


def _quit(child: pexpect.spawn, timeout: float = 10) -> None:
    """Send Ctrl+C until the process exits, tolerating a quit-confirmation prompt."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        child.sendcontrol("c")
        try:
            child.expect(pexpect.EOF, timeout=2)
            return
        except pexpect.TIMEOUT:
            continue
    raise AssertionError("Timed out waiting for the CLI to quit after Ctrl+C")


@pytest.mark.timeout(60)
def test_spawn_cli_opens_tui_directly_without_cloud_onboarding(
    tmp_path: Path,
    e2e_workdir: Path,
    spawned_vibe_process: SpawnedVibeProcessFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vibe_home = tmp_path / "vibe-home-onboarding"
    vibe_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VIBE_HOME", str(vibe_home))
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    with spawned_vibe_process(e2e_workdir) as (child, captured):
        wait_for_main_screen(child, timeout=25)
        _quit(child)

    output = strip_ansi(captured.getvalue())
    assert "Welcome to vibe" not in output
    assert "API key" not in output
