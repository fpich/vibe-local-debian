from __future__ import annotations

from vibe.core.skills.builtins.skill_creator import SKILL as SKILL_CREATOR_SKILL
from vibe.core.skills.models import SkillInfo

BUILTIN_SKILLS: dict[str, SkillInfo] = {
    skill.name: skill for skill in [SKILL_CREATOR_SKILL]
}
