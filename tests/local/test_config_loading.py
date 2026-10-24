"""Tests for hierarchical configuration loading."""

from __future__ import annotations

from pathlib import Path
import tempfile

from vibe.core.config.loading import HierarchicalConfigLoader, load_hierarchical_config


class TestHierarchicalConfigLoader:
    """Test suite for HierarchicalConfigLoader."""

    def test_load_base_config(self) -> None:
        """Test loading base configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "config.toml"
            config_file.write_text(
                "active_model = 'worker1'\nenabled_tools = ['read_file']"
            )

            loader = HierarchicalConfigLoader(config_dir)
            config = loader.load()

            assert config["active_model"] == "worker1"
            assert config["enabled_tools"] == ["read_file"]

    def test_load_with_profile(self) -> None:
        """Test loading configuration with a profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create base config
            config_file = config_dir / "config.toml"
            config_file.write_text("active_model = 'worker1'\nthinking = 'off'")

            # Create profile
            profiles_dir = config_dir / "profiles"
            profiles_dir.mkdir()
            profile_file = profiles_dir / "coding.toml"
            profile_file.write_text("active_model = 'worker2'\ntemperature = 0.7")

            loader = HierarchicalConfigLoader(config_dir)
            config = loader.load(profile="coding")

            # Profile should override base
            assert config["active_model"] == "worker2"
            # Base should be preserved
            assert config["thinking"] == "off"
            # Profile additions should be present
            assert config["temperature"] == 0.7

    def test_load_with_local_overrides(self) -> None:
        """Test loading configuration with local overrides."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create base config
            config_file = config_dir / "config.toml"
            config_file.write_text("active_model = 'worker1'\nthinking = 'off'")

            # Create local overrides
            local_file = config_dir / "local.toml"
            local_file.write_text("active_model = 'worker2'")

            loader = HierarchicalConfigLoader(config_dir)
            config = loader.load()

            # Local should override base
            assert config["active_model"] == "worker2"
            # Base should be preserved
            assert config["thinking"] == "off"

    def test_deep_merge(self) -> None:
        """Test deep merging of nested dictionaries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create base config with nested structure
            config_file = config_dir / "config.toml"
            config_file.write_text("""
[models]
active = "worker1"

[models.worker1]
provider = "llamacpp"
""")

            # Create profile with nested override
            profiles_dir = config_dir / "profiles"
            profiles_dir.mkdir()
            profile_file = profiles_dir / "test.toml"
            profile_file.write_text("""
[models]
active = "worker2"

[models.worker2]
provider = "albert"
""")

            loader = HierarchicalConfigLoader(config_dir)
            config = loader.load(profile="test")

            # Check that models are merged
            assert config["models"]["active"] == "worker2"
            assert config["models"]["worker1"]["provider"] == "llamacpp"
            assert config["models"]["worker2"]["provider"] == "albert"

    def test_missing_files(self) -> None:
        """Test loading with missing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            loader = HierarchicalConfigLoader(config_dir)
            config = loader.load(profile="nonexistent")
            assert config == {}

    def test_invalid_toml(self) -> None:
        """Test loading with invalid TOML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "config.toml"
            config_file.write_text("invalid toml [[[")

            loader = HierarchicalConfigLoader(config_dir)
            config = loader.load()
            assert config == {}

    def test_save_config(self) -> None:
        """Test saving configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            loader = HierarchicalConfigLoader(config_dir)

            config = {"active_model": "worker1", "enabled_tools": ["read_file"]}
            loader.save(config)

            # Verify file was created
            config_file = config_dir / "config.toml"
            assert config_file.exists()

            # Verify content
            loader2 = HierarchicalConfigLoader(config_dir)
            loaded = loader2.load()
            assert loaded["active_model"] == "worker1"

    def test_ensure_config_dir(self) -> None:
        """Test ensuring config directory exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "nested" / "config"
            loader = HierarchicalConfigLoader(config_dir)
            loader.ensure_config_dir()
            assert config_dir.exists()


class TestLoadHierarchicalConfig:
    """Test the convenience function."""

    def test_load_hierarchical_config(self) -> None:
        """Test the load_hierarchical_config function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "config.toml"
            config_file.write_text("active_model = 'worker1'")

            config = load_hierarchical_config(config_dir)
            assert config["active_model"] == "worker1"

    def test_load_with_profile(self) -> None:
        """Test loading with a profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            config_file = config_dir / "config.toml"
            config_file.write_text("active_model = 'worker1'")

            profiles_dir = config_dir / "profiles"
            profiles_dir.mkdir()
            profile_file = profiles_dir / "test.toml"
            profile_file.write_text("active_model = 'worker2'")

            config = load_hierarchical_config(config_dir, profile="test")
            assert config["active_model"] == "worker2"
