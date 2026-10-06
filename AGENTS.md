# AGENTS.md

Conventions pour les agents et humains qui modifient **vibe-local-debian**.

## Mission du dépôt

Maintenir un agent de code CLI local-first pour Debian 13, Python 3.12/3.13, avec une TUI Textual et des backends `llama.cpp` OpenAI-compatible. Le fork ne suit pas automatiquement Mistral Vibe upstream.

## Invariants à préserver

- L'inférence passe uniquement par les providers génériques configurés par l'utilisateur (`llama.cpp` par défaut).
- Ne pas réintroduire de backend cloud Mistral, authentication cloud, MCP/connecteurs distants, ACP, Teleport/Vibe Code, voice/narration, Sentry/OTEL/télémétrie ou update notifier sans décision explicite.
- Le profil par défaut expose seulement `bash`, `read_file`, `write_file`, `edit`, `grep`, `ask_user_question`, `todo`.
- `allowed_models` doit rester fail-closed.
- Les permissions et la frontière du workspace sont des functions de sécurité : ne pas les contourner pour simplifier un flux.
- La compaction locale par défaut est à **80k tokens** dans `.vibe/config.toml`.
- Aucun secret ou clé Mistral n'est requis.
- Un serveur LLM distant sur le LAN est supporté via `api_base` ; ne jamais coder en dur une IP privée utilisateur.

## Architecture actuelle

- `vibe/core/agent_loop/` : boucle agentique legacy Python conservée.
- `vibe/core/llm/` : abstraction LLM et backend générique OpenAI-compatible.
- `vibe/core/tools/` : outils, permissions et exécution terminal.
- `vibe/core/config/` : configuration et layering.
- `vibe/core/session/`, `checkpoints/`, `compaction/` : persistence et gestion du contexte.
- `vibe/app_server/` : frontière locale entre la TUI et l'AgentLoop.
- `vibe/cli/` : CLI et TUI Textual.
- `tests/local/` : suite de stabilisation maintenue du fork.

Voir `docs/architecture.md`.

## Commands de développement

Toujours utiliser `uv` pour l'environment du project :

```bash
uv sync --group dev
uv run pytest
uv run ruff check vibe tests
uv run ruff format --check vibe tests
uv run pyright
uv build --wheel
```

Après une modification runtime :

```bash
python -m compileall -q vibe
```

Pour une modification liée à l'inférence, valider aussi un vrai endpoint :

```bash
curl -s http://127.0.0.1:8080/v1/models
```

## Règles de stabilisation

- Préférer une modification petite et testée à une nouvelle suppression massive.
- Toute suppression de classe/méthode doit être accompagnée d'une recherche globale des références et d'un import réel du chemin de démarrage, pas seulement de `py_compile`.
- Les décorateurs (`@dataclass`, Pydantic, Textual) doivent être exercés par import réel sous Python 3.13 : certaines erreurs n'apparaissent pas à la compilation.
- Conserver les tests d'intégrité d'`AgentLoop` qui protègent la surface legacy nécessaire au runtime.
- Ne pas ajouter un fallback qui réactive une fonctionnalité distante lorsqu'une config locale est invalid.

## Documentation

Les ADR upstream archivés sous `docs/archive/upstream/` peuvent expliquer l'origine du code mais ne sont pas normatifs pour les fonctionnalités supprimées. La documentation active est : `README.md`, `docs/architecture.md`, `docs/configuration.md`, `docs/testing.md`, `SECURITY.md` et ce fichier.
