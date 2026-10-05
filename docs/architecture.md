# Architecture locale

## Vue d'ensemble

```text
vibe CLI / Textual TUI
        │
        ▼
local app-server
        │
        ▼
LegacySessionRuntimeController
        │
        ▼
AgentLoop (Python)
   ┌────┴─────────┐
   ▼              ▼
LLM backend      ToolManager
   │              │
   ▼              ├─ read_file
llama.cpp         ├─ write_file
OpenAI API        ├─ edit
                  ├─ grep
                  ├─ bash
                  ├─ ask_user_question
                  └─ todo
```

## Composants conservés

### CLI et TUI

`vibe/cli/` contient le launcher, les arguments CLI et la TUI Textual. Il n'existe plus de second CLI Rust.

### App-server local

`vibe/app_server/` reste une frontière interne utile : la TUI manipulate des sessions et des événements via cette couche sans connaître directement tous les détails d'`AgentLoop`. Le fork n'essaie plus de supporter ACP ou plusieurs backends de harness.

### AgentLoop

`vibe/core/agent_loop/` est le cœur agentique conservé de l'amont. Il orchestre le streaming du modèle, les appels d'outils, les approvals, la compaction, les sessions enfants encore nécessaires au code legacy et les événements vers l'UI.

La stabilisation 1.2.1 protège explicitement cette surface avec des tests structures : plusieurs méthodes supprimées accidentellement pendant le nettoyage 1.2.0 sont désormais considérées comme faisant partie du contrat interne du fork.

### Backend LLM

Le fork utilise le backend générique OpenAI-compatible. Les providers par défaut pointent vers `llama.cpp`. Aucun backend spécifique Mistral n'est livré.

### Outils

Le motor contient encore quelques outils hérités désactivés par configuration, mais le profil livré n'expose que sept outils de coding. Les outils web dédiés et les registries distants ont été supprimés.

### Permissions et workspace

Les outils fichier et shell sont liés au workspace. Les actions hors périmètre ou sensibles passent par la politique de permissions. Cette politique n'est pas une isolation OS complète.

## Sous-systèmes supprimés

La 1.2.x ne contient plus :

- CLI Rust ;
- Unified Harness Rust ;
- ACP ;
- auth/onboarding cloud Mistral ;
- backend Mistral ;
- MCP/connecteurs distants ;
- plugins distants ;
- web search/fetch ;
- Teleport/Vibe Code ;
- voice/narration ;
- Sentry/OTEL/télémétrie distante ;
- update notifier.

## Principe de changement

Le fork est maintenant en phase de stabilisation. Une nouvelle suppression n'est acceptable que si :

1. aucune référence runtime ne subsiste ;
2. les imports réels sous Python 3.13 passent ;
3. les tests structures passent ;
4. le smoke test avec un endpoint llama.cpp est rejoué.
