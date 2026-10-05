# What's new in v1.2.1

- **Stabilized Python runtime**: startup issues introduced during the 1.2.0 cleanup are fixed and protected by regression tests.
- **Local-only product boundary**: cloud auth/providers, ACP, MCP/connectors, Rust runtimes, dedicated web tools, voice, telemetry and Teleport are no longer part of the supported runtime.
- **Safer local install**: `install.sh` always installs the current checkout and never upgrades the distribution name from a public package index.
- **Two self-hosted workers**: configure `worker1` and `worker2` in `~/.vibe/config.toml`; localhost and LAN llama.cpp servers are supported.
- **Focused coding tools**: the default model-visible tools are bash, read/write/edit, grep, ask-user and todo.
