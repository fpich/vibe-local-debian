# Changelog

Historique du fork `vibe-local-debian`. Les versions amont de Mistral Vibe ne sont plus recopiées ici afin d'éviter de présenter des functions supprimées comme faisant partie du produit.

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
