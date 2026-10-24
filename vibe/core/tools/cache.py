from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ToolResultCache:
    """Cache for tool execution results to avoid redundant computations.

    This cache stores the results of tool calls (e.g., read_file, grep) to speed up
    repeated operations. The cache is persisted to disk in ~/.vibe/cache/tools/.

    Attributes:
        cache_dir: Directory where cache files are stored.
        enabled: Whether caching is enabled.
        max_size: Maximum number of entries to keep in memory.
    """

    def __init__(
        self, cache_dir: Path | None = None, enabled: bool = True, max_size: int = 100
    ) -> None:
        """Initialize the tool result cache.

        Args:
            cache_dir: Directory for cache files. Defaults to ~/.vibe/cache/tools/.
            enabled: Whether caching is enabled.
            max_size: Maximum number of entries to keep in memory.
        """
        self.cache_dir = cache_dir or Path("~/.vibe/cache/tools").expanduser()
        self.enabled = enabled
        self.max_size = max_size
        self._cache: dict[str, Any] = {}

        if enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def _get_key(self, tool: str, args: dict[str, Any]) -> str:
        """Generate a unique cache key for a tool call.

        Args:
            tool: Name of the tool.
            args: Arguments passed to the tool.

        Returns:
            A unique hash string for the tool call.
        """
        # Sort keys for consistent hashing
        sorted_args = json.dumps({"tool": tool, "args": args}, sort_keys=True)
        return hashlib.sha256(sorted_args.encode()).hexdigest()[:16]

    def get(self, tool: str, args: dict[str, Any]) -> Any | None:
        """Retrieve a cached result for a tool call.

        Args:
            tool: Name of the tool.
            args: Arguments passed to the tool.

        Returns:
            The cached result if found, None otherwise.
        """
        if not self.enabled:
            return None

        key = self._get_key(tool, args)

        # Check in-memory cache first
        if key in self._cache:
            return self._cache[key]

        # Check disk cache
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, encoding="utf-8") as f:
                    result = json.load(f)
                    self._cache[key] = result
                    return result
            except (json.JSONDecodeError, OSError):
                return None

        return None

    def set(self, tool: str, args: dict[str, Any], result: Any) -> None:
        """Store a tool result in the cache.

        Args:
            tool: Name of the tool.
            args: Arguments passed to the tool.
            result: Result to cache.
        """
        if not self.enabled:
            return

        key = self._get_key(tool, args)

        # Store on disk first (if serializable)
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(result, f)
        except (TypeError, OSError):
            # Result is not JSON-serializable or disk error
            pass

        # Store in memory
        self._cache[key] = result

        # Evict oldest entries if over max_size
        if len(self._cache) > self.max_size:
            # Simple FIFO eviction - remove from both memory and disk
            oldest_key = next(iter(self._cache))
            self._cache.pop(oldest_key)
            # Remove from disk
            try:
                (self.cache_dir / f"{oldest_key}.json").unlink()
            except OSError:
                pass

    def _load(self) -> None:
        """Load cache entries from disk into memory."""
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, encoding="utf-8") as f:
                        self._cache[cache_file.stem] = json.load(f)
                except (json.JSONDecodeError, OSError):
                    continue
        except OSError:
            pass

    def clear(self) -> None:
        """Clear all cached entries from memory and disk."""
        self._cache.clear()
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
        except OSError:
            pass

    def invalidate(self, tool: str, args: dict[str, Any]) -> None:
        """Invalidate a specific cache entry.

        Args:
            tool: Name of the tool.
            args: Arguments passed to the tool.
        """
        key = self._get_key(tool, args)
        if key in self._cache:
            del self._cache[key]

        cache_file = self.cache_dir / f"{key}.json"
        try:
            cache_file.unlink()
        except OSError:
            pass

    def __len__(self) -> int:
        """Return the number of cached entries."""
        return len(self._cache)
