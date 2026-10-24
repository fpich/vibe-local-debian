"""Tests for the ToolResultCache functionality."""

from __future__ import annotations

from pathlib import Path
import tempfile

from vibe.core.tools.cache import ToolResultCache


class TestToolResultCache:
    """Test suite for ToolResultCache."""

    def test_cache_initialization(self) -> None:
        """Test that cache initializes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ToolResultCache(cache_dir=Path(tmpdir), enabled=True)
            assert cache.enabled is True
            assert cache.cache_dir == Path(tmpdir)
            assert len(cache) == 0

    def test_cache_disabled(self) -> None:
        """Test that disabled cache does not store or retrieve."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ToolResultCache(cache_dir=Path(tmpdir), enabled=False)
            cache.set("read_file", {"path": "test.py"}, "result")
            assert cache.get("read_file", {"path": "test.py"}) is None

    def test_cache_set_and_get(self) -> None:
        """Test basic set and get operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ToolResultCache(cache_dir=Path(tmpdir), enabled=True)

            # Test with simple data
            cache.set("read_file", {"path": "test.py"}, "file content")
            assert cache.get("read_file", {"path": "test.py"}) == "file content"

            # Test with complex data
            test_data = {"lines": ["line1", "line2"], "count": 2}
            cache.set("grep", {"pattern": "test"}, test_data)
            assert cache.get("grep", {"pattern": "test"}) == test_data

    def test_cache_miss(self) -> None:
        """Test cache miss returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ToolResultCache(cache_dir=Path(tmpdir), enabled=True)
            assert cache.get("read_file", {"path": "nonexistent.py"}) is None

    def test_cache_key_consistency(self) -> None:
        """Test that the same arguments produce the same key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ToolResultCache(cache_dir=Path(tmpdir), enabled=True)

            # Set with one order of args
            cache.set("grep", {"pattern": "test", "path": "file.py"}, "result1")

            # Get with different order (should still work due to JSON sorting)
            assert (
                cache.get("grep", {"path": "file.py", "pattern": "test"}) == "result1"
            )

    def test_cache_persistence(self) -> None:
        """Test that cache persists to disk and reloads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)

            # Create cache and add entry
            cache1 = ToolResultCache(cache_dir=cache_dir, enabled=True)
            cache1.set("read_file", {"path": "test.py"}, "persistent content")

            # Create new cache instance with same directory
            cache2 = ToolResultCache(cache_dir=cache_dir, enabled=True)

            # Should load from disk
            assert cache2.get("read_file", {"path": "test.py"}) == "persistent content"

    def test_cache_eviction(self) -> None:
        """Test that cache evicts old entries when max_size is reached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ToolResultCache(cache_dir=Path(tmpdir), enabled=True, max_size=3)

            # Add 4 entries
            cache.set("tool1", {}, "result1")
            cache.set("tool2", {}, "result2")
            cache.set("tool3", {}, "result3")
            assert len(cache) == 3

            # Add 4th entry - should evict oldest
            cache.set("tool4", {}, "result4")
            assert len(cache) == 3

            # First entry should be evicted
            assert cache.get("tool1", {}) is None

    def test_cache_invalidate(self) -> None:
        """Test invalidating specific cache entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ToolResultCache(cache_dir=Path(tmpdir), enabled=True)

            cache.set("read_file", {"path": "test.py"}, "content")
            assert cache.get("read_file", {"path": "test.py"}) == "content"

            # Invalidate
            cache.invalidate("read_file", {"path": "test.py"})
            assert cache.get("read_file", {"path": "test.py"}) is None

    def test_cache_clear(self) -> None:
        """Test clearing the entire cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ToolResultCache(cache_dir=Path(tmpdir), enabled=True)

            cache.set("tool1", {}, "result1")
            cache.set("tool2", {}, "result2")
            assert len(cache) == 2

            cache.clear()
            assert len(cache) == 0

            # Verify disk files are also cleared
            assert len(list(cache.cache_dir.glob("*.json"))) == 0

    def test_cache_with_unserializable_data(self) -> None:
        """Test that unserializable data is handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ToolResultCache(cache_dir=Path(tmpdir), enabled=True)

            # Data with a lambda (not JSON serializable)
            unserializable_data = {"func": lambda x: x}
            cache.set("test", {}, unserializable_data)

            # Should not crash, but won't persist to disk
            assert cache.get("test", {}) == unserializable_data

            # Create new cache - should not load from disk
            cache2 = ToolResultCache(cache_dir=Path(tmpdir), enabled=True)
            assert cache2.get("test", {}) is None

    def test_cache_with_different_tools(self) -> None:
        """Test that different tools have separate cache entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ToolResultCache(cache_dir=Path(tmpdir), enabled=True)

            cache.set("read_file", {"path": "a.py"}, "content a")
            cache.set("read_file", {"path": "b.py"}, "content b")
            cache.set("grep", {"pattern": "test"}, "grep result")

            assert cache.get("read_file", {"path": "a.py"}) == "content a"
            assert cache.get("read_file", {"path": "b.py"}) == "content b"
            assert cache.get("grep", {"pattern": "test"}) == "grep result"

    def test_cache_with_nested_args(self) -> None:
        """Test cache with nested argument structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ToolResultCache(cache_dir=Path(tmpdir), enabled=True)

            complex_args = {
                "path": "test.py",
                "options": {
                    "recursive": True,
                    "max_depth": 5,
                    "patterns": ["*.py", "*.md"],
                },
            }
            cache.set("complex_tool", complex_args, "complex result")

            # Same args in different order
            complex_args_2 = {
                "options": {
                    "max_depth": 5,
                    "patterns": ["*.py", "*.md"],
                    "recursive": True,
                },
                "path": "test.py",
            }
            assert cache.get("complex_tool", complex_args_2) == "complex result"
