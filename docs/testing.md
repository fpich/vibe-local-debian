# Tests et stabilisation

## Suite maintenue

La suite stable du fork est :

```bash
uv run pytest
```

Elle est volontairement plus petite que l'ancienne suite upstream : les tests d'ACP, cloud auth, MCP/connecteurs, Rust, voice, telemetry et autres surfaces supprimées ne sont plus collectés.

En plus de `tests/local`, la suite par défaut collecte les suites legacy réintégrées car elles passent intégralement :

- `tests/backend` — adaptation OpenAI-compatible ;
- `tests/core/agent_loop` — intégrité du runtime `AgentLoop` ;
- `tests/core/autocompletion` — autocomplétion ;
- `tests/core/utils` — utilitaires cœur ;
- `tests/core/vision` — gestion des images.

Les suites legacy connues comme échouant sur POSIX (`tests/tools`, `tests/core/git`, `tests/core/paths`, `tests/core/tools`) ne sont pas dans le chemin par défaut ; elles peuvent être exécutées explicitement avec :

```bash
make test-legacy
```

Les tests maintenus couvrent principalement :

- invariants local-only ;
- allowlist des outils ;
- modèles fail-closed ;
- sécurité des scripts install/uninstall ;
- absence des sous-systèmes supprimés ;
- intégrité du runtime `AgentLoop` ;
- cohérence de release/documentation.

## Vérifications statiques

```bash
python -m compileall -q vibe
uv run ruff check vibe tests/local
uv run ruff format --check vibe tests/local
uv run pyright
```

Important : `compileall` seul ne suffit pas. Les erreurs de décorateurs exécutés à l'import (par exemple `@dataclass(slots=True)`) peuvent n'apparaître qu'au chargement réel du module.

## Smoke test runtime

Avant une release, sous Python 3.13 au minimum :

```bash
vibe --version
vibe-app-server --help
```

Puis avec un vrai serveur llama.cpp :

1. chat simple ;
2. `read_file` ;
3. `write_file` ;
4. `edit` ;
5. `grep` ;
6. `bash` ;
7. accès hors workspace sans auto-approve — doit être refusé ou demander une permission ;
8. `/compact` ;
9. fermeture/réouverture avec `--continue` ou `--resume`.

## Test de dépôt minimal

```bash
mkdir -p /tmp/vibe-smoke
cd /tmp/vibe-smoke
git init
echo "print('hello')" > app.py
vibe
```

Prompt conseillé :

```text
Lis app.py, remplace hello par hello local agent, vérifie le fichier puis explique le changement.
```

## Packaging

```bash
uv build --wheel
```

Le wheel attendu est pure Python (`py3-none-any`). Il ne doit contenir ni `harness/`, ni CLI Rust, ni ACP, ni backend Mistral supprimé.

## Checklist release

- [ ] version cohérente dans `pyproject.toml`, `vibe/__init__.py` et `uv.lock` ;
- [ ] `uv run pytest` vert ;
- [ ] compilation Python verte ;
- [ ] lint/type-check vérifiés ;
- [ ] wheel construit ;
- [ ] installation locale `uv tool install --force .` ;
- [ ] smoke test llama.cpp ;
- [ ] README/CHANGELOG mis à jour ;
- [ ] aucune config utilisateur écrasée par l'installateur.
