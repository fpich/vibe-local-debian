from __future__ import annotations


# Kept intentionally tiny: the `vibe` console script lands here without
# importing the whole CLI stack. Importing entrypoint also runs its module-top
# pty-helper check.
def main() -> None:
    from vibe.cli.entrypoint import main as entrypoint_main

    entrypoint_main()


if __name__ == "__main__":
    main()
