"""Tests for configuration profiles."""

from __future__ import annotations

import pytest

from vibe.core.config.profiles import (
    CODING_PROFILE,
    DEFAULT_PROFILE,
    FULL_PROFILE,
    MINIMAL_PROFILE,
    PROFILES,
    REA_PROFILE,
    SECURE_PROFILE,
    ConfigProfiles,
)


class TestConfigProfiles:
    """Test suite for ConfigProfiles."""

    def test_get_profile_default(self) -> None:
        """Test getting the default profile."""
        profile = ConfigProfiles.get_profile("default")
        assert profile == DEFAULT_PROFILE

    def test_get_profile_coding(self) -> None:
        """Test getting the coding profile."""
        profile = ConfigProfiles.get_profile("coding")
        assert profile == CODING_PROFILE

    def test_get_profile_minimal(self) -> None:
        """Test getting the minimal profile."""
        profile = ConfigProfiles.get_profile("minimal")
        assert profile == MINIMAL_PROFILE

    def test_get_profile_full(self) -> None:
        """Test getting the full profile."""
        profile = ConfigProfiles.get_profile("full")
        assert profile == FULL_PROFILE

    def test_get_profile_rea(self) -> None:
        """Test getting the REA profile."""
        profile = ConfigProfiles.get_profile("rea")
        assert profile == REA_PROFILE

    def test_get_profile_secure(self) -> None:
        """Test getting the secure profile."""
        profile = ConfigProfiles.get_profile("secure")
        assert profile == SECURE_PROFILE

    def test_get_profile_unknown(self) -> None:
        """Test getting an unknown profile raises ValueError."""
        with pytest.raises(ValueError, match="Unknown profile"):
            ConfigProfiles.get_profile("unknown")

    def test_list_profiles(self) -> None:
        """Test listing all profiles."""
        profiles = ConfigProfiles.list_profiles()
        assert set(profiles) == set(PROFILES.keys())
        assert "default" in profiles
        assert "coding" in profiles
        assert "minimal" in profiles
        assert "full" in profiles
        assert "rea" in profiles
        assert "secure" in profiles

    def test_get_profile_description(self) -> None:
        """Test getting profile descriptions."""
        desc = ConfigProfiles.get_profile_description("default")
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_get_profile_description_unknown(self) -> None:
        """Test getting description for unknown profile."""
        desc = ConfigProfiles.get_profile_description("unknown")
        assert desc == "Unknown profile"

    def test_apply_profile(self) -> None:
        """Test applying a profile to a base configuration."""
        base_config = {
            "active_model": "worker2",
            "enabled_tools": ["read_file"],
            "temperature": 0.5,
        }

        result = ConfigProfiles.apply_profile(base_config, "coding")

        # Profile should override active_model
        assert result["active_model"] == "worker1"

        # Profile should override enabled_tools
        assert result["enabled_tools"] == CODING_PROFILE["enabled_tools"]

        # Profile should override temperature
        assert result["temperature"] == CODING_PROFILE["temperature"]

    def test_apply_profile_preserves_base(self) -> None:
        """Test that applying a profile preserves base config values not in profile."""
        base_config = {
            "active_model": "worker2",
            "enabled_tools": ["read_file"],
            "custom_setting": "custom_value",
        }

        result = ConfigProfiles.apply_profile(base_config, "minimal")

        # Custom setting should be preserved
        assert result["custom_setting"] == "custom_value"

    def test_apply_profile_does_not_modify_original(self) -> None:
        """Test that applying a profile doesn't modify the original config."""
        base_config = {"active_model": "worker2", "enabled_tools": ["read_file"]}
        original_active_model = base_config["active_model"]

        ConfigProfiles.apply_profile(base_config, "coding")

        # Original should be unchanged
        assert base_config["active_model"] == original_active_model


class TestProfileContents:
    """Test the contents of predefined profiles."""

    def test_default_profile_has_required_keys(self) -> None:
        """Test that default profile has required keys."""
        assert "active_model" in DEFAULT_PROFILE
        assert "enabled_tools" in DEFAULT_PROFILE
        assert isinstance(DEFAULT_PROFILE["enabled_tools"], list)

    def test_coding_profile_has_bash(self) -> None:
        """Test that coding profile includes bash."""
        assert "bash" in CODING_PROFILE["enabled_tools"]

    def test_minimal_profile_no_bash(self) -> None:
        """Test that minimal profile doesn't include bash."""
        assert "bash" not in MINIMAL_PROFILE["enabled_tools"]

    def test_full_profile_has_rea_tools(self) -> None:
        """Test that full profile includes REA tools."""
        rea_tools = [
            t for t in FULL_PROFILE["enabled_tools"] if t.startswith("mcp_rea_")
        ]
        assert len(rea_tools) > 0

    def test_rea_profile_only_rea_tools(self) -> None:
        """Test that REA profile focuses on REA tools."""
        tools = REA_PROFILE["enabled_tools"]
        # Should have read_file and grep
        assert "read_file" in tools
        assert "grep" in tools
        # Should have REA tools
        rea_tools = [t for t in tools if t.startswith("mcp_rea_")]
        assert len(rea_tools) > 0

    def test_secure_profile_minimal_tools(self) -> None:
        """Test that secure profile has minimal tools."""
        tools = SECURE_PROFILE["enabled_tools"]
        assert len(tools) == 2
        assert "read_file" in tools
        assert "grep" in tools
