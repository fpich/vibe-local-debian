# Politique de sécurité

`vibe-local-debian` est un fork indépendant orienté exécution locale. Il n'est pas un produit Mistral AI et les vulnérabilités spécifiques à ce fork ne doivent pas être envoyées au support Mistral.

## Signaler une vulnérabilité

Privilégier un signalement privé via les mécanismes de sécurité du dépôt GitHub. Si aucun canal privé n'est disponible, ouvrir une issue avec uniquement une description générale et demander un canal privé avant de publier un exploit, un secret ou des données sensibles.

Inclure si possible : version/commit, Debian/Python utilisés, étapes minimales de reproduction, configuration pertinente avec secrets masqués, impact attendu et différence entre comportement attendu et observé.

## Modèle de menace

Le produit est conçu pour que **l'inférence** soit effectuée par un ou plusieurs serveurs `llama.cpp` choisis par l'utilisateur. Les backends cloud Mistral, MCP/connecteurs distants, outils web dédiés, télémétrie, Sentry et update notifier ont été retirés.

Cela ne constitue toutefois pas une sandbox réseau ou système :

- `bash` peut exécuter un programme qui accède au réseau ;
- un build/test du project peut télécharger des dépendances ;
- un serveur `llama.cpp` placé sure le LAN reçoit les prompts, extraits de fichiers et résultats d'outils transmis au modèle ;
- HTTP ne chiffre pas ce traffic ;
- les permissions Vibe réduisent les actions accidentelles mais ne remplacent pas l'isolation Unix, un conteneur ou une VM.

## Frontière du workspace

Le répertoire courant est la frontière principale de travail. Les accès sensibles ou extérieurs au workspace passent par le système de permissions lorsque le profil ne les autorise pas explicitement.

Pour du code non fiable :

- ne pas utiliser `--auto-approve`/`--yolo` ;
- utiliser un compte Unix sans secrets et avec des droits minimaux ;
- préférer un conteneur/VM si le dépôt peut être hostile ;
- examiner les commands shell proposées avant approbation.

## Serveur llama.cpp distant

Pour un serveur sure le LAN :

- écouter sure une IP LAN dédiée lorsque possible plutôt que sure toutes les interfaces ;
- filtrer les ports 8080/8081 avec le pare-feu ;
- ne pas exposer les endpoints directement sure Internet ;
- utiliser TLS ou un tunnel si le réseau n'est pas de confiance.

## Secrets

Le profil par défaut ne requiert aucune clé Mistral. Éviter de placer des tokens dans `AGENTS.md`, les prompts, les fichiers de logs ou le dépôt. Les logs sont stockés sous `$VIBE_HOME/logs` (par défaut `~/.vibe/logs`).
