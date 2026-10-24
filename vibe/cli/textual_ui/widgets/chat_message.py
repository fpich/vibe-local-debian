"""Streaming message widget for incremental rendering in the TUI.

This module provides widgets for efficient streaming and rendering of
chat messages in the Textual TUI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.widgets import Static

if TYPE_CHECKING:
    pass


class StreamingMessage(Static):
    """A widget for displaying messages with incremental streaming support.

    This widget efficiently handles streaming content by:
    1. Buffering small chunks to reduce refresh overhead
    2. Only refreshing the display when significant content is accumulated
    3. Supporting both streaming and complete content modes

    Attributes:
        _buffer: Temporary buffer for accumulating small chunks.
        _full_content: Complete content of the message.
        _min_refresh_length: Minimum buffer length before refreshing.
    """

    def __init__(
        self, initial_content: str = "", *, min_refresh_length: int = 100, **kwargs: Any
    ) -> None:
        """Initialize the streaming message widget.

        Args:
            initial_content: Initial content for the message.
            min_refresh_length: Minimum number of characters to buffer
                before refreshing the display.
            **kwargs: Additional arguments passed to Static.
        """
        super().__init__(initial_content, **kwargs)
        self._buffer = ""
        self._full_content = initial_content
        self._min_refresh_length = min_refresh_length
        self.add_class("streaming-message")

    def add_chunk(self, chunk: str) -> None:
        """Add a chunk of content to the message.

        This method efficiently buffers small chunks and only refreshes
        the display when enough content has accumulated or when a natural
        breaking point (like a newline or sentence end) is reached.

        Args:
            chunk: The chunk of text to add.
        """
        if not chunk:
            return

        self._buffer += chunk
        self._full_content += chunk

        # Refresh if buffer is large enough or if we hit a natural break
        should_refresh = (
            len(self._buffer) >= self._min_refresh_length
            or chunk.endswith(("\n", ".", "!", "?", ":", ";"))
            or "\n" in self._buffer
        )

        if should_refresh:
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        """Flush the buffer and update the display."""
        if self._buffer:
            # Update with full content to ensure consistency
            self.update(self._full_content)
            self._buffer = ""

    def finalize(self) -> None:
        """Finalize the message and ensure all content is displayed."""
        self._flush_buffer()

    def get_full_content(self) -> str:
        """Get the complete content of the message.

        Returns:
            The full content including any buffered chunks.
        """
        return self._full_content

    def is_empty(self) -> bool:
        """Check if the message content is empty.

        Returns:
            True if the message has no content.
        """
        return not self._full_content.strip()

    def clear(self) -> None:
        """Clear the message content."""
        self._buffer = ""
        self._full_content = ""
        self.update("")


class VirtualizedMessage(Static):
    """A virtualized message widget for efficient rendering of large chats.

    This widget is designed to be used in a virtualized list where only
    visible messages are fully rendered, improving performance with
    large chat histories.

    Attributes:
        _content: The full content of the message.
        _is_visible: Whether the message is currently visible.
    """

    def __init__(
        self, content: str = "", *, is_visible: bool = True, **kwargs: Any
    ) -> None:
        """Initialize the virtualized message widget.

        Args:
            content: The content of the message.
            is_visible: Whether the message is currently visible.
            **kwargs: Additional arguments passed to Static.
        """
        super().__init__(content if is_visible else "", **kwargs)
        self._content = content
        self._is_visible = is_visible
        self.add_class("virtualized-message")

    def set_visible(self, visible: bool) -> None:
        """Set whether the message should be rendered.

        Args:
            visible: True to render the message, False to hide it.
        """
        self._is_visible = visible
        if visible:
            self.update(self._content)
        else:
            self.update("")

    def set_content(self, content: str) -> None:
        """Update the message content.

        Args:
            content: The new content for the message.
        """
        self._content = content
        if self._is_visible:
            self.update(content)

    def get_content(self) -> str:
        """Get the message content.

        Returns:
            The full content of the message.
        """
        return self._content


class ChatMessageFactory:
    """Factory for creating chat message widgets.

    This factory provides methods for creating different types of message
    widgets with consistent styling and behavior.
    """

    @staticmethod
    def create_streaming_message(
        initial_content: str = "", **kwargs: Any
    ) -> StreamingMessage:
        """Create a streaming message widget.

        Args:
            initial_content: Initial content for the message.
            **kwargs: Additional arguments passed to StreamingMessage.

        Returns:
            A new StreamingMessage widget.
        """
        return StreamingMessage(initial_content, **kwargs)

    @staticmethod
    def create_virtualized_message(
        content: str = "", **kwargs: Any
    ) -> VirtualizedMessage:
        """Create a virtualized message widget.

        Args:
            content: The content of the message.
            **kwargs: Additional arguments passed to VirtualizedMessage.

        Returns:
            A new VirtualizedMessage widget.
        """
        return VirtualizedMessage(content, **kwargs)
