# vibe-local-debian — hard fork local de Mistral Vibe

Hard fork **non suivi** de [mistralai/mistral-vibe](https://github.com/mistralai/mistral-vibe) : le contenu amont est vendé ici en commit racine unique, **aucune synchronisation avec l'amont n'est prévue**. Les évolutions se font directement dans ce dépôt.

**Objectif** : agent de code CLI sur Debian 13 avec backends `llama.cpp` auto-hébergés — **worker1 (KAT)** et **worker2 (Qwen3.5)**, alias serveur `worker` sur chaque port. Aucune API cloud : les serveurs llama.cpp peuvent tourner en localhost ou sur une machine distante du réseau local (il suffit d'adapter `api_base`).

## Ce qui est spécifique à ce fork

| Fichier | Rôle |
|---|---|
| `install.sh` | Installation Debian 13 : Kitty + uv + CLI vibe + config globale |
| `.vibe/config.toml` | Config de projet : providers `llamacpp-worker1`/`llamacpp-worker2` → alias `worker1`/`worker2`, télémétrie/updates coupés, compaction auto à 180k |
| `uninstall.sh` | Désinstallation complète : retire le CLI et supprime toutes les données (`~/.vibe`) |

Tout le reste est le vendor de l'amont (`mistral-vibe` 2.25.8 au moment du fork), licence Apache-2.0 conservée.

## Installation (Debian 13)

```bash
git clone https://github.com/fpich/vibe-local-debian.git
cd vibe-local-debian
./install.sh
```

Le script :
1. installe **Kitty** via apt (terminal recommandé pour le TUI) ;
2. installe **uv** dans `~/.local/bin` ;
3. installe le CLI **vibe** depuis ce dépôt (`uv tool install .`) ;
4. copie la config locale dans `~/.vibe/config.toml` (seulement si absent).

Si nécessaire : `export PATH="$HOME/.local/bin:$PATH"` dans `~/.bashrc`.

## Backends llama.cpp

Deux serveurs llama.cpp sont requis, chacun avec l'alias `--alias worker` (côté client, les modèles sont distingués par leur `api_base`). Ils peuvent tourner **en localhost ou sur une machine distante** du réseau local — la config par défaut de ce dépôt pointe vers `127.0.0.1` ; pour un serveur distant, remplacer par son adresse IP dans `api_base` :

- **worker1** — KAT sur le port `8080` ;
- **worker2** — Qwen3.5 sur le port `8081`.

Exemple d'unit systemd (adapter le `-m` et le port par serveur) :

```ini
# /etc/systemd/system/llama-worker.service (machine GPU)
[Service]
Type=simple
WorkingDirectory=/opt/llama.cpp
Environment=CUDA_VISIBLE_DEVICES=0
ExecStart=/usr/local/bin/llama-server \
  -m /opt/models/<modele>.gguf \
  --host 127.0.0.1 --port 8080 --alias worker \
  -c 262144 -np 1 --split-mode none --main-gpu 0 -ngl all \
  --n-cpu-moe 40 --fit off --load-mode mmap -fa on \
  -ctk q8_0 -ctv q8_0 -b 2048 -ub 512 -t 8 -tb 8 \
  --jinja \
  --temp <temp> --top-p <top_p> --top-k 20 --min-p 0 \
  --presence-penalty <pp> --repeat-penalty <rp>
Restart=on-failure
RestartSec=2
```

Points clés : `--jinja` (tool-calling), `--alias worker` (modèle exposé), `-c 262144` (256k contexte), `-ctk/-ctv q8_0` + `-fa on` (tenir 256k en 6 Go de VRAM), `-np 1` (une session à la fois).

**Paramètres d'échantillonnage** — à fixer côté serveur (le client n'envoie que la température) ; le `top_k` par défaut de llama.cpp est 40 : passe-le à 20 dans l'unit systemd.

## Modèles actifs

La config de projet expose **deux modèles** vers deux serveurs llama.cpp (alias serveur `worker` sur chaque port) — bascule = un seul changement dans `.vibe/config.toml` (`active_model`) :

| active_model | Modèle | Endpoint | temp client | top_p (serveur) | top_k | min_p | presence_penalty | repetition_penalty | thinking |
|---|---|---|---|---|---|---|---|---|---|
| `worker1` | KAT | `127.0.0.1:8080` | 1.0 | 0.95 | 20 | 0 | 1.5 | 1.0 | ON (preserve_thinking ON) |
| `worker2` | Qwen3.5 | `127.0.0.1:8081` | 0.7 | 0.8 | 20 | 0 | 1.5 | 1.0 | OFF |

Gestion des services (sur la machine qui héberge llama.cpp) :

```bash
sudo systemctl enable --now llama-worker1.service
sudo systemctl enable --now llama-worker2.service
systemctl status llama-worker1.service llama-worker2.service
```

Vérification depuis la machine Debian :

```bash
curl -s http://127.0.0.1:8080/v1/models   # doit lister "worker"
curl -s http://127.0.0.1:8081/v1/models   # doit lister "worker"
```

⚠️ `--host 127.0.0.1` limite l'écoute à la machine locale : aucun port exposé sur le LAN.

## Utilisation — démarrer dans un projet

Dans le répertoire du projet (le dossier où l'agent doit travailler) :

```bash
cd ~/mon-projet
vibe
```

C'est tout. L'agent ouvre un TUI interactif, lit les fichiers du répertoire courant et travaille dedans. Il faut lancer `vibe` **depuis la racine du projet** — c'est le dossier de travail de l'agent, et les sessions sont rattachées à ce dossier.

### Session de travail type

1. Décris la tâche en language naturel : « corrige le bug dans src/auth.py », « ajoute un test pour la fonction X ».
2. L'agent explore (outils read/grep), propose ou applique des modifications, te montre les diffs.
3. Approuve ou refuse chaque action sensible selon le profil d'agent choisi.
4. Termine par « commit » ou fais-le toi-même.

### Commandes de démarrage utiles

| Commande | Usage |
|---|---|
| `vibe` | Session interactive dans le dossier courant |
| `vibe --continue` | Reprend la dernière session de ce dossier |
| `vibe --resume` | Ouvre un sélecteur des sessions **de ce dossier** |
| `vibe -p "fais X"` | Mode one-shot : exécute et sort (idéal scripts/cron) |
| `vibe --agent NAME` | Profile spécifique (`plan` = lecture seule, `auto-approve` = tout approuvé) |

### En session — les commandes essentielles

| Commande | Effet |
|---|---|
| `/help` | Liste toutes les commandes disponibles |
| `/model` | Bascule worker1 (KAT) ↔ worker2 (Qwen3.5) sans quitter |
| `Shift+Tab` | Cycle les profils d'agent (ask → plan → accept-edits…) |
| `/resume` ou `/continue` | Reprend une session précédente |
| `/clear` (alias `/new`) | Nouvelle conversation à zéro (suit le modèle par défaut) |
| `/exit` | Quitter (ou `exit`, `quit`, `:q`) |

### Pour être productif

- **Créer un `AGENTS.md` à la racine du projet** : l'agent le lit automatiquement au démarrage et suit les consignes qu'il contient (style de code, commandes de build/test, conventions). C'est le meilleur levier de productivité.
- **Donner des tâches ciblées** : une tâche = un objectif clair. Les tâches larges (« améliore le projet ») diluent les petits contextes locaux.
- **worker1 (KAT) pour l'analyse et le refactoring** (thinking ON) ; **worker2 (Qwen3.5) pour les tâches simples et rapides**. Bascule via `/model`.
- **Le compteur de contexte est affiché** (`X/180k tokens`) : la **compaction automatique se déclenche à 180k tokens** — au-delà, l'agent résume et continue. Pas besoin de gérer.
- **`@fichier`** dans le message pour pointer un fichier directement ; **`/`** pour l'autocomplétion des commandes.
- Les sessions sont **rattachées au dossier** : relancer `vibe` au même endroit retrouve l'historique (`/resume`).

**Compteurs masqués dans la bannière d'accueil** (réversibles via `HIDDEN_BANNER_COUNTERS` dans `vibe/cli/textual_ui/widgets/banner/banner.py`) : connectors et MCP servers.

**Commandes masquées temporairement** (code intact, réactivables dans `vibe/cli/commands.py` via `HIDDEN_COMMANDS`) : `/connectors`, `/mcp`, `/proxy-setup`, `/remote-project`, `/teleport`, `/voice`, `/whoami`, `/leanstall`, `/unleanstall`.

**Désactivé volontairement** (config) :
- voice mode (transcription cloud non configurée) ;
- télémétrie, OTEL, update-checks, auto-update ;
- promo VSCode (apparaît au pire une fois, compteur local).

**Aucune clé Mistral requise.**

## Configuration

- Projet : `.vibe/config.toml` (versionné ici).
- Globale : `~/.vibe/config.toml` (installée par `install.sh`).
- Providers : `llamacpp-worker1` → `http://127.0.0.1:8080/v1`, `llamacpp-worker2` → `http://127.0.0.1:8081/v1` ; les modèles sont exposés sous l'alias serveur `worker` (`worker1` actif par défaut), compaction auto à 180k tokens.
- Surcharges rapides : copie du fichier et édition de `api_base` / `alias`.

## AGENTS.md

L'`AGENTS.md` du dépôt est adapté au fork : contraintes self-hosted (pas de cloud, backends llama.cpp, télémétrie désactivée) + conventions de contribution au code du CLI (ADRs, `uv run pytest`, ruff/pyright). Il guide l'agent quand il travaille dans ce dépôt. Pour orienter l'agent dans **d'autres projets**, créer un `AGENTS.md` à la racine de chaque projet.

## Points de vigilance

- Le **tool-calling du modèle actif** est le facteur limitant : si l'agent n'utilise pas bien les outils, c'est le modèle, pas la config.
- Terminal moderne requis (Kitty recommandé, xfce4-terminal fonctionne avec des raccourcis multilignes parfois limités).
- Ce fork ne suit pas l'amont : les mises à jour de sécurité/fonctionnalités de mistral-vibe ne sont pas rapatriées automatiquement.

## Licence

Apache-2.0 (héritée de l'amont, voir `LICENSE`). Le code amont est la propriété de ses auteurs ; ce fork respecte les termes de la licence.
