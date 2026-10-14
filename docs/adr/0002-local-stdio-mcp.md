# ADR 0002 — Local stdio MCP support

## Status

Accepted for `vibe-local-debian` 1.2.5.

## Context

ADR 0001 removed MCP/connectors from the supported boundary. The removal
targeted remote registries, HTTP transports, cloud authorization bridges and
the upstream `mcp` SDK dependency.

A recurring local-only use case remains: attaching a local MCP server (for
example REA) running on the same machine as a subprocess speaking stdio
JSON-RPC. This needs no network, no authorization provider and no registry:
it is the same trust level as the `bash` tool, which already executes local
commands under the permission policy.

The typed surfaces survived the pruning: the config models
(`MCPStdio` in `vibe/core/config/models.py`), the app-server session options
(`SessionMCPStdioServer`), the client projection models (`MCPState`,
`MCPSourceSummary`) and the tool-manager hooks (`integrate_mcp`,
`reconfigure_mcp_async`, `suspend_mcp`) exist as no-op stubs.

## Decision

`vibe-local-debian` supports MCP servers with the `stdio` transport only:

- servers are local subprocesses declared in `[[mcp_servers]]` (config) or
  session `mcp_servers` options (app-server);
- the wire protocol is newline-delimited JSON-RPC 2.0 over the subprocess
  stdin/stdout, implemented in-repo without the upstream `mcp` SDK or any
  network-capable dependency;
- HTTP and `streamable-http` transports remain unsupported: configuring one
  fails at config validation with an explicit error;
- remote registries, connectors, authorization providers and MCP sampling
  (`sampling_enabled` is read but not honored) stay out of scope;
- tools are exposed as `mcp_<server>_<tool>` through the regular tool manager
  and inherit the existing permission policy like any builtin tool;
- the schema field `mcp_servers` re-enters `VibeConfigSchema` as a
  union-merged list keyed by name.

## Consequences

- The `tests/local` cleanup suites that assert the physical absence of the
  removed remote MCP surfaces are updated: the stdio client lives in
  `vibe/core/mcp/` (not `vibe/core/tools/mcp/`), declares no `mcp==`
  dependency, and performs no remote I/O.
- Fail-closed: a server that fails to start or initialize surfaces as a
  discovery error in `/mcp`; it never crashes the session and never
  re-enables a removed surface.
- Reverting this ADR means deleting `vibe/core/mcp/`, the `mcp_servers`
  schema field and the tool-manager wiring in one change.
