"""Sélection dynamique des prompts système.

Ce module permet de sélectionner le prompt optimal en function du type de tâche,
du modèle utilisé et du contexte d'exécution.
"""

from __future__ import annotations

from enum import StrEnum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class TaskType(StrEnum):
    """Types de tâches pour la sélection de prompts."""

    DEFAULT = auto()  # Tâche générale
    CODING = auto()  # Développement de code
    EXPLORATION = auto()  # Exploration de codebase
    TESTING = auto()  # Tests
    ANALYSIS = auto()  # Analyse de code
    DOCUMENTATION = auto()  # Génération de documentation
    REFACTORING = auto()  # Refactoring
    DEBUGGING = auto()  # Debugging
    PLANNING = auto()  # Planification
    REVIEW = auto()  # Revue de code


class PromptSelector:
    """Sélectionne le prompt optimal en function du contexte.

    Cette classe permet de choisir le prompt système le plus adapté
    en function de :
    - Le type de tâche
    - La taille du contexte du modèle
    - Le mode d'exécution (headless, etc.)
    - Les préférences utilisateur

    Exemple d'utilisation:
        >>> selector = PromptSelector()
        >>> prompt_id = selector.select(
        ...     task_type=TaskType.CODING,
        ...     model_context=8192,
        ...     is_headless=True
        ... )
    """

    # Mapping des types de tâches vers les prompts optimaux
    PROMPT_MAPPING: dict[TaskType, str] = {
        TaskType.DEFAULT: "cli",
        TaskType.CODING: "lean",  # Plus court pour le coding
        TaskType.EXPLORATION: "explore",  # Spécifique à l'exploration
        TaskType.TESTING: "tests",  # Prompt minimal pour les tests
        TaskType.ANALYSIS: "lean",  # Moins d'instructions pour l'analyse
        TaskType.DOCUMENTATION: "lean",  # Pour la documentation
        TaskType.REFACTORING: "lean",  # Pour le refactoring
        TaskType.DEBUGGING: "lean",  # Pour le debugging
        TaskType.PLANNING: "cli",  # Besoin de toutes les instructions
        TaskType.REVIEW: "lean",  # Pour la revue de code
    }

    # Seuil de contexte pour forcer un prompt minimal
    MINIMAL_CONTEXT_THRESHOLD = 4096

    # Seuil de contexte pour forcer un prompt lean
    LEAN_CONTEXT_THRESHOLD = 8192

    def __init__(self) -> None:
        """Initialise le sélecteur de prompts."""
        pass

    def select(
        self,
        task_type: TaskType | str = TaskType.DEFAULT,
        model_context: int | None = None,
        is_headless: bool = False,
        user_preference: str | None = None,
    ) -> str:
        """Sélectionne l'ID du prompt optimal.

        Args:
            task_type: Type de tâche (TaskType ou string).
            model_context: Taille du contexte du modèle (en tokens).
            is_headless: Mode headless (sans interaction utilisateur).
            user_preference: Préférence utilisateur explicite (override tout).

        Returns:
            ID du prompt à utiliser.
        """
        # Préférence utilisateur en priorité
        if user_preference:
            return user_preference

        # Convertir task_type en TaskType si nécessaire
        if isinstance(task_type, str):
            try:
                task_type = TaskType[task_type.upper()]
            except KeyError:
                task_type = TaskType.DEFAULT

        # Pour les petits contextes, forcer minimal
        if model_context and model_context < self.MINIMAL_CONTEXT_THRESHOLD:
            return "minimal"

        # Pour les contextes moyens, forcer lean
        if model_context and model_context < self.LEAN_CONTEXT_THRESHOLD:
            return "lean"

        # En mode headless, utiliser lean (moins de verbosité)
        if is_headless:
            return "lean"

        # Retourner le mapping par défaut
        return self.PROMPT_MAPPING.get(task_type, "cli")

    def select_with_fallback(
        self,
        task_type: TaskType | str = TaskType.DEFAULT,
        model_context: int | None = None,
        is_headless: bool = False,
        user_preference: str | None = None,
        available_prompts: list[str] | None = None,
    ) -> str:
        """Sélectionne le prompt avec fallback vers cli si non disponible.

        Args:
            task_type: Type de tâche.
            model_context: Taille du contexte du modèle.
            is_headless: Mode headless.
            user_preference: Préférence utilisateur.
            available_prompts: Liste des prompts disponibles.

        Returns:
            ID du prompt à utiliser.
        """
        selected = self.select(
            task_type=task_type,
            model_context=model_context,
            is_headless=is_headless,
            user_preference=user_preference,
        )

        # Vérifier si le prompt sélectionné est disponible
        if available_prompts and selected not in available_prompts:
            # Fallback vers cli
            if "cli" in available_prompts:
                return "cli"
            # Fallback vers le premier disponible
            return available_prompts[0] if available_prompts else "cli"

        return selected

    @classmethod
    def get_prompt_context_requirements(cls, prompt_id: str) -> dict[str, int]:
        """Retourne les exigences de contexte pour un prompt donné.

        Args:
            prompt_id: ID du prompt.

        Returns:
            Dictionnaire avec min_context et recommended_context.
        """
        # Estimation de la taille des prompts en tokens
        prompt_sizes = {
            "minimal": {"min_context": 1024, "recommended_context": 2048},
            "tests": {"min_context": 2048, "recommended_context": 4096},
            "compact": {"min_context": 2048, "recommended_context": 4096},
            "compact_system": {"min_context": 1024, "recommended_context": 2048},
            "lean": {"min_context": 4096, "recommended_context": 8192},
            "explore": {"min_context": 4096, "recommended_context": 8192},
            "cli": {"min_context": 8192, "recommended_context": 16384},
            "cli_2026-07_v2": {"min_context": 8192, "recommended_context": 16384},
            "cli_2026-08_v3": {"min_context": 8192, "recommended_context": 16384},
        }

        return prompt_sizes.get(
            prompt_id, {"min_context": 8192, "recommended_context": 16384}
        )

    @classmethod
    def detect_task_type(
        cls, user_message: str, previous_messages: list[dict] | None = None
    ) -> TaskType:
        """Détecte automatiquement le type de tâche à partir du message utilisateur.

        Args:
            user_message: Message de l'utilisateur.
            previous_messages: Messages précédents (optionnel).

        Returns:
            TaskType détecté.
        """
        user_message_lower = user_message.lower()

        # Détection par mots-clés
        coding_keywords = [
            "write a function",
            "create a class",
            "implement",
            "code",
            "write code",
            "develop",
            "build",
            "fix the bug",
            "add feature",
            "refactor",
            "modify",
            "change",
            "update",
            "edit",
            "write a script",
        ]

        exploration_keywords = [
            "explore",
            "browse",
            "navigate",
            "find",
            "search",
            "locate",
            "discover",
            "understand",
            "analyze the structure",
            "what does this do",
            "how does this work",
            "explain",
        ]

        testing_keywords = [
            "test",
            "write a test",
            "create test",
            "unit test",
            "integration test",
            "verify",
            "check",
            "assert",
            "run tests",
            "fix the test",
            "test coverage",
        ]

        analysis_keywords = [
            "analyze",
            "review",
            "audit",
            "profile",
            "optimize",
            "performance",
            "memory",
            "bottleneck",
            "complexity",
            "why is this slow",
            "what's wrong",
            "debug",
        ]

        documentation_keywords = [
            "document",
            "write docs",
            "create documentation",
            "add comments",
            "explain",
            "describe",
            "README",
            "docstring",
            "help text",
        ]

        debugging_keywords = [
            "debug",
            "fix",
            "error",
            "exception",
            "traceback",
            "why is this failing",
            "what's wrong with",
            "broken",
            "not working",
            "issue",
            "problem",
            "bug",
        ]

        planning_keywords = [
            "plan",
            "design",
            "architecture",
            "strategy",
            "roadmap",
            "approach",
            "how should I",
            "what's the best way",
            "steps",
            "process",
            "workflow",
        ]

        # Vérifier les mots-clés dans l'ordre de priorité
        if any(kw in user_message_lower for kw in debugging_keywords):
            return TaskType.DEBUGGING

        if any(kw in user_message_lower for kw in testing_keywords):
            return TaskType.TESTING

        if any(kw in user_message_lower for kw in documentation_keywords):
            return TaskType.DOCUMENTATION

        if any(kw in user_message_lower for kw in analysis_keywords):
            return TaskType.ANALYSIS

        if any(kw in user_message_lower for kw in exploration_keywords):
            return TaskType.EXPLORATION

        if any(kw in user_message_lower for kw in planning_keywords):
            return TaskType.PLANNING

        if any(kw in user_message_lower for kw in coding_keywords):
            return TaskType.CODING

        # Par défaut
        return TaskType.DEFAULT


# Instance globale du sélecteur
prompt_selector = PromptSelector()
