"""Configuration profiles for vibe-local-debian.

This module provides predefined configuration profiles that can be
activated via the --profile CLI flag or config.profiles.active setting.
"""

from __future__ import annotations

from typing import Any

# Default profile - balanced configuration
DEFAULT_PROFILE: dict[str, Any] = {
    "active_model": "worker1",
    "enabled_tools": [
        "bash",
        "read_file",
        "write_file",
        "edit",
        "grep",
        "ask_user_question",
        "todo",
    ],
    "thinking": "off",
    "auto_compact_threshold": 80000,
}

# Coding profile - optimized for coding tasks
CODING_PROFILE: dict[str, Any] = {
    "active_model": "worker1",
    "enabled_tools": [
        "bash",
        "read_file",
        "write_file",
        "edit",
        "grep",
        "ask_user_question",
        "todo",
    ],
    "thinking": "off",
    "auto_compact_threshold": 75000,
    "temperature": 0.7,
}

# Minimal profile - read-only access
MINIMAL_PROFILE: dict[str, Any] = {
    "active_model": "worker1",
    "enabled_tools": ["read_file", "grep"],
    "thinking": "off",
    "auto_compact_threshold": 80000,
}

# Full profile - all tools enabled
FULL_PROFILE: dict[str, Any] = {
    "active_model": "worker1",
    "enabled_tools": [
        "bash",
        "read_file",
        "write_file",
        "edit",
        "grep",
        "ask_user_question",
        "todo",
        "mcp_rea_open_binary",
        "mcp_rea_binary_overview",
        "mcp_rea_binary_session",
        "mcp_rea_close_binary",
        "mcp_rea_search_procedures",
        "mcp_rea_search_strings",
        "mcp_rea_procedure_info",
        "mcp_rea_procedure_pseudo_code",
        "mcp_rea_procedure_assembly",
        "mcp_rea_procedure_callers",
        "mcp_rea_procedure_callees",
        "mcp_rea_procedure_references",
        "mcp_rea_xrefs",
        "mcp_rea_address_name",
        "mcp_rea_set_address_name",
        "mcp_rea_set_comment",
        "mcp_rea_read_bytes",
        "mcp_rea_read_function_instructions",
        "mcp_rea_resolve_containing_procedure",
        "mcp_rea_list_unknowns",
        "mcp_rea_record_unknown",
        "mcp_rea_trace_feature",
    ],
    "thinking": "off",
    "auto_compact_threshold": 80000,
}

# REA profile - optimized for reverse engineering
REA_PROFILE: dict[str, Any] = {
    "active_model": "worker1",
    "enabled_tools": [
        "read_file",
        "grep",
        "mcp_rea_open_binary",
        "mcp_rea_binary_overview",
        "mcp_rea_binary_session",
        "mcp_rea_close_binary",
        "mcp_rea_search_procedures",
        "mcp_rea_search_strings",
        "mcp_rea_procedure_info",
        "mcp_rea_procedure_pseudo_code",
        "mcp_rea_procedure_assembly",
        "mcp_rea_procedure_callers",
        "mcp_rea_procedure_callees",
        "mcp_rea_procedure_references",
        "mcp_rea_xrefs",
        "mcp_rea_address_name",
        "mcp_rea_set_address_name",
        "mcp_rea_set_comment",
        "mcp_rea_read_bytes",
        "mcp_rea_read_function_instructions",
        "mcp_rea_resolve_containing_procedure",
        "mcp_rea_list_unknowns",
        "mcp_rea_record_unknown",
        "mcp_rea_trace_feature",
    ],
    "thinking": "off",
    "auto_compact_threshold": 75000,
}

# Secure profile - minimal permissions
SECURE_PROFILE: dict[str, Any] = {
    "active_model": "worker1",
    "enabled_tools": ["read_file", "grep"],
    "thinking": "off",
    "auto_compact_threshold": 80000,
}

# All available profiles
PROFILES: dict[str, dict[str, Any]] = {
    "default": DEFAULT_PROFILE,
    "coding": CODING_PROFILE,
    "minimal": MINIMAL_PROFILE,
    "full": FULL_PROFILE,
    "rea": REA_PROFILE,
    "secure": SECURE_PROFILE,
}


class ConfigProfiles:
    """Manager for configuration profiles.

    This class provides methods to work with predefined configuration profiles.
    """

    @classmethod
    def get_profile(cls, name: str) -> dict[str, Any]:
        """Get a profile by name.

        Args:
            name: The name of the profile.

        Returns:
            The profile configuration dictionary.

        Raises:
            ValueError: If the profile name is not found.
        """
        if name not in PROFILES:
            raise ValueError(
                f"Unknown profile: {name}. Available profiles: {list(PROFILES.keys())}"
            )
        return PROFILES[name].copy()

    @classmethod
    def list_profiles(cls) -> list[str]:
        """List all available profile names.

        Returns:
            List of profile names.
        """
        return list(PROFILES.keys())

    @classmethod
    def get_profile_description(cls, name: str) -> str:
        """Get a description of a profile.

        Args:
            name: The name of the profile.

        Returns:
            A description of the profile.
        """
        descriptions = {
            "default": "Balanced configuration with common tools",
            "coding": "Optimized for coding tasks with worker1",
            "minimal": "Read-only access with minimal tools",
            "full": "All tools enabled including REA tools",
            "rea": "Optimized for reverse engineering with REA tools",
            "secure": "Minimal permissions for secure environments",
        }
        return descriptions.get(name, "Unknown profile")

    @classmethod
    def apply_profile(
        cls, base_config: dict[str, Any], profile_name: str
    ) -> dict[str, Any]:
        """Apply a profile to a base configuration.

        This method merges the profile configuration with the base configuration,
        with profile values taking precedence.

        Args:
            base_config: The base configuration to apply the profile to.
            profile_name: The name of the profile to apply.

        Returns:
            The merged configuration.
        """
        profile = cls.get_profile(profile_name)
        result = base_config.copy()

        # Apply profile settings, with profile values taking precedence
        for key, value in profile.items():
            if isinstance(value, list):
                # For lists, replace the entire list
                result[key] = value.copy()
            elif isinstance(value, dict):
                # For dicts, merge recursively
                if key in result and isinstance(result[key], dict):
                    result[key] = {**result[key], **value}
                else:
                    result[key] = value.copy()
            else:
                # For simple values, replace
                result[key] = value

        return result
