"""Hierarchical configuration loading for vibe-local-debian.

This module provides functionality to load configuration from multiple
sources with hierarchical merging, allowing for base configurations,
profile overrides, and local customizations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomli
import tomli_w

from vibe.observability.logging import logger


class HierarchicalConfigLoader:
    """Loader for hierarchical configuration files.

    This loader supports loading configuration from multiple TOML files
    and merging them hierarchically. The merge order is:
    1. Base configuration (config.toml)
    2. Profile configuration (profiles/<profile>.toml)
    3. Local overrides (local.toml)

    Later files override earlier ones, with dictionary values being merged
    rather than replaced.
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        """Initialize the hierarchical config loader.

        Args:
            config_dir: The directory containing configuration files.
                       Defaults to ~/.vibe/
        """
        self.config_dir = config_dir or Path("~/.vibe").expanduser()

    def load(self, profile: str | None = None) -> dict[str, Any]:
        """Load configuration from multiple sources with hierarchical merging.

        Args:
            profile: Optional profile name to load from profiles/ directory.

        Returns:
            Merged configuration dictionary.
        """
        config: dict[str, Any] = {}

        # 1. Load base configuration
        base_config = self._load_file(self.config_dir / "config.toml")
        if base_config:
            config = self._deep_merge(config, base_config)

        # 2. Load profile configuration
        if profile:
            profile_config = self._load_profile(profile)
            if profile_config:
                config = self._deep_merge(config, profile_config)

        # 3. Load local overrides
        local_config = self._load_file(self.config_dir / "local.toml")
        if local_config:
            config = self._deep_merge(config, local_config)

        return config

    def _load_profile(self, profile: str) -> dict[str, Any]:
        """Load a profile configuration file.

        Args:
            profile: The profile name.

        Returns:
            Profile configuration dictionary or empty dict if not found.
        """
        profiles_dir = self.config_dir / "profiles"
        profile_path = profiles_dir / f"{profile}.toml"
        return self._load_file(profile_path)

    def _load_file(self, path: Path) -> dict[str, Any]:
        """Load a TOML file.

        Args:
            path: Path to the TOML file.

        Returns:
            Configuration dictionary or empty dict if file doesn't exist.
        """
        try:
            if path.exists():
                with open(path, "rb") as f:
                    return tomli.load(f)
        except (OSError, tomli.TOMLDecodeError) as e:
            logger.warning(f"Failed to load config file {path}: {e}")
        return {}

    def _deep_merge(
        self, base: dict[str, Any], override: dict[str, Any]
    ) -> dict[str, Any]:
        """Deep merge two dictionaries.

        Values from override take precedence over base. Nested dictionaries
        are merged recursively.

        Args:
            base: The base dictionary.
            override: The dictionary to merge over base.

        Returns:
            Merged dictionary.
        """
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def save(self, config: dict[str, Any], path: Path | None = None) -> None:
        """Save configuration to a file.

        Args:
            config: Configuration dictionary to save.
            path: Path to save to. Defaults to config.toml in config_dir.
        """
        save_path = path or self.config_dir / "config.toml"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(save_path, "wb") as f:
                tomli_w.dump(config, f)
        except (OSError, TypeError) as e:
            logger.error(f"Failed to save config to {save_path}: {e}")
            raise

    def get_config_dir(self) -> Path:
        """Get the configuration directory.

        Returns:
            Path to the configuration directory.
        """
        return self.config_dir

    def ensure_config_dir(self) -> None:
        """Ensure the configuration directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)


def load_hierarchical_config(
    config_dir: Path | None = None, profile: str | None = None
) -> dict[str, Any]:
    """Convenience function to load hierarchical configuration.

    Args:
        config_dir: The directory containing configuration files.
        profile: Optional profile name to load.

    Returns:
        Merged configuration dictionary.
    """
    loader = HierarchicalConfigLoader(config_dir)
    return loader.load(profile)
