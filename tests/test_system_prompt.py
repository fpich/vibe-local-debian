from __future__ import annotations

from datetime import date

import pytest

from tests.conftest import ConfigBuilder, OrchestratorLoader
from vibe.core.agents import AgentManager
from vibe.core.config import VibeConfigSchema
from vibe.core.scratchpad import init_scratchpad
from vibe.core.skills.manager import SkillManager
from vibe.core.system_prompt import get_universal_system_prompt


def _hide_standard_git_installs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)


def test_system_prompt_reports_resolved_model_when_unpinned(
    build_config: ConfigBuilder, load_orchestrator: OrchestratorLoader[VibeConfigSchema]
) -> None:
    # The unpinned default (active_model == "") must still report the resolved
    # model alias, not an empty name.
    config = build_config(
        include_model_info=True,
        include_prompt_detail=False,
        include_commit_signature=False,
    )
    assert config.active_model == ""
    skill_manager = SkillManager(lambda: config)
    agent_manager = AgentManager(load_orchestrator(config))

    prompt = get_universal_system_prompt(config, skill_manager, agent_manager)

    assert f"Your model name is: `{config.get_active_model().alias}`" in prompt
    assert "Your model name is: ``" not in prompt


def test_scratchpad_section_included_when_passed(
    build_config: ConfigBuilder, load_orchestrator: OrchestratorLoader[VibeConfigSchema]
) -> None:
    sp = init_scratchpad("test-session")
    config = build_config(
        include_prompt_detail=True,
        include_model_info=False,
        include_commit_signature=False,
    )
    skill_manager = SkillManager(lambda: config)
    agent_manager = AgentManager(load_orchestrator(config))

    prompt = get_universal_system_prompt(
        config, skill_manager, agent_manager, scratchpad_dir=sp
    )

    assert "# Scratchpad Directory" in prompt
    assert sp is not None
    assert str(sp) in prompt


def test_scratchpad_section_absent_when_not_passed(
    build_config: ConfigBuilder, load_orchestrator: OrchestratorLoader[VibeConfigSchema]
) -> None:
    config = build_config(
        include_prompt_detail=True,
        include_model_info=False,
        include_commit_signature=False,
    )
    skill_manager = SkillManager(lambda: config)
    agent_manager = AgentManager(load_orchestrator(config))

    prompt = get_universal_system_prompt(config, skill_manager, agent_manager)

    assert "Scratchpad Directory" not in prompt


def test_headless_section_included_when_enabled(
    build_config: ConfigBuilder, load_orchestrator: OrchestratorLoader[VibeConfigSchema]
) -> None:
    config = build_config(include_model_info=False, include_commit_signature=False)
    skill_manager = SkillManager(lambda: config)
    agent_manager = AgentManager(load_orchestrator(config))

    prompt = get_universal_system_prompt(
        config, skill_manager, agent_manager, headless=True
    )

    assert "# Headless Mode" in prompt
    assert "no human is available to respond" in prompt


def test_headless_section_absent_by_default(
    build_config: ConfigBuilder, load_orchestrator: OrchestratorLoader[VibeConfigSchema]
) -> None:
    config = build_config(include_model_info=False, include_commit_signature=False)
    skill_manager = SkillManager(lambda: config)
    agent_manager = AgentManager(load_orchestrator(config))

    prompt = get_universal_system_prompt(config, skill_manager, agent_manager)

    assert "Headless Mode" not in prompt


def test_current_date_placeholder_substituted_in_prompt(
    build_config: ConfigBuilder, load_orchestrator: OrchestratorLoader[VibeConfigSchema]
) -> None:
    config = build_config(
        system_prompt_id="cli", include_model_info=False, include_commit_signature=False
    )
    skill_manager = SkillManager(lambda: config)
    agent_manager = AgentManager(load_orchestrator(config))

    prompt = get_universal_system_prompt(config, skill_manager, agent_manager)

    today = date.today()
    expected = f"Today's date is {today.isoformat()} ({today.strftime('%A')})."
    assert expected in prompt
    assert "$current_date" not in prompt


def test_v3_system_prompt_variant_is_available_to_legacy_harness(
    build_config: ConfigBuilder, load_orchestrator: OrchestratorLoader[VibeConfigSchema]
) -> None:
    config = build_config(
        system_prompt_id="cli_2026-08_v3",
        include_model_info=False,
        include_commit_signature=False,
    )
    skill_manager = SkillManager(lambda: config)
    agent_manager = AgentManager(load_orchestrator(config))

    prompt = get_universal_system_prompt(config, skill_manager, agent_manager)

    assert prompt.startswith("You are Mistral Vibe, an interactive coding agent.")
    assert "# Harness" in prompt
    assert "invoke it via the `skill` tool" in prompt
    assert "## Instruction hierarchy" not in prompt
