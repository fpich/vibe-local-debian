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

## Compaction

Les deux modèles fournis utilisent :

```toml
auto_compact_threshold = 90000
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
