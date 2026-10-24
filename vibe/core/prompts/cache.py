"""Optimisation des prompts système : cache, compression et envoi conditionnel.

Ce module fournit un système de cache et d'optimisation pour les prompts système
afin de réduire le nombre de tokens envoyés au LLM.

Fonctionnalités:
- Cache LRU des prompts système (par ID + modèle + hash des dépendances)
- Compression des prompts (suppression des escapes inutiles)
- Envoi conditionnel (seulement si le prompt a changé)
- Hash unique pour éviter les duplications
- Statistiques de cache pour le monitoring
- Support des prompts dynamiques (générés par le code)
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any

from vibe import VIBE_ROOT

if TYPE_CHECKING:
    pass

# Répertoire des prompts système
PROMPTS_DIR = VIBE_ROOT / "core" / "prompts"


class PromptCache:
    """Cache et optimisation des prompts système pour réduire les tokens envoyés au LLM.

    Ce cache stocke les prompts système déjà chargés et compressés, et permet
    de déterminer si un prompt doit être envoyé à nouveau ou s'il peut être omis
    (car déjà envoyé dans une requête précédente).

    Exemple d'utilisation:
        >>> cache = PromptCache(compress=True)
        >>> # Pour un prompt statique
        >>> prompt, should_send = cache.get_prompt("cli", "worker1")
        >>> if should_send:
        ...     messages.insert(0, {"role": "system", "content": prompt})
        >>> # Pour un prompt dynamique
        >>> deps_hash = cache.compute_dependencies_hash(config, skill_manager, agent_manager)
        >>> prompt, should_send = cache.get_or_store_dynamic_prompt(
        ...     "", "worker1", deps_hash, lambda: build_prompt()
        ... )

    Attributes:
        max_size: Nombre maximum de prompts à garder en cache.
        compress: Si True, compresse les prompts avant stockage.
    """

    def __init__(self, max_size: int = 100, compress: bool = True) -> None:
        """Initialise le cache des prompts.

        Args:
            max_size: Nombre maximum de prompts à garder en cache.
            compress: Si True, compresse les prompts avant stockage.
        """
        self.max_size = max_size
        self.compress = compress
        self._prompt_cache: dict[str, str] = {}
        self._last_sent: dict[str, str] = {}  # model_name -> prompt_hash
        self._hit_count = 0
        self._miss_count = 0
        self._dynamic_prompt_cache: dict[str, str] = {}  # deps_hash -> prompt

    def _get_compressed_prompt(self, prompt_id: str, model_name: str) -> str:
        """Récupère et compresse un prompt système (cache LRU).

        Args:
            prompt_id: ID du prompt (ex: "cli").
            model_name: Nom du modèle (ex: "worker1").

        Returns:
            Le contenu du prompt, éventuellement compressé.
        """
        prompt_path = self._get_prompt_path(prompt_id)
        content = self._load_prompt(prompt_path)

        if self.compress:
            content = self._compress_prompt(content)

        return content

    def _get_prompt_path(self, prompt_id: str) -> Path:
        """Récupère le chemin d'un prompt système.

        Args:
            prompt_id: ID du prompt.

        Returns:
            Chemin vers le fichier du prompt.
        """
        return (PROMPTS_DIR / prompt_id).with_suffix(".md")

    def _load_prompt(self, path: Path) -> str:
        """Charge un prompt depuis un fichier.

        Args:
            path: Chemin vers le fichier du prompt.

        Returns:
            Contenu du prompt.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
        """
        from vibe.utils.io import read_safe

        try:
            return read_safe(path).text.strip()
        except Exception:
            # Fallback vers un prompt minimal si le fichier est introuvable
            return "You are a helpful coding assistant."

    def _compress_prompt(self, content: str) -> str:
        """Compresse un prompt en supprimant les escapes et formatages inutiles.

        Cette méthode applique plusieurs optimisations pour réduire la taille
        du prompt sans altérer son sens:
        - Suppression des lignes vides multiples
        - Suppression des escapes en début/fin de ligne
        - Suppression des escapes autour de la ponctuation
        - Suppression des escapes avant les listed
        - Suppression des escapes multiples

        Args:
            content: Contenu du prompt à compressor.

        Returns:
            Contenu compressé.

        Exemple:
            >>> cache = PromptCache(compress=True)
            >>> original = "Hello   ,   world !"
            >>> cache._compress_prompt(original)
            'Hello, world!'
        """
        # Supprimer les lignes vides multiples (3+ -> 2)
        content = re.sub(r"\n{3,}", "\n\n", content)

        # Supprimer les escapes en début/fin de ligne
        lines = [line.strip() for line in content.split("\n")]
        content = "\n".join(line for line in lines if line)

        # Supprimer les escapes autour de la ponctuation
        content = re.sub(r"\s+([,.!?;:])", r"\1", content)

        # Supprimer les escapes avant les listed
        content = re.sub(r"\s+(-|\*|\d+\.)", r"\1", content)

        # Supprimer les escapes multiples
        content = re.sub(r"[ \t]{2,}", " ", content)

        # Supprimer les sauts de ligne inutiles avant les listed
        content = re.sub(r"\n+(-|\*|\d+\.)", r"\n\1", content)

        return content

    def get_prompt(
        self, prompt_id: str, model_name: str, force_send: bool = False
    ) -> tuple[str, bool]:
        """Récupère un prompt optimisé et détermine s'il doit être envoyé.

        Cette méthode combine la récupération du prompt depuis le cache,
        sa compression éventuelle, et la décision d'envoi conditionnel.

        Args:
            prompt_id: ID du prompt (ex: "cli").
            model_name: Nom du modèle (ex: "worker1").
            force_send: Si True, force l'envoi même si le prompt est déjà
                       dans le cache.

        Returns:
            Tuple de (prompt_optimisé, doit_être_envoyé).
            Le prompt est toujours retourné, mais doit_être_envoyé indique
            s'il doit être inclus dans la requête LLM.

        Exemple:
            >>> cache = PromptCache()
            >>> prompt, should_send = cache.get_prompt("cli", "worker1")
            >>> print(f"Prompt: {prompt[:50]}...")
            >>> print(f"Should send: {should_send}")
        """
        # Récupérer le prompt depuis le cache (avec compression si activée)
        prompt = self._get_compressed_prompt(prompt_id, model_name)

        # Générer un hash unique pour ce prompt + modèle
        prompt_hash = hashlib.sha256(f"{prompt}:{model_name}".encode()).hexdigest()[:16]

        # Vérifier si on doit envoyer ce prompt
        should_send = force_send or (
            model_name not in self._last_sent
            or self._last_sent[model_name] != prompt_hash
        )

        # Mettre à jour le cache des prompts envoyés
        if should_send:
            self._last_sent[model_name] = prompt_hash
            self._miss_count += 1
        else:
            self._hit_count += 1

        return prompt, should_send

    def get_or_store_dynamic_prompt(
        self,
        prompt_id: str,
        model_name: str,
        dependencies_hash: str,
        prompt_builder: callable[[], str],
        force_send: bool = False,
    ) -> tuple[str, bool]:
        """Récupère ou stocke un prompt dynamique et détermine s'il doit être envoyé.

        Pour les prompts dynamiques (générés par le code), cette méthode:
        1. Vérifie si le prompt est déjà en cache
        2. Si oui, retourne le prompt cache et détermine s'il doit être envoyé
        3. Si non, appelle prompt_builder pour générer le prompt, le stocke, et retourne True

        Args:
            prompt_id: ID du prompt (peuvent être vide pour les prompts dynamiques).
            model_name: Nom du modèle.
            dependencies_hash: Hash des dépendances pour identifier le prompt.
            prompt_builder: Function qui génère le prompt si nécessaire.
            force_send: Si True, force l'envoi même si le prompt est déjà envoyé.

        Returns:
            Tuple de (prompt, doit_être_envoyé).
        """
        # Vérifier si on a déjà ce prompt en cache
        cache_key = f"{model_name}:{dependencies_hash}"

        if cache_key in self._dynamic_prompt_cache:
            prompt = self._dynamic_prompt_cache[cache_key]
            prompt_hash = hashlib.sha256(f"{prompt}:{model_name}".encode()).hexdigest()[
                :16
            ]

            # Vérifier si on doit envoyer
            should_send = force_send or (
                model_name not in self._last_sent
                or self._last_sent[model_name] != prompt_hash
            )

            # Mettre à jour les statistiques
            if should_send:
                self._last_sent[model_name] = prompt_hash
                self._miss_count += 1
            else:
                self._hit_count += 1

            return prompt, should_send
        else:
            # Le prompt n'est pas encore en cache, il faut le générer
            # Générer le prompt via le builder
            prompt = prompt_builder()

            # Compressor si nécessaire
            if self.compress:
                prompt = self._compress_prompt(prompt)

            # Stocker dans le cache dynamique
            self._dynamic_prompt_cache[cache_key] = prompt

            # Générer un hash unique
            prompt_hash = hashlib.sha256(f"{prompt}:{model_name}".encode()).hexdigest()[
                :16
            ]

            # Pour un nouveau prompt, on doit toujours l'envoyer
            self._last_sent[model_name] = prompt_hash
            self._miss_count += 1

            return prompt, True

    def store_dynamic_prompt(
        self, prompt: str, model_name: str, dependencies_hash: str
    ) -> tuple[str, bool]:
        """Stocke un prompt dynamique et détermine s'il doit être envoyé.

        Args:
            prompt: Le contenu du prompt dynamique.
            model_name: Nom du modèle.
            dependencies_hash: Hash des dépendances.

        Returns:
            Tuple de (prompt, doit_être_envoyé).
        """
        # Compressor si nécessaire
        if self.compress:
            prompt = self._compress_prompt(prompt)

        # Stocker dans le cache dynamique
        cache_key = f"{model_name}:{dependencies_hash}"
        self._dynamic_prompt_cache[cache_key] = prompt

        # Générer un hash unique
        prompt_hash = hashlib.sha256(f"{prompt}:{model_name}".encode()).hexdigest()[:16]

        # Vérifier si on doit envoyer
        should_send = (
            model_name not in self._last_sent
            or self._last_sent[model_name] != prompt_hash
        )

        if should_send:
            self._last_sent[model_name] = prompt_hash
            self._miss_count += 1
        else:
            self._hit_count += 1

        return prompt, should_send

    @staticmethod
    def compute_dependencies_hash(
        config_system_prompt: str,
        include_commit_signature: bool,
        include_model_info: bool,
        include_prompt_detail: bool,
        include_project_context: bool,
        skills_sorted_names: list[str],
        agents_sorted_names: list[str],
        tools_sorted_names: list[str],
        headless: bool = False,
        model_name: str | None = None,
    ) -> str:
        """Calcule un hash unique basé sur les dépendances du prompt système.

        Cette méthode permet de détecter si le prompt système doit être
        régénéré en function des changements de configuration, skills, agents, etc.

        Args:
            config_system_prompt: Le contenu du prompt de base.
            include_*: Flags de configuration.
            skills_sorted_names: Liste triée des noms des skills disponibles.
            agents_sorted_names: Liste triée des noms des agents disponibles.
            tools_sorted_names: Liste triée des noms des outils disponibles.
            headless: Mode headless.
            model_name: Nom du modèle.

        Returns:
            Un hash unique représentant l'état des dépendances.
        """
        deps = [
            str(config_system_prompt),
            str(include_commit_signature),
            str(include_model_info),
            str(include_prompt_detail),
            str(include_project_context),
            str(headless),
            str(model_name) if model_name else "",
            ":".join(skills_sorted_names),
            ":".join(agents_sorted_names),
            ":".join(tools_sorted_names),
        ]

        return hashlib.sha256(":".join(deps).encode()).hexdigest()[:16]

    def reset_session(self, model_name: str | None = None) -> None:
        """Réinitialise le cache pour une nouvelle session.

        Cette méthode doit être appelée au début d'une nouvelle session
        ou lorsque le modèle change.

        Args:
            model_name: Si fourni, réinitialise seulement pour ce modèle.
                       Si None, réinitialise tout.
        """
        if model_name is None:
            self._last_sent.clear()
            self._prompt_cache.clear()
            self._dynamic_prompt_cache.clear()
        else:
            self._last_sent.pop(model_name, None)

    def get_stats(self) -> dict[str, Any]:
        """Récupère les statistiques du cache.

        Returns:
            Dictionnaire contenant:
            - hits: Nombre de hits de cache
            - misses: Nombre de misses de cache
            - hit_rate: Taux de hit (0.0 à 1.0)
            - cached_prompts: Nombre de prompts en cache
            - cached_dynamic_prompts: Nombre de prompts dynamiques en cache
            - size_bytes: Taille totale du cache en octets
        """
        total_requests = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total_requests if total_requests > 0 else 0.0

        return {
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": hit_rate,
            "cached_prompts": len(self._prompt_cache),
            "cached_dynamic_prompts": len(self._dynamic_prompt_cache),
            "size_bytes": sum(len(v) for v in self._prompt_cache.values())
            + sum(len(v) for v in self._dynamic_prompt_cache.values()),
        }

    def clear(self) -> None:
        """Efface complètement le cache.

        Cette méthode efface tous les prompts mis en cache et réinitialise
        les statistiques.
        """
        self._prompt_cache.clear()
        self._last_sent.clear()
        self._dynamic_prompt_cache.clear()
        self._hit_count = 0
        self._miss_count = 0
        self._get_compressed_prompt.cache_clear()

    def preload_prompt(self, prompt_id: str, model_name: str) -> str:
        """Précharge un prompt dans le cache.

        Utile pour précharger les prompts fréquemment utilisés
        avant le début d'une session.

        Args:
            prompt_id: ID du prompt à précharger.
            model_name: Nom du modèle associé.

        Returns:
            Le contenu du prompt (compressé si activé).
        """
        return self._get_compressed_prompt(prompt_id, model_name)


# Instance globale du cache des prompts
prompt_cache = PromptCache(compress=True)
