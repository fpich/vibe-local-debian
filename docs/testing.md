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
- `tests/core/vision` — gestion des images ;
- `tests/e2e` — tests de caractérisation TUI avec mock server (pexpect, pty réels).

Les suites réintégrées (`tests/tools`, `tests/core/git`, `tests/core/paths`, `tests/core/tools`) couvrent les surfaces sensibles (shell, chemins, Git) et passent désormais sur POSIX ; elles ne sont pas dans le chemin par défaut pour garder la suite rapide, et peuvent être exécutées explicitement avec :

```bash
make test-legacy
```

La CI exécute à chaque push, dans le job `python` : les hooks pre-commit sur tous les fichiers (étape « Run pre-commit hooks on all files »), puis `uv run pytest`, puis les quatre suites réintégrées (étape « Test shell/paths/git/tools suites »).

La couverture de la suite maintenue se measure avec :

```bash
make test-coverage
```

Elle est indicative (~35 % global) : le fork n'a pas d'objectif de couverture
chiffré, mais l'écart doit rester surveillé à chaque réintégration.

Les tests maintenus couvrent principalement :

- invariants local-only ;
- allowlist des outils ;
- modèles fail-closed ;
- sécurité des scripts install/uninstall ;
- absence des sous-systèmes supprimés ;
- intégrité du runtime `AgentLoop` ;
- cohérence de release/documentation.

## Suites dormantes (dette connue)

Les suites suivantes restent présentes dans l'arborescence mais ne sont **pas
collectables** : leur import échoue car elles référencent des symbols supprimés
ou neutralisés du fork (cloud auth, MCP, ACP, voice, telemetry, snapshots TUI
de surfaces retirées). Elles ne sont volontairement ni dans `uv run pytest`, ni
dans `make test-legacy`, et sont exclues des hooks pre-commit (pyright, ruff).

| Suite | Cause racine |
| --- | --- |
| `tests/agent_loop` | dépendances MCP supprimées |
| `tests/app_server` | symbols `_account`/`_identity` et protocole ACP retirés |
| `tests/banner` | `AudioProviderView` supprimé |
| `tests/cli` | `AccountAction`, onboarding, `OtelRedactionMode` retirés |
| `tests/core/compaction` | telemetry supprimée |
| `tests/core/config` | surfaces transcribe/tts/otel retirées |
| `tests/core/llm/test_backend_error.py` | symbols backend cloud supprimés |
| `tests/core/test_identity.py` | cloud identity supprimée |
| `tests/onboarding`, `tests/setup` | `vibe.setup.*` supprimé |
| `tests/snapshots` | instantanés TUI de surfaces Windows/account |
| `tests/test_tracing.py` | tracing OpenTelemetry supprimé |
| `tests/stubs/*` | stubs des passerelles supprimées |

La dette est assumée : ces fichiers seront supprimés ou réécrits quand les
surfaces correspondantes seront réintroduites ou stabilisées. Ne pas les
réactiver en l'état.

## Vérifications statiques

```bash
python -m compileall -q vibe
uv run ruff check vibe tests/local
uv run ruff format --check vibe tests/local
uv run pyright vibe
uv run pre-commit run --all-files
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
- [ ] `make test-legacy` vert (suites shell/paths/git/tools) ;
- [ ] compilation Python verte ;
- [ ] lint/type-check vérifiés ;
- [ ] wheel construit ;
- [ ] installation locale `uv tool install --force .` ;
- [ ] smoke test llama.cpp ;
- [ ] README/CHANGELOG mis à jour ;
- [ ] aucune config utilisateur écrasée par l'installateur.
