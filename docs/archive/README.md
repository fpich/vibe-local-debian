# Surfaces supprimées — index unique

Ce répertoire conserve la documentation **upstream archivée** de Mistral Vibe. Elle n'est
**pas normative** pour `vibe-local-debian` : elle décrit des surfaces qui n'existent plus
dans le runtime local-only. Elle sert uniquement à comprendre l'origine de certain choix
de code.

## Surfaces retirées du produit (1.2.0–1.2.1)

| Surface supprimée | Documentation archivée associée |
|---|---|
| CLI Rust / Unified Harness Rust / build Maturin | [0016-rust-cli-delivery-surface.md](upstream/0016-rust-cli-delivery-surface.md), [0011-unified-harness-backend.md](upstream/0011-unified-harness-backend.md) |
| ACP | [acp-setup.md](upstream/acp-setup.md) |
| MCP / connecteurs distants / plugins distants | [0007-extension-mechanisms.md](upstream/0007-extension-mechanisms.md) |
| Backends cloud Mistral / compat contrat backend | [0014-backend-contract-compatibility.md](upstream/0014-backend-contract-compatibility.md), [proxy-setup.md](upstream/proxy-setup.md) |
| Instrumentation / télémétrie distante (Sentry, OTEL) | [0008-feature-instrumentation.md](upstream/0008-feature-instrumentation.md) |
| Narration / voice / playback | [0017-narration-playback-in-subprocess.md](upstream/0017-narration-playback-in-subprocess.md) |
| Motor amont et surfaces de livraison | [0002-core-engine-and-delivery-surfaces.md](upstream/0002-core-engine-and-delivery-surfaces.md) |

La frontière produit actuelle et normative est définie dans
[ADR 0001 — Local runtime boundary](../adr/0001-local-runtime-boundary.md).
