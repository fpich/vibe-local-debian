"""Minimal pytest configuration for the maintained local-fork test suite.

The original upstream conftest depended on cloud auth, MCP, voice and update
components that are intentionally absent from vibe-local-debian.  The stable
suite under tests/local is self-contained and uses only pytest built-ins.
"""

from __future__ import annotations
