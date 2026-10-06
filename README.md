# vibe-local-debian

Agent de code CLI **local-first** pour Debian 13, dérivé de Mistral Vibe et simplifié pour utiliser exclusivement des serveurs `llama.cpp` compatibles avec l'API OpenAI.

La branche stable **1.2.1** conserve le moteur agentique Python, la TUI Textual, les sessions, la compaction, les worktrees Git et les permissions d'outils. Les surfaces cloud et les runtimes alternatifs de l'amont ont été retirés.

## Périmètre du fork

Le chemin d'exécution principal est volontairement réduit :

```text
Textual CLI
    ↓
local app-server
    ↓
AgentLoop Python
    ↓
llama.cpp (OpenAI-compatible)
    ↓
read_file / write_file / edit / grep / bash / todo / ask_user_question
    ↓
workspace + permissions
```

Ne font plus partie du produit : authentification Mistral, providers cloud Mistral, ACP, CLI Rust, Unified Harness Rust, MCP/connecteurs distants, plugins distants, `web_search`, `web_fetch`, Teleport/Vibe Code, voice/narration, Sentry/OTEL/télémétrie et update notifier.

> **Local-first ne signifie pas sandbox réseau.** Le client ne contient plus d'outil web dédié ni de backend cloud, mais l'outil `bash` peut lancer des programmes ayant eux-mêmes accès au réseau si l'utilisateur les autorise. Le serveur LLM peut également se trouver sur le LAN.

## Installation — Debian 13

```bash
git clone https://github.com/fpich/vibe-local-debian.git
cd vibe-local-debian
./install.sh
```

Le script :

1. vérifie Debian 13 ;
2. installe `curl`, les certificats CA et Kitty si nécessaire ;
3. installe `uv` avec un installateur épinglé et vérifié par SHA-256 si `uv` est absent ;
4. installe **ce dépôt local** avec `uv tool install --force` ;
5. copie `.vibe/config.toml` vers `~/.vibe/config.toml` uniquement si la configuration globale n'existe pas déjà.

Pour une mise à jour du code sans toucher à ta configuration :

```bash
cd ~/vibe-local-debian
uv tool install --force .
```

## Configurer le serveur llama.cpp

La configuration utilisateur est :

```text
~/.vibe/config.toml
```

La configuration fournie par le dépôt est :

```text
.vibe/config.toml
```

Par défaut, les deux workers pointent sur la machine locale :

```toml
api_base = "http://127.0.0.1:8080/v1"  # worker1
api_base = "http://127.0.0.1:8081/v1"  # worker2
```

Pour un serveur LAN, par exemple `192.168.1.116` :

```toml
[[providers]]
name = "llamacpp-worker1"
api_base = "http://192.168.1.116:8080/v1"

[[providers]]
name = "llamacpp-worker2"
api_base = "http://192.168.1.116:8081/v1"
```

Vérification :

```bash
curl -s http://192.168.1.116:8080/v1/models
curl -s http://192.168.1.116:8081/v1/models
```

Chaque serveur doit exposer son modèle (par exemple `worker1` côté client), typiquement avec :

```bash
llama-server \
  -m /chemin/vers/modele.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --alias worker1 \
  --jinja
```

Si le client et `llama.cpp` tournent sur la même machine, préfère `--host 127.0.0.1`. Si le serveur est distant, lie-le à son IP LAN ou à `0.0.0.0` et limite l'accès avec le pare-feu. HTTP sur le LAN n'est pas chiffré ; utilise HTTPS/reverse proxy si le réseau n'est pas de confiance.

## Modèles fournis

La config du dépôt expose deux aliases côté client :

| Alias | Usage prévu | Port par défaut | Thinking |
|---|---|---:|---|
| `worker1` | KAT / analyse et refactoring | 8080 | `high` |
| `worker2` | Qwen3.5 / tâches rapides | 8081 | `off` |

Chaque serveur expose un nom distinct (`worker1`, `worker2`). `allowed_models = ["worker*"]` est appliqué en mode **fail-closed** : si aucun modèle autorisé n'est disponible, le client ne retombe pas sur une liste cloud.

La compaction automatique est configurée à **90 000 tokens** pour les deux workers.

## Utilisation

Dans le répertoire que l'agent doit traiter :

```bash
cd ~/mon-projet
vibe
```

Test minimal :

```bash
mkdir -p ~/test-vibe
cd ~/test-vibe
git init
echo "print('hello')" > app.py
vibe
```

Exemples de démarrage :

```bash
vibe                              # TUI interactif
vibe --continue                   # dernière session
vibe --resume                     # sélecteur de sessions
vibe -p "analyse le dépôt"        # mode one-shot
vibe --workdir ~/src/projet       # choisit explicitement le workspace
vibe --agent plan                 # profil lecture/planification
vibe --auto-approve -p "..."      # sans prompts d'approbation : à utiliser avec prudence
```

Commandes principales dans la TUI : `/help`, `/config`, `/model`, `/thinking`, `/reload`, `/clear`, `/compact`, `/status`, `/resume`, `/rename`, `/todo`, `/rewind`, `/branch`, `/retry`, `/loop`, `/theme`, `/log`, `/log-level` et `/exit`.

## Outils exposés au modèle

Le profil local fourni n'expose que :

```text
bash
read_file
write_file
edit
grep
ask_user_question
todo
```

`task` et `skill` existent encore dans le moteur pour compatibilité interne mais ne sont pas exposés dans le profil minimal. Les outils réseau `web_search` et `web_fetch` ont été supprimés.

## Sécurité et workspace

Vibe est un agent capable de lire, modifier des fichiers et exécuter des commandes. Les protections du workspace et les demandes d'approbation restent actives, mais elles ne remplacent pas un conteneur ou une VM.

Recommandations :

- lance `vibe` à la racine exacte du projet ;
- évite `--auto-approve` sur un dépôt non fiable ;
- inspecte les commandes `bash` qui demandent une permission ;
- ne stocke pas de secrets inutiles dans le workspace ;
- garde le serveur llama.cpp inaccessible depuis Internet ;
- utilise un compte Unix dédié ou un conteneur pour du code réellement non fiable.

Voir [SECURITY.md](SECURITY.md) pour le modèle de menace détaillé.

## AGENTS.md

Place un `AGENTS.md` à la racine d'un projet pour fournir à l'agent les conventions de code, commandes de build/test et contraintes locales. Le dépôt contient son propre [AGENTS.md](AGENTS.md) pour les contributions au fork.

## Développement

```bash
uv sync --group dev
uv run pytest
uv run ruff check vibe tests/local
uv run pyright
uv build --wheel
```

La suite de tests maintenue du fork se concentre sur les invariants local-only, l'intégrité du runtime legacy Python, le packaging et les protections install/uninstall. Les anciens tests de fonctionnalités supprimées ne font plus partie de la suite stable.

Documentation complémentaire :

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Tests et stabilisation](docs/testing.md)
- [Documentation](docs/README.md)
- [Historique](CHANGELOG.md)

## Compatibilité et origine

- Debian 13 ciblé pour l'installateur.
- Python 3.12 et 3.13 supportés par le package stable.
- Le nom de distribution Python reste `mistral-vibe` pour conserver la compatibilité avec l'installation existante et les chemins `uv tool`.
- Le code est dérivé de Mistral Vibe sous licence Apache-2.0. Ce fork est indépendant et ne suit pas automatiquement l'amont.
