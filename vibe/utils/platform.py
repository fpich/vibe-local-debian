from __future__ import annotations

import os
from pathlib import Path
import platform
import sys
from typing import Final

_GIT_EXECUTABLE_ENV: Final = "GIT_PYTHON_GIT_EXECUTABLE"

_PLATFORM_IDS: Final[dict[str, str]] = {
    "win32": "windows",
    "darwin": "darwin",
    "linux": "linux",
    "freebsd": "freebsd",
    "openbsd": "openbsd",
    "netbsd": "netbsd",
}

_PLATFORM_DISPLAY_NAMES: Final[dict[str, str]] = {
    "windows": "Windows",
    "darwin": "macOS",
    "linux": "Linux",
    "freebsd": "FreeBSD",
    "openbsd": "OpenBSD",
    "netbsd": "NetBSD",
}


def is_windows() -> bool:
    return sys.platform == "win32"


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and (is_windows() or os.access(path, os.X_OK))


def _resolved_executable(path: Path) -> Path | None:
    try:
        resolved = path.expanduser().resolve()
        return resolved if _is_executable_file(resolved) else None
    except (OSError, RuntimeError):
        return None


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _is_overbroad_project_dir(directory: Path) -> bool:
    if directory.parent == directory:
        return True
    try:
        return directory == Path.home().expanduser().resolve()
    except (OSError, RuntimeError):
        return False


def _is_untrusted_project_executable(path: Path, project_dir: Path) -> bool:
    """Return whether automatic discovery must ignore a project-local binary.

    Filesystem roots and home directories also contain ordinary executable
    locations such as ``/usr/bin`` and ``~/.local/bin``. When either is the
    working directory, only a binary directly in that directory is treated as
    the implicit current-directory candidate.
    """
    if not _is_within(path, project_dir):
        return False
    if _is_overbroad_project_dir(project_dir):
        return path.parent == project_dir
    return True


def _search_trusted_path(name: str, *, cwd: Path) -> str | None:
    """Resolve an executable without implicit current-directory search."""
    for raw_entry in os.get_exec_path():
        entry = Path(raw_entry.strip('"')).expanduser()
        if not entry.is_absolute():
            continue
        for executable_name in (name,):
            candidate = _resolved_executable(entry / executable_name)
            if candidate is not None and not _is_untrusted_project_executable(
                candidate, cwd
            ):
                return str(candidate)
    return None


def _resolve_configured_git(configured: str) -> str | None:
    configured_path = Path(configured).expanduser()
    if not configured_path.is_absolute():
        return None
    resolved = _resolved_executable(configured_path)
    return str(resolved) if resolved is not None else None


def resolve_git_executable(*, cwd: Path | None = None) -> str | None:
    """Return an absolute Git executable safe for application-owned calls.

    A process-level ``GIT_PYTHON_GIT_EXECUTABLE`` override is an explicit trust
    decision and may point at a portable installation. Automatic discovery never
    searches relative PATH entries or selects an executable from the project.
    """
    project_dir = (cwd or Path.cwd()).resolve()
    configured = os.environ.get(_GIT_EXECUTABLE_ENV)
    if configured:
        return _resolve_configured_git(configured)

    if resolved := _search_trusted_path("git", cwd=project_dir):
        return resolved

    return None


def resolve_ssh_executable(*, cwd: Path | None = None) -> str | None:
    """Return an absolute SSH client that is not a project-local binary.

    Automatic discovery never searches relative PATH entries or selects an
    executable from the working directory, including Windows' implicit
    current-directory search used by ``shutil.which``.
    """
    return _search_trusted_path("ssh", cwd=(cwd or Path.cwd()).resolve())


def configure_git_python_executable(*, cwd: Path | None = None) -> str | None:
    """Pin GitPython to the same trusted executable used by direct callers."""
    executable = resolve_git_executable(cwd=cwd)
    if executable is not None:
        os.environ[_GIT_EXECUTABLE_ENV] = executable
    return executable


def get_platform_id() -> str:
    """Canonical lowercase platform identifier (e.g. ``windows``, ``darwin``, ``linux``).

    Matches the values expected by ``ExperimentAttributes.os`` and is suitable for
    machine-readable contexts. Falls back to the
    raw ``sys.platform`` value for unknown platforms.
    """
    return _PLATFORM_IDS.get(sys.platform, sys.platform)


def get_platform_version() -> str | None:
    match get_platform_id():
        case "darwin":
            version = platform.mac_ver()[0] or platform.release()
        case "windows":
            version = platform.version() or platform.release()
        case "linux":
            version = _linux_os_version() or platform.release()
        case _:
            version = platform.release() or platform.version()
    return version or None


def _linux_os_version() -> str | None:
    try:
        os_release = platform.freedesktop_os_release()
    except OSError:
        return None
    return os_release.get("VERSION_ID") or os_release.get("VERSION")


def get_platform_display_name() -> str:
    """Human-readable platform name (e.g. ``Windows``, ``macOS``, ``Linux``).

    Suitable for surfacing in system prompts. Falls back to ``Unix-like`` for
    unknown platforms.
    """
    return _PLATFORM_DISPLAY_NAMES.get(get_platform_id(), "Unix-like")
