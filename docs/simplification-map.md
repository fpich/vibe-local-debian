# Cartographie de simplification — vibe-local-debian local-only

Cartographie fichier-par-fichier de la v1.2.0, à utiliser comme feuille de route de commits.
Chaque ligne : KEEP (conserver tel quel), DELETE (supprimer), MODIFY (conserver mais réduire).
Colonne « couper d'abord » : dépendances à retirer avant de pouvoir supprimer la ligne.

Légende étapes : E1..E19 = plan de commits (voir README/plan). « — » = aucune dépendance.

## Racine `vibe/`

| Chemin | Lignes | Verdict | Étape | Couper d'abord |
|---|---|---|---|---|
| `vibe/__init__.py` | — | KEEP | — | — |
| `vibe/_experimental_harness.py` | — | DELETE | E5 | forcer legacy dans `cli/entrypoint.py` |
| `vibe/agents.py` | — | KEEP | — | — |
| `vibe/config_values.py` | — | KEEP | — | — |
| `vibe/feedback.py` | — | KEEP | — | — |
| `vibe/permissions.py` | — | KEEP | — | — |
| `vibe/questions.py` | — | KEEP | — | — |
| `vibe/user_content.py` | — | KEEP | — | — |
| `vibe/whats_new.md` | — | DELETE | E13 | `cli/update_notifier/` |
| `vibe/core_experimental_harness.py` | — | DELETE | E5 | idem `_experimental_harness.py` |

## `vibe/acp/` — 5 355 l. — DELETE (E6)

Tout le paquet : `entrypoint.py`, `commands/`, `tools/`, `agent.py`, `client.py`…
Dépendances à couper : entry point `vibe-acp` (pyproject), `vibe-app-server.spec`/`vibe-acp.spec`,
ADR 0017, `tests/acp/`, narration en subprocess (`_narration.py` côté app_server → E11).

## `vibe/cli-rust/` — 57 273 l. Rust — DELETE (E4)

Tout le paquet Cargo. Couper d'abord : `vibe/cli/_rust.py`, routeur `VIBE_CLI` dans
`vibe/cli/launcher.py`, cibles `make start/run/build` (Makefile), `client-e2e/` (goldens),
`tests/cli/` spécifiques Rust, features `voice` (→ E11 pour libasound2).

## `harness/` — 90 874 l. Rust+Python — DELETE (E5)

`harness/core/`, `harness/runtimes/python/` (runtime `mistralai_vibe_local_harness`).
Couper d'abord : `vibe/_experimental_harness.py`, `vibe/cli/entrypoint.py` (force legacy),
`vibe/app_server/_unified_*.py` (15 fichiers), `_unified_harness_backend_adapter.py`,
`build_backend/`, `[tool.maturin]` (→ E17), `tool.uv.cache-keys` harness.

## `vibe/app_server/` — 50 124 l. — MODIFY (E14) puis DELETE particle

| Chemin | Verdict | Étape |
|---|---|---|
| `_legacy_composition.py`, `_legacy_session_backend.py`, `_legacy_session_runtime.py` | KEEP | E14 (devient la seule composition) |
| `stdio.py`, `connection.py`, `protocol.py`, `events.py`, `session.py`, `models.py` | KEEP (réduits) | E14 |
| `_unified_*.py` (15 fichiers : harness, permissions, scratchpad, tool projection, vibe_code, scheduled loops, tool observability) | DELETE | E5 |
| `_vibe_code.py`, `_worktree_session.py`, `_worktree_effects.py` | DELETE | E10 (worktrees : décision E19) |
| `_mcp_authorization_bridge.py`, `_mcp_auth.py`, `mcp_catalog.py`, `_plugin_mcp.py`, `connector_catalog.py` | DELETE | E7 |
| `_plugins.py`, `plugin_catalog.py` | DELETE | E7 |
| `_account.py`, `_provider_credentials.py`, `identity.py`, `host.py` (partie cloud) | DELETE | E9 |
| `_narration.py` | DELETE | E11 |
| `telemetry_port.py`, `_connector_observability.py` | DELETE | E12 |
| `_review.py`, `review.py` | KEEP (si /review conservé) | — |
| `entrypoint.py`, `server.py` | MODIFY | E14 (plus de `--experimental-harness`, un seul backend) |

## `vibe/cli/` — 33 606 l. — MODIFY

| Chemin | Verdict | Étape |
|---|---|---|
| `launcher.py` | MODIFY | E4 (suppression routeur Rust) |
| `_rust.py` | DELETE | E4 |
| `cli.py`, `entrypoint.py`, `commands.py`, `theme.py`, `autocompletion/`, `history_manager.py`, `input_modes.py`, `plan_offer/`, `textual_ui/**` (hors ci-dessous) | KEEP | — |
| `textual_ui/widgets/vibe_code_project/` | DELETE | E10 |
| `audio_player/`, `audio_recorder/`, `voice_manager/`, `narrator_manager/`, `tts/`, `transcribe/`, `lazy_audio_managers.py`, `audio_request_metadata.py` | DELETE | E11 |
| `update_notifier/` | DELETE | E13 |
| `vscode_extension_promo/` | DELETE | E13 |
| `mcp_command.py` | DELETE | E7 |
| `browser_sign_in` (si présent dans cli) | DELETE | E9 |
| `profiler.py`, `_process_title.py` | KEEP | — |

## `vibe/core/` — 63 305 l. — MODIFY (cœur conservé)

| Chemin | Verdict | Étape |
|---|---|---|
| `agent_loop/`, `loop.py`, `agent_loop_hooks.py` | **KEEP — ne pas réécrire** | — |
| `tools/builtins/` : `read_file.py`, `edit.py`, `write_file.py`, `grep.py`, `bash.py`, `todo.py`, `ask_user_question.py`, `task.py`, `skill.py`, `git_bash.py`, `managed_shell/`, `_shell_*` | **KEEP** | — |
| `tools/builtins/web_fetch.py`, `web_search.py` | DELETE | E8 |
| `tools/builtins/experimental_bash.py`, `windows_shell.py` | DELETE/MODIFY | E18 (Debian only : windows_shell → DELETE) |
| `tools/permissions.py`, `permissions` (racine `vibe/permissions.py`) | **KEEP** | — |
| `compaction/` | **KEEP** | — |
| `session/` (16 fichiers : logger, resume, index, migration, permissions) | **KEEP** | — |
| `session/worktrees.py` | décision | E19 |
| `llm/`, `llm/backend/` | KEEP (retirer provider mistral) | E9 |
| `config/` | MODIFY | E2 (allowlist/fail-closed), E15 (schéma réduit) |
| `config/harness_files/`, `config/layers/` (parts harness) | MODIFY | E5/E15 |
| `prompts/` | KEEP (retirer `vision_describe.md`) | E11 |
| `workspace.py`, `trusted_folders.py`, `checkpoints/`, `rewind/`, `identity.py`, `paths/` | **KEEP** | — |
| `hooks/`, `agents/`, `skills/`, `subagents.py` | KEEP | E19 (décision skills/subagents) |
| `tools/mcp/`, `tools/connectors/`, `tools/remote.py`, `tools/mcp_sampling.py`, `tools/mcp_settings.py` | DELETE | E7 |
| `auth/` (`mcp_oauth.py`) | DELETE | E7 |
| `plugins/` (20 fichiers) | DELETE | E7 |
| `teleport/` (7 fichiers), `vibe_code_project/` (6 fichiers) | DELETE | E10 |
| `telemetry/` (5 fichiers), `experiments/` (9 fichiers) | DELETE | E12 |
| `vision/` | DELETE | E11 |
| `git/worktree/` | décision | E19 |
| `review/` | KEEP | — |
| `utils/` | KEEP (retirer `sse.py` si plus utilisé) | — |
| `autocompletion/` | KEEP | — |

## `vibe/observability/` — DELETE (E12)
## `vibe/plugins/` — vide — DELETE (E7)
## `vibe/setup/` — 4 356 l. — DELETE (E9)

Onboarding cloud, `auth/`, `update_prompt/`, `trusted_folders/` (absorber le minimum
dans `cli/entrypoint.py` : création `~/.vibe`, config défaut).

## `vibe/utils/` — 1 648 l. — KEEP

## Hors `vibe/`

| Chemin | Verdict | Étape |
|---|---|---|
| `tests/` — 210 029 l. | MODIFY | E18 (purge acp/mcp/connectors/voice/narrator/onboarding/observability/browser_signin/update_notifier/vscode_promo/mock si morts) + au fil de E4..E14 |
| `client-e2e/` — 13 328 l. | DELETE | E4/E5 |
| `pyinstaller/`, `vibe.spec`, `vibe-acp.spec`, `vibe-app-server.spec` | DELETE | E17 |
| `build_backend/` | DELETE | E17 |
| `distribution/`, `action.yml`, `flake.nix`, `flake.lock`, `scripts/ci/` | DELETE | E13/E17 |
| `pyproject.toml`, `uv.lock` | MODIFY | E16 (purge deps mcp/mistralai/otel/sentry/miniaudio/websockets…, régénérer lock) puis E17 (maturin→hatchling) |
| `Makefile` | MODIFY | E4 (cibles Rust) |
| `install.sh` / `uninstall.sh` | MODIFY | E3 |
| `docs/adr/` | MODIFY | mettre à jour au fil des étapes (0016 Rust CLI, 0017 narration ACP, 0011 unified harness → retirées) |
| `harness/` (déjà ci-dessus) | DELETE | E5 |

## Bilan quantitatif estimé

- Supprimé : ~260k lignes (Rust 104k, harness runtime, app_server unifié, acp, setup,
  voice/narrator, telemetry, teleport/vibe_code, plugins/mcp/connectors, tests morts,
  e2e, packaging).
- Conservé : ~114k lignes Python (core motor ~63k dont une partie réduite, cli ~20k
  après purge, app_server ~8k après réduction, tests de contrat + tests vivants).
