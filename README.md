# vibe-local-debian — hard fork local de Mistral Vibe

Hard fork **non suivi** de [mistralai/mistral-vibe](https://github.com/mistralai/mistral-vibe) : le contenu amont est vendé ici en commit racine unique, **aucune synchronisation avec l'amont n'est prévue**. Évolutions à ta discrétion, directement dans ce dépôt.

**Objectif** : agent de code CLI 100 % local sur Debian 13, backend `llama.cpp` — modèle **Ornith 1.5** (`--alias ornith`, `--jinja`, 256k contexte) sur `192.168.1.116:8080`. Aucune API cloud.

## Ce qui est spécifique à ce fork

| Fichier | Rôle |
|---|---|
| `install.sh` | Installation Debian 13 : Kitty + uv + CLI vibe + config globale |
| `.vibe/config.toml` | Config de projet : provider `llamacpp` → ornith, télémétrie/updates coupés |

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

Sur la machine GPU, lance ton serveur avec `--jinja` (indispensable pour le tool-calling) :

```bash
llama-server -m /chemin/Ornith-1.5-35B-A3B-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 --alias ornith \
  -c 262144 --jinja
```

Vérification depuis la machine Debian :

```bash
curl -s http://192.168.1.116:8080/v1/models   # doit lister "ornith"
```

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
- Le provider `llamacpp` pointe sur `http://192.168.1.116:8080/v1` ; le modèle actif est `ornith`, compaction auto à 200k tokens.
- Surcharges rapides : copie du fichier et édition de `api_base` / `alias`.

## AGENTS.md

L'`AGENTS.md` présent est celui de l'amont : conventions pour **contribuer au code du CLI** (ADRs, `uv run pytest`, ruff/pyright). Il s'applique si tu modifies le code du fork. Pour orienter l'agent dans **tes projets**, crée plutôt un `AGENTS.md` à la racine de chaque projet.

## Points de vigilance

- Le **tool-calling d'Ornith** est le facteur limitant : si l'agent n'utilise pas bien les outils, c'est le modèle, pas la config.
- Terminal moderne requis (Kitty recommandé, xfce4-terminal fonctionne avec des raccourcis multilignes parfois limités).
- Ce fork ne suit pas l'amont : les mises à jour de sécurité/fonctionnalités de mistral-vibe ne sont pas rapatriées automatiquement.

## Licence

Apache-2.0 (héritée de l'amont, voir `LICENSE`). Le code amont est la propriété de ses auteurs ; ce fork respecte les termes de la licence.
