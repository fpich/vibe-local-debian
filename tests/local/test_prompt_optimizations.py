"""Tests pour les optimisations des prompts système.

Ce module contient des tests unitaires pour vérifier le bon fonctionnement
des optimisations de cache, compression et sélection des prompts.
"""
from __future__ import annotations

from vibe.core.prompts.cache import PromptCache
from vibe.core.prompts.dependencies import DynamicPromptDependencies
from vibe.core.prompts.selector import PromptSelector, TaskType
from vibe.core.prompts.token_estimator import ContextMonitor, TokenEstimator


class TestPromptCache:
    """Tests pour le cache des prompts."""

    def test_basic_cache_operation(self):
        """Test les opérations de base du cache."""
        cache = PromptCache(compress=False)

        # Premier appel : doit envoyer
        prompt, should_send = cache.get_prompt("cli", "worker1")
        assert should_send is True
        assert len(prompt) > 0
        assert "Vibe Local" in prompt or "coding assistant" in prompt

        # Deuxième appel : ne doit pas envoyer
        prompt2, should_send2 = cache.get_prompt("cli", "worker1")
        assert should_send2 is False
        assert prompt == prompt2

    def test_compression_enabled(self):
        """Test la compression des prompts."""
        cache = PromptCache(compress=True)

        # Charger un prompt
        prompt, _ = cache.get_prompt("cli", "worker1")

        # Vérifier que la compression a réduit la taille
        # (on ne peut pas vérifier exactement car on ne connaît pas la taille originale)
        assert len(prompt) > 0

    def test_compress_prompt_method(self):
        """Test la méthode de compression directement."""
        cache = PromptCache(compress=True)

        original = "Hello   ,   world !  \n\n\n  Test"
        compressed = cache._compress_prompt(original)

        # Doit être plus court
        assert len(compressed) < len(original)
        # Doit conserver le sens
        assert "Hello, world!" in compressed
        assert "Test" in compressed

    def test_dynamic_prompt_cache(self):
        """Test le cache des prompts dynamiques."""
        cache = PromptCache(compress=False)

        deps_hash = "test_hash_123"
        model_name = "test_model"

        # Premier appel : doit générer et envoyer
        prompt_builder_called = False

        def build_prompt():
            nonlocal prompt_builder_called
            prompt_builder_called = True
            return "Dynamic prompt content"

        prompt, should_send = cache.get_or_store_dynamic_prompt(
            prompt_id="",
            model_name=model_name,
            dependencies_hash=deps_hash,
            prompt_builder=build_prompt,
        )

        assert prompt_builder_called is True
        assert should_send is True
        assert prompt == "Dynamic prompt content"

        # Deuxième appel avec même hash : ne doit pas régénérer
        prompt_builder_called = False
        prompt2, should_send2 = cache.get_or_store_dynamic_prompt(
            prompt_id="",
            model_name=model_name,
            dependencies_hash=deps_hash,
            prompt_builder=build_prompt,
        )

        assert prompt_builder_called is False
        assert should_send2 is False
        assert prompt2 == "Dynamic prompt content"

    def test_different_dependencies_hash(self):
        """Test avec des hash de dépendances différents."""
        cache = PromptCache(compress=False)

        model_name = "test_model"

        # Premier prompt
        prompt1, _ = cache.get_or_store_dynamic_prompt(
            prompt_id="",
            model_name=model_name,
            dependencies_hash="hash_1",
            prompt_builder=lambda: "Prompt 1",
        )

        # Deuxième prompt avec hash différent
        prompt2, _ = cache.get_or_store_dynamic_prompt(
            prompt_id="",
            model_name=model_name,
            dependencies_hash="hash_2",
            prompt_builder=lambda: "Prompt 2",
        )

        assert prompt1 == "Prompt 1"
        assert prompt2 == "Prompt 2"

    def test_store_dynamic_prompt(self):
        """Test le stockage direct d'un prompt dynamique."""
        cache = PromptCache(compress=False)

        prompt, should_send = cache.store_dynamic_prompt(
            prompt="Test prompt",
            model_name="model1",
            dependencies_hash="hash1",
        )

        assert prompt == "Test prompt"
        assert should_send is True

        # Même prompt, même hash : ne doit pas envoyer
        prompt2, should_send2 = cache.store_dynamic_prompt(
            prompt="Test prompt",
            model_name="model1",
            dependencies_hash="hash1",
        )

        assert should_send2 is False

    def test_stats(self):
        """Test les statistiques du cache."""
        cache = PromptCache(compress=False)

        # Premier appel : miss
        cache.get_prompt("cli", "worker1")

        # Deuxième appel : hit
        cache.get_prompt("cli", "worker1")

        stats = cache.get_stats()

        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["cached_prompts"] >= 1

    def test_reset_session(self):
        """Test la réinitialisation de session."""
        cache = PromptCache(compress=False)

        # Premier appel
        cache.get_prompt("cli", "worker1")

        # Réinitialiser
        cache.reset_session("worker1")

        # Prochain appel doit envoyer à nouveau
        _, should_send = cache.get_prompt("cli", "worker1")
        assert should_send is True

    def test_clear(self):
        """Test l'effacement complet du cache."""
        cache = PromptCache(compress=False)

        cache.get_prompt("cli", "worker1")
        cache.get_prompt("lean", "worker2")

        cache.clear()

        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["cached_prompts"] == 0


class TestDynamicPromptDependencies:
    """Tests pour les dépendances des prompts dynamiques."""

    def test_compute_hash(self):
        """Test le calcul du hash des dépendances."""
        hash1 = DynamicPromptDependencies.compute_hash(
            config_system_prompt="prompt1",
            include_commit_signature=True,
            include_model_info=True,
            include_prompt_detail=True,
            include_project_context=True,
            skills_sorted_names=["skill1", "skill2"],
            agents_sorted_names=["agent1"],
            tools_sorted_names=["tool1", "tool2"],
            headless=False,
            model_name="model1",
            cwd="/path/to/cwd",
            scratchpad_dir="/path/to/scratchpad",
        )

        # Doit retourner un hash de 16 caractères
        assert len(hash1) == 16
        assert isinstance(hash1, str)

        # Même entrée doit donner même hash
        hash2 = DynamicPromptDependencies.compute_hash(
            config_system_prompt="prompt1",
            include_commit_signature=True,
            include_model_info=True,
            include_prompt_detail=True,
            include_project_context=True,
            skills_sorted_names=["skill1", "skill2"],
            agents_sorted_names=["agent1"],
            tools_sorted_names=["tool1", "tool2"],
            headless=False,
            model_name="model1",
            cwd="/path/to/cwd",
            scratchpad_dir="/path/to/scratchpad",
        )

        assert hash1 == hash2

        # Entrée différente doit donner hash différent
        hash3 = DynamicPromptDependencies.compute_hash(
            config_system_prompt="prompt2",
            include_commit_signature=True,
            include_model_info=True,
            include_prompt_detail=True,
            include_project_context=True,
            skills_sorted_names=["skill1", "skill2"],
            agents_sorted_names=["agent1"],
            tools_sorted_names=["tool1", "tool2"],
            headless=False,
            model_name="model1",
            cwd="/path/to/cwd",
            scratchpad_dir="/path/to/scratchpad",
        )

        assert hash1 != hash3


class TestPromptSelector:
    """Tests pour la sélection des prompts."""

    def test_default_selection(self):
        """Test la sélection par défaut."""
        selector = PromptSelector()

        # Sans paramètres : doit retourner "cli"
        assert selector.select() == "cli"

    def test_coding_selection(self):
        """Test la sélection pour le coding."""
        selector = PromptSelector()

        assert selector.select(task_type=TaskType.CODING) == "lean"

    def test_exploration_selection(self):
        """Test la sélection pour l'exploration."""
        selector = PromptSelector()

        assert selector.select(task_type=TaskType.EXPLORATION) == "explore"

    def test_small_context_force_minimal(self):
        """Test le forçage du prompt minimal pour les petits contextes."""
        selector = PromptSelector()

        # Contexte très petit : doit forcer minimal
        assert selector.select(
            task_type=TaskType.DEFAULT,
            model_context=1024,
        ) == "minimal"

    def test_medium_context_force_lean(self):
        """Test le forçage du prompt lean pour les contextes moyens."""
        selector = PromptSelector()

        # Contexte moyen : doit forcer lean
        assert selector.select(
            task_type=TaskType.DEFAULT,
            model_context=4096,
        ) == "lean"

    def test_headless_mode(self):
        """Test le mode headless."""
        selector = PromptSelector()

        # Mode headless : doit retourner lean
        assert selector.select(
            task_type=TaskType.DEFAULT,
            is_headless=True,
        ) == "lean"

    def test_user_preference_override(self):
        """Test la priorité de la préférence utilisateur."""
        selector = PromptSelector()

        assert selector.select(
            task_type=TaskType.DEFAULT,
            user_preference="minimal",
        ) == "minimal"

    def test_string_task_type(self):
        """Test avec un type de tâche en string."""
        selector = PromptSelector()

        assert selector.select(task_type="coding") == "lean"
        assert selector.select(task_type="CODING") == "lean"

    def test_with_fallback(self):
        """Test avec fallback."""
        selector = PromptSelector()

        # Prompt non disponible : doit fallback vers cli
        assert selector.select_with_fallback(
            task_type=TaskType.DEFAULT,
            available_prompts=["lean", "minimal"],
        ) == "lean"  # cli n'est pas disponible, donc lean (premier dans le mapping)

    def test_get_prompt_context_requirements(self):
        """Test les exigences de contexte."""
        reqs = PromptSelector.get_prompt_context_requirements("cli")

        assert "min_context" in reqs
        assert "recommended_context" in reqs
        assert reqs["min_context"] == 8192

    def test_detect_task_type_coding(self):
        """Test la détection du type de tâche pour le coding."""
        assert PromptSelector.detect_task_type("write a function") == TaskType.CODING
        assert PromptSelector.detect_task_type("implement") == TaskType.CODING

    def test_detect_task_type_testing(self):
        """Test la détection du type de tâche pour les tests."""
        assert PromptSelector.detect_task_type("write a test") == TaskType.TESTING
        assert PromptSelector.detect_task_type("unit test") == TaskType.TESTING

    def test_detect_task_type_analysis(self):
        """Test la détection du type de tâche pour l'analyse."""
        assert PromptSelector.detect_task_type("analyze") == TaskType.ANALYSIS
        assert PromptSelector.detect_task_type("performance") == TaskType.ANALYSIS

    def test_detect_task_type_debugging(self):
        """Test la détection du type de tâche pour le debugging."""
        assert PromptSelector.detect_task_type("debug") == TaskType.DEBUGGING
        assert PromptSelector.detect_task_type("error") == TaskType.DEBUGGING

    def test_detect_task_type_default(self):
        """Test la détection par défaut."""
        assert PromptSelector.detect_task_type("hello") == TaskType.DEFAULT


class TestTokenEstimator:
    """Tests pour l'estimation des tokens."""

    def test_estimate_tokens_empty(self):
        """Test l'estimation avec un texte vide."""
        assert TokenEstimator.estimate_tokens("") == 0

    def test_estimate_tokens_text(self):
        """Test l'estimation avec du texte normal."""
        text = "Hello, world! This is a test."
        tokens = TokenEstimator.estimate_tokens(text)

        # "Hello, world! This is a test." = 28 caractères
        # Ratio texte : ~4 caractères = 1 token
        # Donc ~7 tokens
        assert tokens > 0
        assert tokens < 10

    def test_estimate_tokens_code(self):
        """Test l'estimation avec du code."""
        code = "def hello():\n    return 'world'"
        tokens = TokenEstimator.estimate_tokens(code)

        # Code est plus dense : ~3 caractères = 1 token
        # 25 caractères / 3 = ~8 tokens
        assert tokens > 0

    def test_estimate_message_tokens(self):
        """Test l'estimation avec un message."""
        message = {
            "role": "user",
            "content": "Hello, world!",
        }

        tokens = TokenEstimator.estimate_message_tokens(message)
        assert tokens > 0

    def test_estimate_messages_tokens(self):
        """Test l'estimation avec plusieurs messages."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        tokens = TokenEstimator.estimate_messages_tokens(messages)
        assert tokens > 0

    def test_can_send_request(self):
        """Test la vérification de l'envoi."""
        system_prompt = "You are a helpful assistant."
        messages = [{"role": "user", "content": "Hello"}]

        # Contexte suffisamment grand
        can_send, stats = TokenEstimator.can_send_request(
            system_prompt=system_prompt,
            messages=messages,
            model_context=10000,
            reserved_tokens=1000,
        )

        assert can_send is True
        assert stats["prompt_tokens"] > 0
        assert stats["messages_tokens"] > 0
        assert stats["total_tokens"] > 0
        assert stats["available_tokens"] > 0

    def test_cannot_send_request(self):
        """Test quand l'envoi n'est pas possible."""
        system_prompt = "You are a helpful assistant. " * 1000
        messages = [{"role": "user", "content": "Hello" * 1000}]

        # Contexte trop petit
        can_send, stats = TokenEstimator.can_send_request(
            system_prompt=system_prompt,
            messages=messages,
            model_context=100,
            reserved_tokens=1000,
        )

        assert can_send is False
        assert stats["available_tokens"] < 0

    def test_get_compaction_threshold(self):
        """Test le calcul du seuil de compactation."""
        threshold = TokenEstimator.get_compaction_threshold(
            model_context=10000,
            reserved_tokens=1000,
            safety_margin=0.2,
        )

        # (10000 - 1000) * 0.8 = 7200
        assert threshold == 7200


class TestContextMonitor:
    """Tests pour le moniteur de contexte."""

    def test_initial_state(self):
        """Test l'état initial."""
        monitor = ContextMonitor(
            model_context=10000,
            reserved_tokens=1000,
        )

        # Aucun message initialement
        result = monitor.update("", [])

        assert result["status"] == "ok"
        assert result["usage_percent"] == 0.0

    def test_with_messages(self):
        """Test avec des messages."""
        monitor = ContextMonitor(
            model_context=10000,
            reserved_tokens=1000,
        )

        messages = [
            {"role": "user", "content": "Hello" * 100},
        ]

        result = monitor.update("System prompt", messages)

        assert result["status"] == "ok"
        assert result["usage_percent"] > 0

    def test_warning_threshold(self):
        """Test le seuil d'avertissement."""
        monitor = ContextMonitor(
            model_context=1000,
            reserved_tokens=100,
            warning_threshold=0.5,
            critical_threshold=0.9,
        )

        # Utiliser 60% du contexte
        system_prompt = "A" * 500
        messages = [{"role": "user", "content": "B" * 50}]

        result = monitor.update(system_prompt, messages)

        # 550 caractères / 1000 = 55% > 50% (warning)
        assert result["status"] == "warning"

    def test_critical_threshold(self):
        """Test le seuil critique."""
        monitor = ContextMonitor(
            model_context=1000,
            reserved_tokens=100,
            warning_threshold=0.5,
            critical_threshold=0.8,
        )

        # Utiliser 90% du contexte
        system_prompt = "A" * 800
        messages = [{"role": "user", "content": "B" * 100}]

        result = monitor.update(system_prompt, messages)

        # 900 caractères / 1000 = 90% > 80% (critical)
        assert result["status"] == "critical"

    def test_should_compact(self):
        """Test la recommandation de compactation."""
        monitor = ContextMonitor(
            model_context=1000,
            reserved_tokens=100,
            warning_threshold=0.5,
        )

        # Utiliser 60% du contexte
        system_prompt = "A" * 500
        messages = [{"role": "user", "content": "B" * 100}]

        monitor.update(system_prompt, messages)

        assert monitor.should_compact() is True

    def test_get_recommendation(self):
        """Test les recommandations."""
        monitor = ContextMonitor(
            model_context=1000,
            reserved_tokens=100,
            warning_threshold=0.5,
            critical_threshold=0.8,
        )

        # Utiliser 90% du contexte
        system_prompt = "A" * 800
        messages = [{"role": "user", "content": "B" * 100}]

        monitor.update(system_prompt, messages)

        recommendation = monitor.get_recommendation()

        assert recommendation is not None
        assert "critical" in recommendation.lower() or "compact" in recommendation.lower()


class TestGlobalPromptCache:
    """Tests pour l'instance globale du cache."""

    def test_global_cache_instance(self):
        """Test l'instance globale du cache."""
        from vibe.core.prompts import prompt_cache

        assert isinstance(prompt_cache, PromptCache)
        assert prompt_cache.compress is True

    def test_global_cache_operations(self):
        """Test les opérations sur le cache global."""
        from vibe.core.prompts import prompt_cache

        # Réinitialiser pour le test
        prompt_cache.clear()

        # Premier appel
        prompt, should_send = prompt_cache.get_prompt("cli", "test_model")
        assert should_send is True

        # Deuxième appel
        prompt2, should_send2 = prompt_cache.get_prompt("cli", "test_model")
        assert should_send2 is False

        # Vérifier les stats
        stats = prompt_cache.get_stats()
        assert stats["misses"] >= 1
        assert stats["hits"] >= 1
