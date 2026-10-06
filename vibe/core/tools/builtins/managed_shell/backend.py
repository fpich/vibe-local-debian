from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ManagedShellBackendError(Exception):
    pass


# Stands in for a terminal that was killed but never reaped.
UNKNOWN_EXIT_CODE = 1


@dataclass(frozen=True)
class ManagedShellBackendCapabilities:
    interactive_tty: bool
    control_sequences: bool
    process_group_kill: bool
    shell_family: str


class ManagedTerminal(Protocol):
    @property
    def pid(self) -> int | None: ...

    @property
    def pty_backend(self) -> str | None: ...

    @property
    def returncode(self) -> int | None: ...

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int | None: ...

    def wait_readable(self, timeout_seconds: float) -> bool: ...

    def read(self, size: int) -> bytes: ...

    def write(self, data: bytes) -> int: ...

    def close(self) -> None: ...


class ManagedShellBackend(Protocol):
    capabilities: ManagedShellBackendCapabilities

    def resolve_shell(self, requested: str | None, configured: str | None) -> str: ...

    def start_terminal(
        self, *, shell: str, command: str, cwd: Path, env: dict[str, str]
    ) -> ManagedTerminal: ...

    def request_termination(self, terminal: ManagedTerminal) -> None: ...

    def force_terminate_terminal(
        self, terminal: ManagedTerminal, *, timeout_seconds: float
    ) -> None: ...


def posix_managed_shell_supported() -> bool:
    return True


def managed_shell_supported(shell_family: str | None = None) -> bool:
    return shell_family in {None, "posix"}


def create_managed_shell_backend(
    shell_family: str | None = None,
) -> ManagedShellBackend:
    if shell_family not in {None, "posix"}:
        raise ManagedShellBackendError(f"unknown managed shell family: {shell_family}")
    from vibe.core.tools.builtins.managed_shell._posix import PosixManagedShellBackend

    return PosixManagedShellBackend()
