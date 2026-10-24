# Changelog

Historique du fork `vibe-local-debian`. Les versions amont de Mistral Vibe ne sont plus recopiées ici afin d'éviter de présenter des functions supprimées comme faisant partie du produit.

## [2.0.0] - 2026-10-24 (WIP)

### Added

- **Performance** :
  - Cache des résultats des outils (`read_file`, `grep`, etc.) via `ToolResultCache` pour éviter les exécutions redondantes.
  - Exécution asynchrone de `bash` et `grep` pour ne pas bloquer le streaming des réponses.
  - Parallélisation des appels d'outils indépendants (configurable via `max_concurrent_tools`).
  - Utilisation de `ripgrep` (si disponible) pour des recherches plus rapides.

- **TUI** :
  - Rendu incrémental des messages (`StreamingMessage`) pour une interface plus réactive.
  - Virtualisation des messages (`VirtualizedChatHistory`) pour optimiser l'affichage des grands historiques.
  - Cache des rendus (`CachedMessageRenderer`) pour éviter de recalculer la mise en forme.

- **Configuration** :
  - Système de profils prédéfinis (`--profile coding`, `--profile minimal`, etc.).
  - Chargement hiérarchique de la configuration (base + profil + overrides locaux).
  - Feature flags dans `experimental` pour activer/désactiver les nouvelles fonctionnalités.

- **Tests** :
  - Tests par tags (`@pytest.mark.performance`, `@pytest.mark.smoke`, etc.).
  - Fixtures partagées dans `tests/conftest.py`.
  - Tests de fumée pour valider le démarrage et les fonctionnalités de base.

- **Simplification** :
  - Suppression du code mort identifié via `vulture`.
  - Fusion des modules redondants (ex: `vibe/app_server/_model.py` → `vibe/core/llm/`).

### Changed

- Optimisation globale des performances des outils et de l'interface.
- Réorganisation du code pour une meilleure maintenabilité.

### Removed

- Code mort identifié par `vulture` (modules Windows, etc.).

## [1.2.9] - 2026-10-16

### Changed

- Template `.vibe/config.toml` : worker1 (Qwen3-Coder local) ajusté au déploiement réel — contexte serveur **98304** et `auto_compact_threshold` **75000** (~76 %) au lieu de 262144/200000 : sur CPU (i7-9700 + RTX 2060), la génération s'effondre au-delà de ~60-80k de contexte, la compaction précoce maintient la session dans la zone rapide. Le commentaire du bloc documente les flags serveur éprouvés (`--fit-target 2`, `-b 4096 -ub 1024` — un fit/batch plus large fait un OOM CUDA du workspace cuBLAS à la première inférence —, KV q4_0, template froggeric).

### Added

- `docs/configuration.md` : nouvelle section « Tuning serveur llama.cpp (retours d'expérience) » — OOM cuBLAS et crash-loop systemd, plancher de contexte REA (~60k incompressible), latence à contexte long et rôle du cache LCP, threads, KV q4_0, alias serveur/vibe, template function calling Qwen.

## [1.2.8] - 2026-10-16

### Changed

- Template `.vibe/config.toml` : **worker1 passe de KAT-Coder-V2.5-Dev-APEX à Qwen3-Coder-30B-A3B-Instruct** (poids officiels Qwen, quant Q4_K_M, contexte 262144, compaction 200k inchangée). `temperature` 0.3 → **0.7** (reco officielle Qwen3-Coder agentic coding : temp 0.7, top_p 0.8, top_k 20, repetition_penalty 1.05) et `thinking` high → **off** (le modèle est non-thinking uniquement). Le commentaire du bloc documente la commande llama-server, y compris `--chat-template-file` avec le template corrigé `froggeric/Qwen-Fixed-Chat-Templates` (v22.5+) — validé par test function calling direct : `tool_calls` propres avec arguments JSON valides, `reasoning_content` correctement séparé.
- `install.sh` : refuse désormais de copier un template `.vibe/config.toml` modifié localement dans le clone — vérification d'identité avec `git HEAD`, avertissement avec la commande de restoration, copie annulée plutôt qu'installer des défauts modifiés silencieusement.
- README et `docs/configuration.md` : tableaux de référence (modèles, sampling, fenêtres) mis à jour pour le nouveau worker1.

## [1.2.7] - 2026-10-16

### Added

- `docs/configuration.md` : deux nouvelles sections de référence — « Paramètres optimaux par modèle » (température par modèle sourcée des recommandations éditeurs : Qwen3-Coder 0.7, Ministral 0.1, Mistral Small 0.15, GPT-OSS 1.0 + reasoning effort, DeepSeek V4-Flash 1.0/top_p 0.95 agentic, Gemma 4 1.0/top_p 0.95/top_k 64, KAT Coder 0.3 communautaire) et « Fenêtres de contexte et compaction par modèle » (fenêtre servie par modèle, seuil `auto_compact_threshold` à ~75 %, DeepSeek V4-Flash natif 1M vs 131k servi par Albert, note de fit du sous-ensemble REA).
- Template `.vibe/config.toml` : chaque bloc `[[models]]` Albert porte un commentaire inline citant sa source de température ; le rappel que seule `temperature` est envoyée par le client (top_p/top_k restent les défauts de l'endpoint).

### Changed

- `albert-coder` (Qwen3-Coder-30B) : `temperature` 0.15 → **0.7** — correction alignée sur la recommandation officielle Qwen pour l'agentic coding (temp 0.7, top_p 0.8, top_k 20) ; la valeur précédente était inadaptée à ce modèle.

## [1.2.6] - 2026-10-16

### Added

- Template `.vibe/config.toml` : le défaut embarque désormais, en plus des deux workers llama.cpp locaux, un provider **API Albert** (endpoint OpenAI-compatible de l'État, accès enseignant) et six modèles de chat : `albert-coder` (Qwen3 Coder 30B), `albert-small` (Mistral Small 3.2), `albert-large` (GPT-OSS 120B), `albert-deepseek` (exp.), `albert-gemma` (exp.) et `albert-ministral`. L'allowlist couvre chaque modèle déclaré (globs sur les `name`, pas les alias).
- `install.sh` crée `~/.vibe/.env` (mode 600) lors de la première installation et indique comment y placer `ALBERT_API_KEY`.
- Template `.vibe/config.toml` : `enabled_tools` expose un sous-ensemble explicite de 22 outils REA (~42k tokens de définitions) au lieu du glob `mcp_rea_*` — le catalogue complet (170 outils, ~529k tokens) dépassait même un contexte 262k et provoquait des 400 `exceed_context_size_error` sur llama.cpp. L'invariant de profil (`test_block1_hardening`) épingle la liste.
- Template : worker2 devient Ministral-3-3B-Instruct-2512 (Q6_K_L, contexte 262144, compaction 200k, température 0.1) ; worker1 documenté avec sa commande llama-server réelle (262k, temp 0.6).
- Documentation : section « Provider externe compatible OpenAI » dans `docs/configuration.md` avec `~/.vibe/.env` comme méthode recommandée pour les clés (chargé automatiquement au démarrage, priorité à une variable déjà exportée, support des FIFO type coffre 1Password) ; README et en-tête du template mis à jour.

### Changed

- Invariant de release (`test_default_config_uses_only_generic_local_providers`) : continue d'interdire toute clé API en dur ; autorise le provider Albert via la variable d'environnement `ALBERT_API_KEY` et vérifie que l'allowlist couvre tous les modèles déclarés.

## [1.2.5] - 2026-10-15

### Added

- Support des serveurs MCP **stdio locaux** (ADR 0002, `docs/adr/0002-local-stdio-mcp.md`) : nouveau module `vibe/core/mcp/` (client JSON-RPC newline-delimited sur stdin/stdout du sous-processus, sans le SDK `mcp` upstream ni aucune dépendance réseau), pool de clients, exposition des outils du serveur sous la forme `mcp_<serveur>_<outil>` via le tool manager et la politique de permissions existante.
- Champ `mcp_servers` dans `VibeConfigSchema` (union-merge par nom) : transport `stdio` uniquement, les transports HTTP (`http`, `streamable-http`) sont rejetés à la validation de la configuration (fail-closed).
- Options de session app-server `mcp_servers` stdio relayées dans les overrides de config ; projection `/mcp` (`project_mcp`) alimentée depuis le pool.
- `scripts/install_ghidra_rea.sh` : installateur idempotent de la chaîne REA (JDK 21 via apt, Ghidra 12.1.4 épinglé depuis la release GitHub officielle, radare2 6.2.4 épinglé — absent des dépôts trixie —, Node.js si absent, `rea-agents@6.4.0` npm épinglé), avec mode `--doctor` qui ne judge que la santé du provider Ghidra (les avis informatifs du doctor REA ne font pas échouer).
- Template `.vibe/config.toml` : bloc `[[mcp_servers]]` REA documenté en commentaire et glob `mcp_rea_*` ajouté à l'allowlist `enabled_tools`.
- Tests `tests/local/test_local_stdio_mcp.py` : handshake réel avec un serveur MCP stdio Python en loopback, erreurs par serveur, `disabled_tools`, normalisation des noms d'outils, rejet des transports HTTP.
- Documentation : section « Serveurs MCP stdio locaux » dans `README.md` et `docs/configuration.md` ; mise à jour de `AGENTS.md`, `CONTRIBUTING.md` et `docs/architecture.md` pour la nouvelle frontière (stdio local supporté, distant toujours interdit).

### Fixed

- Client MCP stdio : l'environnement du serveur (`env` du schéma) est fusionné par-dessus `os.environ` au lieu de le remplacer — les serveurs basés sur `npx` mouraient au spawn sans `PATH`/`HOME`.
- Client MCP stdio : lecture des réponses JSON-RPC par chunks bornés — `tools/list` d'un serveur riche (REA : 170 outils, réponse > 64 KiB) faisait lever `Separator is not found, and chunk exceed the limit` au `readline()` d'asyncio, tué le lecteur et surfacé en erreur trompeuse « closed the connection ». Vérifié contre le serveur réel `rea-agents@6.4.0` (170 outils enregistrés).

## [1.2.4] - 2026-10-06

### Security

- Durcissement de l'environnement passé aux sous-processus shell (`vibe/core/utils/shell.py`) : les variables `ENV`, `BASH_ENV`, `PS1`, `PROMPT_COMMAND` et `ZDOTDIR` sont retirées de l'environnement du bash tool — elles permettent l'exécution de code arbitraire au démarrage d'un shell non interactif sans passer par la policy shell.
- Les hooks exécutent désormais leurs commandes avec le même environnement durci que le bash tool (`start_new_session=True` + env nettoyé) au lieu d'hériter de tout l'environnement de la TUI.
- `HookConfig.timeout` est borné : un hook ne peut plus déclarer un timeout supérieur à 600 s (défaut 60 s inchangé).
- `install.sh` : `~/.vibe` créé en mode 0700 et `config.toml` copié en mode 0600, au lieu de suivre l'umask.

### Removed
- Élagage de la surface Windows (portée Debian-only) : suppression des modules `vibe/core/tools/builtins/windows_shell.py`, `git_bash.py`, `managed_shell/_windows.py`, `vibe/core/utils/windows_asyncio.py` et de leurs tests dédiés. Le bash tool et le shell managé sont désormais POSIX-only ; les gardes `is_windows()` résiduels (locks de session, permissions de `~/.vibe`, détection de thème, paste de chemins) sont retirés du runtime.

### Changed
- CI : nouvelle étape « Run pre-commit hooks on all files » après la synchronisation des dépendances ; les hooks pre-commit excluent explicitement les suites de tests dormantes (pyright, ruff-check, ruff-format).
- `docs/testing.md` : nouvelle section « Suites dormantes (dette connue) » cartographiant les suites non collectables et leur cause racine ; description du parcours CI et des vérifications statiques mise à jour.

### Added
- Couverture de la suite maintenue : `coverage[toml]` ajoutée aux dépendances de dev, configuration `[tool.coverage]` dans `pyproject.toml`, cible `make test-coverage`. Measure de référence : ~35 % global.

## [1.2.3] - 2026-10-06

### Security
- Suppression de `scripts/install.sh` (obsolète : référençait le package public `mistral-vibe` et un mode ACP supprimé). L'installateur de référence reste `./install.sh`, qui installe explicitement le checkout local.
- Épinglage des trois GitHub Actions de la CI (`checkout`, `setup-uv`, `setup-python`) par SHA complet, conformément à la règle supply-chain du dépôt.
- `SECURITY.md` : nouvelle section « Confiance du workspace et code exécutable » documentant que marquer un dépôt fiable rend actifs les outils `.vibe/tools/*.py` importés dynamiquement.

### Changed
- `requires-python` borné à `>=3.12,<3.14` pour refléter le support documenté 3.12/3.13 ; `uv.lock` rafraîchi (branches de résolution ≥3.14 supprimées).
- README : branche stable référencée mise à jour 1.2.1 → 1.2.2.

### Added
- Réintégration des quatre suites de tests legacy sur POSIX : `tests/tools`, `tests/core/git`, `tests/core/paths`, `tests/core/tools` (2 265 tests verts). La CI les exécute à chaque push.
- Helpers de tests partagés restaurés dans `tests/conftest.py` (adaptés au fork : plus de gateways account/identity, plus de connector catalog).

## [1.2.2] - 2026-10-06

### Changed

- Formatage global du code avec `ruff format` (aucun changement de comportement).
- Documentation mise à jour pour refléter la nouvelle convention de nommage des modèles (`worker1`/`worker2`, `allowed_models = ["worker*"]`) et les suites de tests réintégrées.

### Added

- Index unique des surfaces supprimées dans `docs/archive/README.md`.
- Tests de régression sur le template de configuration livré et sur la sécurité réseau de l'outil bash.
- Suite de tests par défaut élargie : `tests/backend`, `tests/core/agent_loop`, `tests/core/autocompletion`, `tests/core/utils`, `tests/core/vision`, `tests/e2e` ; cible `make test-legacy` pour les suites legacy connues comme échouant sur POSIX.
- CI : vérification explicite du typage (`pyright vibe`) et du formatage (`ruff format --check`) à chaque push ; `make check` aligné (cibles `typecheck` et `format-check`).
- Tests e2e réhabilités : `pexpect` ajouté aux dépendances dev, test d'onboarding adapté au produit local-only (démarrage direct de la TUI sans écran cloud).

### Performance

- Compaction automatique abaissée de 90k à 80k tokens (marge accrue avant débordement de contexte, sur les deux workers).
- `cache_prompt = true` envoyé par défaut aux serveurs OpenAI-compatibles : llama.cpp réutilise son cache de préfixe entre les tours (prompt processing bien plus rapide). Opt-out par provider via `cache_prompt = false`.

### Fixed

- Quatre erreurs de lint `undefined-name` sur les annotations `trace.Span` dans `AgentLoop` (alias de type `Span` ajouté dans `vibe.core.tracing`).
- Erreurs de typage pyright préexistantes : entrées 1-tuple dans le mapping d'import différé `vibe.core.config`, accès `connector_registry` inexistant dans l'app-server.
- Imports `opentelemetry` résiduels (télémétrie supprimée) remplacés par l'alias `Span` de `vibe.core.tracing` dans `agent_loop_hooks` et le backend générique. `pyright vibe` est désormais à 0 erreur.

## [1.2.1] - 2026-10-06

Release de stabilisation après le nettoyage 1.2.0.

### Fixed

- Correction du logger qui référençait encore le Unified Harness supprimé.
- Suppression du dernier initialiseur Teleport résiduel dans `AgentLoop`.
- Correction d'un double décorateur `@dataclass(frozen=True, slots=True)` incompatible au chargement sous Python 3.13.
- Restoration de la surface legacy nécessaire d'`AgentLoop` et des helpers d'ouverture/attachement du runtime de session supprimés accidentellement pendant l'élagage.
- Neutralisation explicite du pool MCP legacy (`_mcp_pool = None`) sans réintroduire de runtime MCP.
- Suppression d'un dernier type MCP non importé encore référencé par le serveur.
- L'installateur réinstalle désormais explicitement le dépôt local au lieu de tenter un upgrade ambigu du paquet par son nom.

### Validation

- Démarrage réel validé sous Python 3.13.
- Import du chemin critique `cli → app_server → AgentLoop` validé.
- Sweep d'import de tous les modules Python du runtime validé pendant la stabilisation.
- Cycle agentique avec faux endpoint OpenAI-compatible validé : chat simple, `read_file`, `write_file`, `edit`, `grep` et `bash`.
- Accès hors workspace sans auto-approve validé comme refusé/annulé.
- Suite de régression structurelle ajoutée pour empêcher la réapparition des suppressions accidentelles.

### Documentation

- README réécrit pour refléter le produit local-only réellement livré.
- Documentation configuration/architecture/tests ajoutée.
- Politique de sécurité adaptée au fork indépendant.
- ADRs concernant ACP, Rust, Unified Harness, narration et autres surfaces supprimées archivés comme documentation upstream non normative.
- Ancienne suite de tests upstream retirée du chemin de test par défaut ; `uv run pytest` cible la suite maintenue du fork.

## [1.2.0] - 2026-10-05

### Changed

- Passage à un runtime Python pur autour de la TUI Textual et de l'AgentLoop legacy.
- Suppression du CLI Rust, du Unified Harness Rust et du build Maturin.
- Suppression d'ACP, auth/onboarding cloud, backend Mistral, MCP/connecteurs distants, plugins distants, web search/fetch, Teleport/Vibe Code, voice/narration, Sentry/OTEL/télémétrie distante et update notifier.
- Réduction forte des dépendances runtime et passage à un wheel pure Python.
- Allowlist stricte des outils de coding locaux.
- `allowed_models` rendu fail-closed.
- Installateur `uv` durci par version et SHA-256 épinglés.
- Désinstallateur protégé contre les valeurs dangereuses de `VIBE_HOME`.

## [1.1.0] - 2026-10-04

Première version publique du fork Debian/local avec deux workers `llama.cpp`, compaction à 90k tokens et configuration sans télémétrie/update automatique.
