# vibe-local-debian — hard fork local de Mistral Vibe

Hard fork **non suivi** de [mistralai/mistral-vibe](https://github.com/mistralai/mistral-vibe) : le contenu amont est vendé ici en commit racine unique, **aucune synchronisation avec l'amont n'est prévue**. Évolutions à ta discrétion, directement dans ce dépôt.

**Objectif** : agent de code CLI 100 % local sur Debian 13, backend `llama.cpp` — modèle **Ornith 1.5** (`--alias ornith`, `--jinja`, 256k contexte) sur `192.168.1.116:8080`. Aucune API cloud.

## Ce qui est spécifique à ce fork

| Fichier | Rôle |
|---|---|
| `install.sh` | Installation Debian 13 : Kitty + uv + CLI vibe + config globale |
| `.vibe/config.toml` | Config de projet : provider `llamacpp` → alias unique `worker` (ornith/kat), télémétrie/updates coupés |

Tout le reste est le vendor de l'amont (`mistral-vibe` 2.25.8 au moment du fork), licence Apache-2.0 conservée.

## Installation (Debian 13, XFCE)

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

## Backend llama.cpp

Le serveur tourne sur la machine GPU (`192.168.1.116`) via l'unit systemd `ornith15-35B-solo.service` (llama.cpp compilé local, RTX 2060, CUDA) :

```ini
# /etc/systemd/system/ornith15-35B-solo.service (machine GPU)
[Service]
Type=simple
WorkingDirectory=/home/fabien/llama.cpp
Environment=CUDA_VISIBLE_DEVICES=0
ExecStart=/home/fabien/llama.cpp/build/bin/llama-server \
  -m /home/fabien/models/Ornith-1.5-35B-A3B-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 --alias worker \
  -c 262144 -np 1 --split-mode none --main-gpu 0 -ngl all \
  --n-cpu-moe 40 --fit off --load-mode mmap -fa on \
  -ctk q8_0 -ctv q8_0 -b 2048 -ub 512 -t 8 -tb 8 \
  --jinja
Restart=on-failure
RestartSec=2
```

Points clés : `--jinja` (tool-calling), `--alias worker` (modèle exposé), `-c 262144` (256k contexte), `-ctk/-ctv q8_0` + `-fa on` (tenir 256k en 6 Go de VRAM), `-np 1` (une session à la fois).

**Paramètres d'échantillonnage** — à fixer côté serveur (le client n'envoie que la température) : `--temp 0.6 --top-p 0.95 --top-k 20`. Le `top_k` par défaut de llama.cpp est 40 : passe-le à 20 dans l'unit systemd.

## Modèles supportés

La config de projet expose **deux modèles interchangeables** sous l'alias unique `worker` — bascule = un seul changement dans `.vibe/config.toml` :

| active_model | Modèle | Points forts | Quant recommandé |
|---|---|---|---|
| `worker-ornith` | Ornith 1.5 35B-A3B | Raisonnement long, chasse aux bugs | Q4_K_M (déjà en place) |
| `worker-kat` | KAT-Coder V2.5 Dev | Tool-calls réguliers, économe en tokens, variance faible | [mudler APEX-I-Compact](https://huggingface.co/mudler/KAT-Coder-V2.5-Dev-APEX-GGUF) (Q4, ~15,4 Go) |

Même architecture (Qwen 35B MoE A3B) → même unit systemd, seul le `-m` et l'`--alias worker` changent.

```bash
# KAT : téléchargement du quant APEX-I-Compact (base Q4_K_M + imatrix)
wget -c https://huggingface.co/mudler/KAT-Coder-V2.5-Dev-APEX-GGUF/resolve/main/KAT-Coder-V2.5-Dev-APEX-I-Compact.gguf -P ~/models/
# puis éditer le -m de l'unit systemd, garder --alias worker, et dans .vibe/config.toml :
#   active_model = "worker-kat"
```

Gestion du service (machine GPU) :

```bash
sudo systemctl enable --now ornith15-35B-solo.service
systemctl status ornith15-35B-solo.service
```

Vérification depuis la machine Debian :

```bash
curl -s http://192.168.1.116:8080/v1/models   # doit lister "worker"
```

⚠️ `--host 0.0.0.0` expose le port sur le LAN : ne publie pas le port 8080 sur Internet.

`--host 0.0.0.0` expose le port sur le LAN : ne publie pas le port 8080 sur Internet.

## Utilisation

```bash
cd ~/mon-projet
vibe
```

Tout le cœur fonctionne en local : chat, outils (read/write/edit/grep/shell), todo, sous-agents, agents intégrés, skills, sessions, thèmes, rendu Markdown/diffs, autocomplétion `@` et `/`.

**Désactivé volontairement** (config) :
- voice mode (transcription cloud non configurée) ;
- télémétrie, OTEL, update-checks, auto-update ;
- promo VSCode (apparaît au pire une fois, compteur local).

**Aucune clé Mistral requise.**

## Configuration

- Projet : `.vibe/config.toml` (versionné ici).
- Globale : `~/.vibe/config.toml` (installé par `install.sh`).
- Le provider `llamacpp` pointe sur `http://192.168.1.116:8080/v1` ; les modèles sont exposés sous l'alias `worker` (`worker-ornith` actif par défaut), compaction auto à 200k tokens.
- Surcharges rapides : copie du fichier et édition de `api_base` / `alias`.

## AGENTS.md

L'`AGENTS.md` du dépôt est adapté au fork : contraintes local-only (pas de cloud, backend llama.cpp, télémétrie désactivée) + conventions de contribution au code du CLI (ADRs, `uv run pytest`, ruff/pyright). Il guide l'agent quand il travaille dans ce dépôt. Pour orienter l'agent dans **tes projets**, crée plutôt un `AGENTS.md` à la racine de chaque projet.

## Points de vigilance

- Le **tool-calling d'Ornith** est le facteur limitant : si l'agent n'utilise pas bien les outils, c'est le modèle, pas la config.
- Terminal moderne requis (Kitty recommandé, xfce4-terminal fonctionne avec des raccourcis multilignes parfois limités).
- Ce fork ne suit pas l'amont : les mises à jour de sécurité/fonctionnalités de mistral-vibe ne sont pas rapatriées automatiquement.

## Licence

Apache-2.0 (héritée de l'amont, voir `LICENSE`). Le code amont est la propriété de ses auteurs ; ce fork respecte les termes de la licence.
