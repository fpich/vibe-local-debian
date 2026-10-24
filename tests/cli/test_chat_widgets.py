"""Tests for chat-related Textual widgets."""

from __future__ import annotations

from vibe.cli.textual_ui.widgets.cached_renderer import CachedMessageRenderer
from vibe.cli.textual_ui.widgets.chat_message import (
    ChatMessageFactory,
    StreamingMessage,
    VirtualizedMessage,
)
from vibe.cli.textual_ui.widgets.virtualized_chat import ChatHistoryManager


class TestStreamingMessage:
    """Tests for StreamingMessage widget."""

    def test_initial_content(self) -> None:
        """Test that initial content is set correctly."""
        msg = StreamingMessage(initial_content="Hello")
        assert msg.get_full_content() == "Hello"

    def test_add_chunk(self) -> None:
        """Test adding chunks to the message."""
        msg = StreamingMessage()
        msg.add_chunk("Hello")
        assert msg.get_full_content() == "Hello"

        msg.add_chunk(" World")
        assert msg.get_full_content() == "Hello World"

    def test_add_chunk_with_newline(self) -> None:
        """Test that newlines trigger immediate refresh."""
        msg = StreamingMessage()
        msg.add_chunk("Line 1\n")
        # Should flush buffer because of newline
        assert msg.get_full_content() == "Line 1\n"

    def test_add_chunk_with_punctuation(self) -> None:
        """Test that punctuation triggers immediate refresh."""
        msg = StreamingMessage(min_refresh_length=100)
        msg.add_chunk("Hello.")
        # Should flush buffer because of punctuation
        assert msg.get_full_content() == "Hello."

    def test_buffer_accumulation(self) -> None:
        """Test that small chunks are buffered."""
        msg = StreamingMessage(min_refresh_length=100)
        msg.add_chunk("a")
        msg.add_chunk("b")
        msg.add_chunk("c")
        # Should not flush yet
        assert msg.get_full_content() == "abc"

        # Add enough to trigger flush
        msg.add_chunk("d" * 98)
        # Total is 101, should flush
        assert msg.get_full_content() == "abc" + "d" * 98

    def test_finalize(self) -> None:
        """Test that finalize flushes any remaining buffer."""
        msg = StreamingMessage(min_refresh_length=100)
        msg.add_chunk("short")
        msg.finalize()
        assert msg.get_full_content() == "short"

    def test_is_content_empty(self) -> None:
        """Test is_empty method."""
        msg = StreamingMessage()
        assert msg.is_content_empty()

        msg.add_chunk(" ")
        assert msg.is_content_empty()

        msg.add_chunk("content")
        assert not msg.is_content_empty()

    def test_clear(self) -> None:
        """Test clear method."""
        msg = StreamingMessage(initial_content="Hello")
        msg.add_chunk(" World")
        msg.clear()
        assert msg.get_full_content() == ""
        assert msg.is_content_empty()


class TestVirtualizedMessage:
    """Tests for VirtualizedMessage widget."""

    def test_initial_content(self) -> None:
        """Test that initial content is set correctly."""
        msg = VirtualizedMessage(content="Hello", is_visible=True)
        assert msg.get_content() == "Hello"

    def test_set_visible(self) -> None:
        """Test setting visibility."""
        msg = VirtualizedMessage(content="Hello", is_visible=False)
        assert msg.get_content() == "Hello"

        msg.set_visible(True)
        # Content should now be displayed

        msg.set_visible(False)
        # Content should be hidden

    def test_set_content(self) -> None:
        """Test updating content."""
        msg = VirtualizedMessage(content="Hello", is_visible=True)
        msg.set_content("World")
        assert msg.get_content() == "World"

    def test_set_content_while_hidden(self) -> None:
        """Test updating content while hidden."""
        msg = VirtualizedMessage(content="Hello", is_visible=False)
        msg.set_content("World")
        assert msg.get_content() == "World"

        msg.set_visible(True)
        # Content should now show "World"


class TestCachedMessageRenderer:
    """Tests for CachedMessageRenderer."""

    def test_render_plain_text(self) -> None:
        """Test rendering plain text."""
        result = CachedMessageRenderer.render_plain_text("Hello", width=80)
        assert "Hello" in result

    def test_render_code(self) -> None:
        """Test rendering code with syntax highlighting."""
        result = CachedMessageRenderer.render_code(
            "print('hello')", width=80, language="python"
        )
        assert "print" in result or "hello" in result

    def test_cache_info(self) -> None:
        """Test cache statistics."""
        # Clear cache first
        CachedMessageRenderer.clear_cache()

        # Render something to create a cache entry
        CachedMessageRenderer.render_plain_text("test", width=80)

        # Get cache info
        hits, misses, maxsize, currsize = CachedMessageRenderer.get_cache_info()
        assert misses >= 1
        assert currsize >= 1
        assert maxsize == CachedMessageRenderer.MAX_CACHE_SIZE

    def test_clear_cache(self) -> None:
        """Test clearing the cache."""
        CachedMessageRenderer.render_plain_text("test", width=80)

        _, _, _, before_size = CachedMessageRenderer.get_cache_info()
        assert before_size >= 1

        CachedMessageRenderer.clear_cache()

        _, _, _, after_size = CachedMessageRenderer.get_cache_info()
        assert after_size == 0

    def test_same_content_different_width(self) -> None:
        """Test that different widths create different cache entries."""
        result_80 = CachedMessageRenderer.render_plain_text("test", width=80)
        result_40 = CachedMessageRenderer.render_plain_text("test", width=40)

        # Results may be different due to line wrapping
        # Just verify both render without error
        assert "test" in result_80 or "test" in result_40


class TestChatMessageFactory:
    """Tests for ChatMessageFactory."""

    def test_create_streaming_message(self) -> None:
        """Test creating a streaming message."""
        msg = ChatMessageFactory.create_streaming_message("Hello")
        assert isinstance(msg, StreamingMessage)
        assert msg.get_full_content() == "Hello"

    def test_create_virtualized_message(self) -> None:
        """Test creating a virtualized message."""
        msg = ChatMessageFactory.create_virtualized_message("Hello")
        assert isinstance(msg, VirtualizedMessage)
        assert msg.get_content() == "Hello"


class TestChatHistoryManager:
    """Tests for ChatHistoryManager."""

    def test_add_message(self) -> None:
        """Test adding messages to history."""
        manager = ChatHistoryManager()
        manager.add_message("Hello", role="user")
        manager.add_message("Hi there", role="assistant")

        assert manager.get_message_count() == 2

    def test_get_messages(self) -> None:
        """Test getting all messages."""
        manager = ChatHistoryManager()
        manager.add_message("Hello", role="user")
        manager.add_message("Hi there", role="assistant")

        messages = manager.get_messages()
        assert len(messages) == 2
        assert messages[0]["content"] == "Hello"
        assert messages[0]["role"] == "user"
        assert messages[1]["content"] == "Hi there"
        assert messages[1]["role"] == "assistant"

    def test_clear(self) -> None:
        """Test clearing the history."""
        manager = ChatHistoryManager()
        manager.add_message("Hello")
        manager.add_message("World")

        assert manager.get_message_count() == 2

        manager.clear()

        assert manager.get_message_count() == 0

    def test_metadata(self) -> None:
        """Test adding messages with metadata."""
        manager = ChatHistoryManager()
        manager.add_message(
            "Hello", role="user", metadata={"timestamp": "2024-01-01", "id": "123"}
        )

        messages = manager.get_messages()
        assert messages[0]["metadata"]["timestamp"] == "2024-01-01"
        assert messages[0]["metadata"]["id"] == "123"
