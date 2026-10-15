# Configuration

## Fichiers

Ordre pratique pour ce fork :

- configuration utilisateur : `~/.vibe/config.toml` ;
- configuration du dépôt : `.vibe/config.toml` ;
- `VIBE_HOME` permet de déplacer le répertoire utilisateur.

`install.sh` ne remplace jamais un `~/.vibe/config.toml` existent.

## Workers llama.cpp

Chaque worker est un provider générique OpenAI-compatible :

```toml
[[providers]]
# cache_prompt = true (défaut) : llama.cpp réutilise son cache de préfixe
# entre les tours. Passer à false si votre serveur ne supporte pas ce champ.
name = "llamacpp-worker1"
api_base = "http://127.0.0.1:8080/v1"
api_key_env_var = ""
api_style = "openai"
backend = "generic"
reasoning_field_name = "reasoning_content"
emits_finish_reason = true
```

Pour un serveur distant sur le LAN, modifier uniquement `api_base`, par exemple :

```toml
api_base = "http://192.168.1.116:8080/v1"
```

## Provider externe compatible OpenAI (API Albert, etc.)

Le template du dépôt inclut depuis la 1.2.6 un provider Albert préconfiguré (clé via `ALBERT_API_KEY` uniquement, jamais en dur). Pour ajouter un autre endpoint distant compatible OpenAI — par exemple l'API Albert (https://albert.api.etalab.gouv.fr/v1) avec un accès enseignant — ajoutez dans `~/.vibe/config.toml` :

```toml
# Clé dans l'environnement, jamais dans le fichier :
#   export ALBERT_API_KEY="votre_jeton"   # dans ~/.bashrc

[[providers]]
name = "albert"
api_base = "https://albert.api.etalab.gouv.fr/v1"
api_key_env_var = "ALBERT_API_KEY"
api_style = "openai"
backend = "generic"
emits_finish_reason = true

[[models]]
name = "qwen3-coder-30b-a3b-instruct"   # nom exact exposé par l'endpoint
provider = "albert"
alias = "albert-coder"                   # nom sélectionnable via /model
display_name = "Albert Coder (Qwen3 30B)"
temperature = 0.15
thinking = "off"
auto_compact_threshold = 196000          # ~75 % de la fenêtre du modèle

# … répéter [[models]] pour chaque modèle ; exemples Albert :
#   mistral-small-3-2-24b-instruct-2506 (131072), ministral-3-8b-instruct-2512 (262144),
#   gpt-oss-120b (131072), qwen3-coder-30b-a3b-instruct (262144),
#   deepseek-v4-flash-0731 (131072, expérimental), gemma-4-31b-it (262144, expérimental)
```

Puis autorisez-les dans l'allowlist (elle agit sur `name`, pas sur l'alias) :

```toml
allowed_models = ["worker*", "mistral-small*", "ministral*", "gpt-oss*", "qwen3-coder*", "deepseek*", "gemma*"]
```

Basculer de modèle : `active_model = "albert-coder"` ou via `/model` dans la TUI. Un provider `api_base` distant reste autorisé par la frontière du fork (comme un serveur llama.cpp sur le LAN) ; les modèles OCR (ex. `lightonocr-2-1b`) ne sont pas des modèles de chat et ne sont pas déclarables comme LLM principal.

## Modèles

Chaque serveur llama.cpp expose un nom distinct : `worker1` (port 8080) et `worker2` (port 8081). L'alias client correspond au nom du modèle.

```toml
active_model = "worker1"
allowed_models = ["worker*"]
```

La logique `allowed_models` est fail-closed : une allowlist sans correspondence ne réactive pas des modèles non autorisés.

## Outils

Le profil minimal :

```toml
enabled_tools = [
  "bash",
  "read_file",
  "write_file",
  "edit",
  "grep",
  "ask_user_question",
  "todo",
]
```

Ajouter un outil élargit explicitement les capacités du modèle. Ne pas réintroduire un outil réseau par défaut.

## Serveurs MCP stdio locaux

Les serveurs MCP locaux en transport `stdio` sont supportés (ADR 0002) ; les transports HTTP ne le sont pas. Chaque entrée `[[mcp_servers]]` lance un sous-processus qui parle JSON-RPC sur stdin/stdout :

```toml
[[mcp_servers]]
name = "rea"
transport = "stdio"
command = "rea-mcp"          # ou ["uvx", "rea-mcp"]
args = []
startup_timeout_sec = 10.0
tool_timeout_sec = 60.0
```

Les outils du serveur sont exposés au modèle sous la forme `mcp_<serveur>_<outil>` (par exemple `mcp_rea_search`) et suivent la politique de permissions existante. Un serveur qui échoue au démarrage apparaît comme erreur de découverte dans `/mcp` sans interrompre la session.

Pour le cas d'usage REA (Reverse Engineer Anything) avec Ghidra comme provider d'analyse native, `scripts/install_ghidra_rea.sh` installe et vérifie la chaîne complète (JDK 21, Ghidra 12.1.4 épinglé, radare2 épinglé — absent des dépôts trixie —, `rea-agents` npm épinglé) :

```bash
scripts/install_ghidra_rea.sh --doctor   # vérifier l'état
scripts/install_ghidra_rea.sh            # installer
```

## Compaction

Les deux modèles fournis utilisent :

```toml
auto_compact_threshold = 80000
```

Le seuil doit rester inférieur à la fenêtre réellement disponible sur le serveur afin de laisser de la marge pour la réponse, les tools et le résumé.

## Titres de session

```toml
[session_logging]
auto_title = "first_message"
```

`first_message` ne consomme aucun appel LLM additionnel. `llm` peut être utilisé si l'utilisateur accept un appel de modèle supplémentaire.

## Variables utiles

- `VIBE_HOME` : répertoire de données/config, défaut `~/.vibe`.
- `LOG_LEVEL` : `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
- `LOG_MAX_BYTES` : rotation du fichier de log.
- `VIBE_<CHAMP>` : surcharge de certain champs de configuration via Pydantic settings.

## Vérification

```bash
curl -s http://127.0.0.1:8080/v1/models
curl -s http://127.0.0.1:8081/v1/models
```

Les réponses doivent contenir les modèles `worker1` et `worker2` respectivement.
