from __future__ import annotations


def main() -> None:
    """Launch the only supported UI: the local Python/Textual CLI."""
    # Importing entrypoint also runs its module-top POSIX PTY helper check.
    from vibe.cli.entrypoint import main as entrypoint_main

    entrypoint_main()
