from __future__ import annotations

import asyncio
import logging
import os
import signal

logger = logging.getLogger(__name__)


async def kill_async_subprocess(
    proc: asyncio.subprocess.Process, *, kill_process_group: bool = True
) -> None:
    """Force-terminate an asyncio child process and wait until it exits.

    With ``kill_process_group=True`` (default), on Unix this sends ``SIGKILL``
    to the child's process group via :func:`os.killpg`. Only use that mode
    when the child is isolated in its own group (for example
    ``start_new_session=True`` with ``create_subprocess_shell``); otherwise the
    group id may match the parent's and unrelated processes could be killed.

    With ``kill_process_group=False``, :meth:`asyncio.subprocess.Process.kill`
    is used on all platforms (typical for a single ``create_subprocess_exec``
    leaf such as ``grep``).
    """
    if proc.returncode is not None:
        return

    try:
        if not kill_process_group:
            proc.kill()
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            except Exception:
                logger.debug(
                    "Unexpected error killing process group for pid %s",
                    proc.pid,
                    exc_info=True,
                )

        await proc.wait()
    except (ProcessLookupError, PermissionError, OSError):
        pass
