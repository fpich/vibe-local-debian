"""Estimation et gestion des tokens pour les prompts et messages.

Ce module fournit des outils pour estimer le nombre de tokens dans les prompts
et messages, et pour vérifier que les requêtes ne dépassent pas le contexte du modèle.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


class TokenEstimator:
    """Estime le nombre de tokens dans un texte.

    Cette classe fournit des méthodes pour estimer le nombre de tokens
    dans un prompt ou message, afin de prévenir les erreurs de contexte.

    L'estimation est basée sur des heuristiques :
    - Texte normal : ~4 caractères = 1 token
    - Code : ~3 caractères = 1 token (plus dense)
    - JSON/XML : ~3.5 caractères = 1 token

    Exemple d'utilisation:
        >>> estimator = TokenEstimator()
        >>> tokens = estimator.estimate("Hello, world!")
        >>> print(f"Estimated tokens: {tokens}")
    """

    # Ratios caractères/tokens par type de contenu
    CHAR_TO_TOKEN_RATIOS = {
        "text": 4.0,  # Texte normal
        "code": 3.0,  # Code source
        "json": 3.5,  # JSON
        "xml": 3.5,  # XML
        "markdown": 3.8,  # Markdown
    }

    # Mots-clés pour détecter le type de contenu
    CODE_KEYWORDS = [
        "def ",
        "class ",
        "import ",
        "from ",
        "return ",
        "if ",
        "else",
        "for ",
        "while ",
        "try:",
        "except",
        "finally",
        "with ",
        "lambda",
        "->",
        "self.",
        "@",
        "# ",
        "//",
        "/*",
        "*/",
        "function",
        "var ",
        "let ",
        "const ",
        "public ",
        "private",
    ]

    JSON_KEYWORDS = ["{", "}", "[", "]", ":", ",", '"', "true", "false", "null"]
    XML_KEYWORDS = ["<", ">", "/", "=", "<?", "?>"]

    @classmethod
    def _detect_content_type(cls, text: str) -> str:
        """Détecte le type de contenu d'un texte.

        Args:
            text: Texte à analyser.

        Returns:
            Type de contenu : "text", "code", "json", ou "xml".
        """
        if not text.strip():
            return "text"

        # Vérifier si c'est du JSON
        if any(kw in text for kw in cls.JSON_KEYWORDS):
            try:
                import json

                json.loads(text)
                return "json"
            except (json.JSONDecodeError, ValueError):
                pass

        # Vérifier si c'est du XML
        if any(kw in text for kw in cls.XML_KEYWORDS):
            return "xml"

        # Vérifier si c'est du code
        if any(kw in text for kw in cls.CODE_KEYWORDS):
            return "code"

        # Par défaut, c'est du texte
        return "text"

    @classmethod
    def _is_code_block(cls, text: str) -> bool:
        """Détecte si un texte est un bloc de code (markdown).

        Args:
            text: Texte à analyser.

        Returns:
            True si le texte est un bloc de code markdown.
        """
        # Blocs de code markdown : ```lang ou ~~~lang
        code_block_pattern = r"^```\w*$|^~~~\w*$"
        return bool(re.match(code_block_pattern, text.strip()))

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Estime le nombre de tokens dans un texte.

        Args:
            text: Texte à estimer.

        Returns:
            Nombre estimé de tokens.
        """
        if not text:
            return 0

        # Détecter le type de contenu
        content_type = cls._detect_content_type(text)
        ratio = cls.CHAR_TO_TOKEN_RATIOS.get(content_type, 4.0)

        # Compter les caractères (en ignorant les escapes de fin)
        stripped_text = text.rstrip()
        char_count = len(stripped_text)

        # Estimation
        return max(1, int(char_count / ratio))

    @classmethod
    def estimate_message_tokens(cls, message: dict[str, Any]) -> int:
        """Estime le nombre de tokens dans un message.

        Args:
            message: Dictionnaire représentant un message (role, content, etc.).

        Returns:
            Nombre estimé de tokens.
        """
        content = message.get("content", "")
        if isinstance(content, list):
            # Messages avec parts (ex: Anthropic)
            return sum(cls.estimate_tokens(part.get("text", "")) for part in content)
        return cls.estimate_tokens(content)

    @classmethod
    def estimate_messages_tokens(cls, messages: Sequence[dict[str, Any]]) -> int:
        """Estime le nombre total de tokens dans une liste de messages.

        Args:
            messages: Liste de messages.

        Returns:
            Nombre total estimé de tokens.
        """
        return sum(cls.estimate_message_tokens(msg) for msg in messages)

    @classmethod
    def can_send_request(
        cls,
        system_prompt: str,
        messages: Sequence[dict[str, Any]],
        model_context: int,
        reserved_tokens: int = 1000,
    ) -> tuple[bool, dict[str, int]]:
        """Vérifie si une requête peut être envoyée sans dépasser le contexte.

        Args:
            system_prompt: Prompt système.
            messages: Liste des messages.
            model_context: Taille du contexte du modèle (en tokens).
            reserved_tokens: Tokens réservés pour la réponse et marge de sécurité.

        Returns:
            Tuple de (peut_être_envoyé, statistiques).
            statistiques contient :
            - prompt_tokens: Tokens du prompt système
            - messages_tokens: Tokens des messages
            - total_tokens: Total
            - available_tokens: Tokens disponibles pour la réponse
        """
        prompt_tokens = cls.estimate_tokens(system_prompt)
        messages_tokens = cls.estimate_messages_tokens(messages)
        total_tokens = prompt_tokens + messages_tokens
        available_tokens = model_context - total_tokens - reserved_tokens

        can_send = available_tokens > 0

        return can_send, {
            "prompt_tokens": prompt_tokens,
            "messages_tokens": messages_tokens,
            "total_tokens": total_tokens,
            "available_tokens": available_tokens,
            "model_context": model_context,
            "reserved_tokens": reserved_tokens,
        }

    @classmethod
    def get_compaction_threshold(
        cls, model_context: int, reserved_tokens: int = 1000, safety_margin: float = 0.2
    ) -> int:
        """Calcule le seuil de tokens pour déclencher une compactation.

        Args:
            model_context: Taille du contexte du modèle.
            reserved_tokens: Tokens réservés.
            safety_margin: Marge de sécurité (0.0 à 1.0).

        Returns:
            Seuil de tokens (si les messages dépassent ce seuil, compacter).
        """
        usable_context = model_context - reserved_tokens
        return int(usable_context * (1.0 - safety_margin))

    @classmethod
    def format_token_stats(cls, stats: dict[str, int]) -> str:
        """Format les statistiques de tokens pour l'affichage.

        Args:
            stats: Dictionnaire de statistiques.

        Returns:
            Chaîne formatée.
        """
        lines = [
            f"Prompt tokens: {stats.get('prompt_tokens', 0)}",
            f"Messages tokens: {stats.get('messages_tokens', 0)}",
            f"Total tokens: {stats.get('total_tokens', 0)}",
            f"Available tokens: {stats.get('available_tokens', 0)}",
            f"Model context: {stats.get('model_context', 0)}",
        ]
        return "\n".join(lines)


class ContextMonitor:
    """Surveille l'utilisation du contexte pour une session.

    Cette classe permet de suivre l'utilisation des tokens au fil
    d'une conversation et de déclencher des alertes ou actions
    quand le contexte approach de la limite.
    """

    def __init__(
        self,
        model_context: int,
        reserved_tokens: int = 1000,
        warning_threshold: float = 0.8,
        critical_threshold: float = 0.95,
    ) -> None:
        """Initialise le moniteur de contexte.

        Args:
            model_context: Taille du contexte du modèle.
            reserved_tokens: Tokens réservés.
            warning_threshold: Seuil d'avertissement (0.0 à 1.0).
            critical_threshold: Seuil critique (0.0 à 1.0).
        """
        self.model_context = model_context
        self.reserved_tokens = reserved_tokens
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self._current_prompt_tokens = 0
        self._current_messages_tokens = 0
        self._history: list[dict[str, int]] = []

    def update(
        self, system_prompt: str, messages: Sequence[dict[str, Any]]
    ) -> dict[str, Any]:
        """Met à jour l'état du contexte.

        Args:
            system_prompt: Prompt système.
            messages: Liste des messages.

        Returns:
            Dictionnaire avec :
            - status: "ok", "warning", ou "critical"
            - usage_percent: Pourcentage d'utilisation
            - stats: Statistiques détaillées
        """
        self._current_prompt_tokens = TokenEstimator.estimate_tokens(system_prompt)
        self._current_messages_tokens = TokenEstimator.estimate_messages_tokens(
            messages
        )

        total_tokens = self._current_prompt_tokens + self._current_messages_tokens
        available_tokens = self.model_context - total_tokens - self.reserved_tokens
        usage_percent = total_tokens / self.model_context

        # Déterminer le statut
        if usage_percent >= self.critical_threshold:
            status = "critical"
        elif usage_percent >= self.warning_threshold:
            status = "warning"
        else:
            status = "ok"

        stats = {
            "prompt_tokens": self._current_prompt_tokens,
            "messages_tokens": self._current_messages_tokens,
            "total_tokens": total_tokens,
            "available_tokens": available_tokens,
            "usage_percent": usage_percent,
        }

        # Sauvegarder dans l'historique
        self._history.append(stats)

        # Limiter l'historique
        if len(self._history) > self.MAX_HISTORY:
            self._history = self._history[-self.MAX_HISTORY :]

        return {"status": status, "usage_percent": usage_percent, "stats": stats}

    def should_compact(self) -> bool:
        """Indique si une compactation est recommandée.

        Returns:
            True si une compactation est recommandée.
        """
        if not self._history:
            return False

        last_stats = self._history[-1]
        return last_stats["usage_percent"] >= self.warning_threshold

    def get_recommendation(self) -> str | None:
        """Retourne une recommandation basée sur l'état actuel.

        Returns:
            Recommandation ou None.
        """
        if not self._history:
            return None

        last_stats = self._history[-1]

        if last_stats["usage_percent"] >= self.critical_threshold:
            return (
                "Context usage is critical! Please use /compact to summarize "
                "the conversation or /rewind to remove recent messages."
            )

        if last_stats["usage_percent"] >= self.warning_threshold:
            return (
                "Context usage is high. Consider using /compact to summarize "
                "the conversation soon."
            )

        return None
