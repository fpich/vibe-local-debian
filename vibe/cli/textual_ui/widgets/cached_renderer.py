"""Cached renderer for message content to improve TUI performance.

This module provides caching for rendered message content to avoid
recomputing syntax highlighting and markdown rendering for the same content.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from rich.console import Console
from rich.syntax import Syntax

if TYPE_CHECKING:
    pass


class CachedMessageRenderer:
    """Renderer for message content with LRU caching.

    This class caches the rendered output of message content to improve
    performance when the same content is rendered multiple times (e.g.,
    during scrolling or window resizing).

    The cache uses a combination of content hash and width to ensure that
    different terminal widths get different cached results.
    """

    # Maximum number of rendered messages to cache
    MAX_CACHE_SIZE = 500

    @staticmethod
    @lru_cache(maxsize=MAX_CACHE_SIZE)
    def render_content(
        content: str, width: int, is_code: bool = False, code_language: str = "python"
    ) -> str:
        """Render content with optional syntax highlighting.

        Args:
            content: The text content to render.
            width: The terminal width for rendering.
            is_code: Whether to apply syntax highlighting.
            code_language: The programming language for syntax highlighting.

        Returns:
            The rendered content as a string.
        """
        console = Console(
            width=width, force_terminal=True, no_color=True, highlight=False
        )

        if is_code and content.strip():
            try:
                syntax = Syntax(
                    content,
                    lexer=code_language,
                    theme="monokai",
                    line_numbers=False,
                    word_wrap=True,
                )
                with console.capture() as capture:
                    console.print(syntax)
                return capture.get()
            except Exception:
                # Fall back to plain text if syntax highlighting fails
                pass

        with console.capture() as capture:
            console.print(content)
        return capture.get()

    @staticmethod
    def render_plain_text(content: str, width: int) -> str:
        """Render plain text content.

        Args:
            content: The text content to render.
            width: The terminal width for rendering.

        Returns:
            The rendered content as a string.
        """
        return CachedMessageRenderer.render_content(content, width, is_code=False)

    @staticmethod
    def render_code(content: str, width: int, language: str = "python") -> str:
        """Render code content with syntax highlighting.

        Args:
            content: The code content to render.
            width: The terminal width for rendering.
            language: The programming language for syntax highlighting.

        Returns:
            The rendered content as a string.
        """
        return CachedMessageRenderer.render_content(
            content, width, is_code=True, code_language=language
        )

    @staticmethod
    def clear_cache() -> None:
        """Clear all cached rendered content."""
        CachedMessageRenderer.render_content.cache_clear()

    @staticmethod
    def get_cache_info() -> tuple[int, int, int, int]:
        """Get cache statistics.

        Returns:
            A tuple of (hits, misses, maxsize, currsize).
        """
        return CachedMessageRenderer.render_content.cache_info()
