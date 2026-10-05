# ADR 0001 — Local runtime boundary

## Status

Accepted for `vibe-local-debian` 1.2.1.

## Context

The upstream project supported several delivery surfaces, cloud services and runtime implementations. This fork is intentionally narrower: a Debian CLI coding agent backed by self-hosted OpenAI-compatible `llama.cpp` endpoints.

Keeping dormant cloud/alternate-runtime behavior as a supported contract made the fork hard to reason about and caused regressions during the 1.2.0 cleanup.

## Decision

The supported product boundary is:

- Python CLI and Textual TUI;
- local app-server boundary;
- legacy Python `AgentLoop`;
- generic OpenAI-compatible backend;
- self-hosted model endpoints configured by the user;
- local sessions, compaction, Git/worktree support and permissioned coding tools.

The default tool profile is restricted to `bash`, `read_file`, `write_file`, `edit`, `grep`, `ask_user_question` and `todo`.

Cloud auth/providers, ACP, Rust CLI, Unified Harness, MCP/connectors, dedicated web tools, Teleport/Vibe Code, voice/narration and remote telemetry are outside the supported boundary.

## Consequences

- New work should simplify the supported path rather than preserve compatibility with removed delivery surfaces.
- A compatibility type may remain internally when deleting it would require a risky rewrite, but it must not instantiate a removed runtime or perform remote I/O.
- Runtime deletion requires real import/startup tests under Python 3.13 in addition to static compilation.
- Model allowlists fail closed and must never reactivate a cloud fallback.
- The project keeps the Python distribution name `mistral-vibe` only for installation compatibility; this does not imply upstream feature parity.
