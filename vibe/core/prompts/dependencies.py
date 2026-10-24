"""Détection des changements de dépendances pour les prompts système.

Ce module permet de calculer un hash unique basé sur l'état des dépendances
du prompt système (configuration, skills, agents, outils, etc.) afin de
détecter quand le prompt doit être régénéré.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibe.core.agents.manager import AgentManager
    from vibe.core.config import VibeConfigSchema
    from vibe.core.skills.manager import SkillManager
    from vibe.core.tools.manager import ToolManager


class SystemPromptDependencies:
    """Calcule et gère les dépendances du prompt système.

    Cette classe permet de détecter si le prompt système doit être
    régénéré en function des changements de :
    - Configuration (system_prompt, flags include_*)
    - Skills disponibles
    - Agents disponibles
    - Outils disponibles
    - Mode headless
    - Modèle actif
    """

    def __init__(
        self,
        config: VibeConfigSchema | None = None,
        skill_manager: SkillManager | None = None,
        agent_manager: AgentManager | None = None,
        tool_manager: ToolManager | None = None,
    ) -> None:
        """Initialise le gestionnaire de dépendances.

        Args:
            config: Configuration Vibe.
            skill_manager: Gestionnaire des skills.
            agent_manager: Gestionnaire des agents.
            tool_manager: Gestionnaire des outils.
        """
        self._config = config
        self._skill_manager = skill_manager
        self._agent_manager = agent_manager
        self._tool_manager = tool_manager
        self._last_hash: str | None = None

    def compute_hash(self) -> str:
        """Calcule un hash unique basé sur toutes les dépendances.

        Returns:
            Un hash SHA256 tronqué à 16 caractères.
        """
        deps_parts = []

        # Configuration
        if self._config:
            deps_parts.append(str(self._config.system_prompt))
            deps_parts.append(str(self._config.include_commit_signature))
            deps_parts.append(str(self._config.include_model_info))
            deps_parts.append(str(self._config.include_prompt_detail))
            deps_parts.append(str(self._config.include_project_context))

            # Information sur le modèle
            try:
                model = self._config.get_active_model()
                deps_parts.append(str(model.name) if model else "")
                deps_parts.append(str(model.alias) if model else "")
            except Exception:
                deps_parts.append("")
                deps_parts.append("")

        # Skills
        if self._skill_manager:
            try:
                available_skills = self._skill_manager.available_skills
                model_invocable = {
                    name: skill
                    for name, skill in available_skills.items()
                    if skill.model_invocable
                }
                user_invocable = any(
                    skill.user_invocable for skill in available_skills.values()
                )
                deps_parts.append(str(sorted(model_invocable.keys())))
                deps_parts.append(str(user_invocable))
            except Exception:
                deps_parts.append("[]")
                deps_parts.append("False")

        # Agents
        if self._agent_manager:
            try:
                agents = self._agent_manager.get_subagents()
                deps_parts.append(str(sorted(a.name for a in agents)))
            except Exception:
                deps_parts.append("[]")

        # Outils
        if self._tool_manager:
            try:
                tools = self._tool_manager.get_tools()
                deps_parts.append(str(sorted(t.name for t in tools)))
            except Exception:
                deps_parts.append("[]")

        # Calculer le hash
        deps_str = ":".join(deps_parts)
        return hashlib.sha256(deps_str.encode()).hexdigest()[:16]

    def has_changed(self) -> bool:
        """Vérifie si les dépendances ont changé depuis le dernier check.

        Returns:
            True si les dépendances ont changé, False sinon.
        """
        current_hash = self.compute_hash()

        if self._last_hash is None:
            self._last_hash = current_hash
            return True  # Premier appel, considérer comme changé

        has_changed = self._last_hash != current_hash
        self._last_hash = current_hash
        return has_changed

    def get_current_hash(self) -> str:
        """Retourne le hash courant des dépendances.

        Returns:
            Le hash SHA256 tronqué à 16 caractères.
        """
        return self.compute_hash()

    def reset(self) -> None:
        """Réinitialise le cache du dernier hash."""
        self._last_hash = None


class DynamicPromptDependencies:
    """Gestionnaire de dépendances pour les prompts dynamiques.

    Similaire à SystemPromptDependencies mais conçu pour être utilisé
    directement dans le code sans stocker de références aux managers.
    """

    @staticmethod
    @staticmethod
    def compute_hash(
        config_system_prompt: str,
        include_flags: tuple[bool, bool, bool, bool],
        skills_sorted: str,
        agents_sorted: str,
        tools_sorted: str,
        extra_info: str = "",
    ) -> str:
        """Calcule un hash unique basé sur les dépendances."""
        deps = [
            str(config_system_prompt),
            str(include_flags),
            skills_sorted,
            agents_sorted,
            tools_sorted,
            extra_info,
        ]
        return hashlib.sha256(":".join(deps).encode()).hexdigest()[:16]
