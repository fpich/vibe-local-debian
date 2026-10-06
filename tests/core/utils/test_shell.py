from __future__ import annotations

import vibe.core.utils.shell as shell


def test_shell_environment_does_not_invent_locale(monkeypatch) -> None:
    monkeypatch.delenv("LC_ALL", raising=False)

    environment = shell.shell_environment()

    assert "LC_ALL" not in environment


def test_shell_environment_forces_lc_ctype_and_drops_inherited_lc_all(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.delenv("LC_CTYPE", raising=False)

    environment = shell.shell_environment()

    assert "LC_ALL" not in environment
    assert environment["LC_CTYPE"] == "C.UTF-8"


def test_shell_environment_preserves_other_user_locale_categories(monkeypatch) -> None:
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.setenv("LC_TIME", "fr_FR.UTF-8")
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")

    environment = shell.shell_environment()

    assert environment["LC_TIME"] == "fr_FR.UTF-8"
    assert environment["LANG"] == "fr_FR.UTF-8"
    assert environment["LC_CTYPE"] == "C.UTF-8"


def test_shell_environment_drops_shell_startup_hook_vars(monkeypatch) -> None:
    for var in ("ENV", "BASH_ENV", "PS1", "PROMPT_COMMAND", "ZDOTDIR"):
        monkeypatch.setenv(var, "/tmp/pwned")
    environment = shell.shell_environment()
    for var in ("ENV", "BASH_ENV", "PS1", "PROMPT_COMMAND", "ZDOTDIR"):
        assert var not in environment
