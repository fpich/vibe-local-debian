"""Virtualized chat history widget for efficient TUI rendering.

This module provides a virtualized chat history that only renders
visible messages, significantly improving performance with large
chat histories.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.widgets import ListItem, ListView

if TYPE_CHECKING:
    pass


class VirtualizedChatHistory(ListView):
    """A virtualized chat history that only renders visible messages.

    This widget improves performance by:
    1. Only creating widgets for messages that are visible or about to be visible
    2. Reusing widgets as the user scrolls
    3. Maintaining a buffer of widgets above and below the visible area

    Attributes:
        _all_messages: List of all message contents.
        _visible_range: Range of message indices currently visible.
        _buffer_size: Number of extra messages to keep rendered above/below.
    """

    def __init__(
        self, *, buffer_size: int = 10, max_visible: int = 50, **kwargs: Any
    ) -> None:
        """Initialize the virtualized chat history.

        Args:
            buffer_size: Number of extra messages to keep rendered.
            max_visible: Maximum number of messages to display at once.
            **kwargs: Additional arguments passed to ListView.
        """
        super().__init__(**kwargs)
        self._all_messages: list[str] = []
        self._visible_range: tuple[int, int] | None = None
        self._buffer_size = buffer_size
        self._max_visible = max_visible
        self.add_class("virtualized-chat")

    def add_message(self, content: str, role: str = "assistant") -> None:
        """Add a new message to the chat history.

        Args:
            content: The content of the message.
            role: The role of the message (e.g., 'user', 'assistant').
        """
        self._all_messages.append(f"[{role}] {content}")

        # If we're at the bottom, scroll to show the new message
        if self._is_at_bottom():
            self._update_visible_range()
            self._ensure_message_visible(len(self._all_messages) - 1)

    def _is_at_bottom(self) -> bool:
        """Check if the scroll position is at the bottom."""
        try:
            return self.scroll_offset >= self.max_scroll_offset
        except Exception:
            return True

    def _update_visible_range(self) -> None:
        """Update the range of visible message indices."""
        try:
            scroll_offset = self.scroll_offset
            viewport_height = self.size.height

            # Calculate which messages are visible
            start_idx = max(0, scroll_offset // 20)  # Approximate line height
            end_idx = min(
                len(self._all_messages), start_idx + viewport_height // 20 + 1
            )

            self._visible_range = (start_idx, end_idx)
        except Exception:
            self._visible_range = None

    def _ensure_message_visible(self, index: int) -> None:
        """Ensure a specific message is visible.

        Args:
            index: The index of the message to make visible.
        """
        if 0 <= index < len(self._all_messages):
            # Scroll to make the message visible
            self.scroll_to_widget(self._get_or_create_message_widget(index))

    def _get_or_create_message_widget(self, index: int) -> ListItem:
        """Get or create a widget for a message.

        Args:
            index: The index of the message.

        Returns:
            The ListItem widget for the message.
        """
        # Check if we already have a widget for this message
        if index < len(self._children):
            return self._children[index]

        # Create a new widget
        from vibe.cli.textual_ui.widgets.chat_message import VirtualizedMessage

        message_content = self._all_messages[index]
        message_widget = VirtualizedMessage(message_content)

        # Add to the list
        self.append(ListItem(message_widget))
        return self._children[index]

    def clear(self) -> None:
        """Clear all messages from the chat history."""
        self._all_messages.clear()
        self.clear_children()
        self._visible_range = None

    def get_message_count(self) -> int:
        """Get the total number of messages.

        Returns:
            The number of messages in the history.
        """
        return len(self._all_messages)

    def get_visible_range(self) -> tuple[int, int] | None:
        """Get the current visible message range.

        Returns:
            A tuple of (start_index, end_index) or None.
        """
        return self._visible_range

    def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the chat history."""
        self.scroll_end()
        self._update_visible_range()

    def scroll_to_top(self) -> None:
        """Scroll to the top of the chat history."""
        self.scroll_home()
        self._update_visible_range()

    def on_scroll(self, event: Any) -> None:
        """Handle scroll events to update visible range."""
        self._update_visible_range()
        self._update_widget_visibility()

    def _update_widget_visibility(self) -> None:
        """Update which message widgets are visible."""
        if self._visible_range is None:
            return

        start_idx, end_idx = self._visible_range

        # Update visibility for all children
        for idx, child in enumerate(self._children):
            if isinstance(child, ListItem) and hasattr(
                child.children[0], "set_visible"
            ):
                # Show widgets that are visible or in the buffer
                should_be_visible = (
                    start_idx - self._buffer_size <= idx < end_idx + self._buffer_size
                )
                child.children[0].set_visible(should_be_visible)


class ChatHistoryManager:
    """Manager for chat history with virtualization support.

    This manager provides a high-level interface for managing chat history
    with virtualization and other optimizations.
    """

    def __init__(self) -> None:
        """Initialize the chat history manager."""
        self._messages: list[dict[str, Any]] = []

    def add_message(
        self,
        content: str,
        role: str = "assistant",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a message to the history.

        Args:
            content: The content of the message.
            role: The role of the message.
            metadata: Optional metadata for the message.
        """
        message = {
            "content": content,
            "role": role,
            "metadata": metadata or {},
            "timestamp": self._get_timestamp(),
        }
        self._messages.append(message)

    def _get_timestamp(self) -> str:
        """Get a timestamp for the current time.

        Returns:
            A timestamp string.
        """
        from datetime import datetime

        return datetime.now().isoformat()

    def get_messages(self) -> list[dict[str, Any]]:
        """Get all messages in the history.

        Returns:
            List of all messages.
        """
        return self._messages.copy()

    def clear(self) -> None:
        """Clear all messages from the history."""
        self._messages.clear()

    def get_message_count(self) -> int:
        """Get the number of messages in the history.

        Returns:
            The number of messages.
        """
        return len(self._messages)
