# Contribute à vibe-local-debian

Ce dépôt est un hard fork local-only de Mistral Vibe. La priorité est la stabilité d'un agent de code Python/Textual utilisant des backends `llama.cpp`, pas la parité fonctionnelle avec l'amont.

## Principes

Toute contribution doit préserver ces invariants :

- aucun backend cloud par défaut ;
- aucun appel de télémétrie ou update-check distant ;
- pas de réintroduction de MCP/connecteurs, ACP, Teleport, voice ou runtime Rust sans décision d'architecture explicite ;
- sélection des modèles fail-closed ;
- allowlist d'outils locale et permissions workspace conservées ;
- Python 3.12/3.13 ;
- installation Debian 13 via `uv`.

Le nom de distribution Python reste `mistral-vibe` pour compatibilité avec les installations `uv tool` existent.

## Installation de développement

```bash
git clone https://github.com/fpich/vibe-local-debian.git
cd vibe-local-debian
uv sync --group dev
```

Exécution depuis le dépôt :

```bash
uv run vibe
```

## Tests

La suite stable par défaut est volontairement centrée sur le fork :

```bash
uv run pytest
```

Elle vérifie notamment :

- l'allowlist des outils ;
- la sélection locale des modèles ;
- les protections `install.sh` / `uninstall.sh` ;
- l'absence des sous-systèmes supprimés ;
- l'intégrité structurelle d'`AgentLoop` et du runtime legacy ;
- l'absence de symbols globaux manquants et de doubles décorateurs ;
- la cohérence de version et de documentation.

Avant une release, suivre aussi [docs/testing.md](docs/testing.md).

## Qualité

```bash
uv run ruff check vibe tests
uv run ruff format --check vibe tests
uv run pyright
python -m compileall -q vibe
uv build --wheel
```

Pour appliquer le formatage :

```bash
uv run ruff check --fix vibe tests
uv run ruff format vibe tests
```

## Validation avec llama.cpp

Avant une release, tester au moins un vrai serveur OpenAI-compatible :

```bash
curl -s http://127.0.0.1:8080/v1/models
```

Puis, dans un dépôt temporaire, vérifier : démarrage TUI, chat simple, `read_file`, `write_file`, `edit`, `grep`, `bash`, refus/approbation d'un accès hors workspace, `/resume` et `/compact`.

## Architecture

Lire [docs/architecture.md](docs/architecture.md) avant de modifier les frontières du runtime. Les ADR hérités de l'amont sont conservés sous `docs/archive/upstream/` uniquement comme historique ; ils ne sont pas normatifs pour les fonctionnalités supprimées.

## Documentation

Une modification fonctionnelle doit mettre à jour au minimum :

- `README.md` si elle change l'usage ;
- `docs/configuration.md` si elle change la configuration ;
- `CHANGELOG.md` si elle est destinée à une release ;
- `AGENTS.md` si elle change une règle permanente de contribution.
