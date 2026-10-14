"""Process-wide pool of local stdio MCP clients.

The pool owns the running subprocesses, discovers their tools and exposes
each tool as a dynamically-generated ``BaseTool`` subclass named
``mcp_<server>_<tool>`` so the regular tool-manager and permission machinery
apply unchanged (ADR 0002).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Iterator
import re
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from vibe.core.config.models import MCPStdio
from vibe.core.mcp.client import MCPClientError, MCPToolDescriptor, StdioMCPClient
from vibe.core.tools.base import BaseTool, BaseToolConfig, BaseToolState, InvokeContext
from vibe.core.types import ToolStreamEvent


class _MCPToolArgs(BaseModel):
    model_config = ConfigDict(extra="allow")

    arguments: dict[str, Any] = {}


class _MCPToolResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    output: str = ""


class _MCPToolConfig(BaseToolConfig):
    pass


class _MCPToolState(BaseToolState):
    pass


class MCPToolError(Exception):
    """Raised when the MCP tool call returns an ``isError`` payload."""


class MCPClientPool:
    """Owns one ``StdioMCPClient`` per configured local MCP server."""

    def __init__(
        self,
        servers: Callable[[], list[MCPStdio]] | None = None,
        *,
        pool: MCPClientPool | None = None,
    ) -> None:
        if pool is not None:
            self._servers_getter = pool._servers_getter
            self._clients = pool._clients
            self._errors = pool._errors
            self._started = pool._started
            return
        self._servers_getter = servers or (lambda: [])
        self._clients: dict[str, StdioMCPClient] = {}
        self._errors: dict[str, str] = {}
        self._started = False

    @property
    def errors(self) -> dict[str, str]:
        return dict(self._errors)

    @property
    def clients(self) -> tuple[StdioMCPClient, ...]:
        return tuple(self._clients.values())

    def active_servers(self) -> list[MCPStdio]:
        return [client.server for client in self._clients.values()]

    def get_client(self, name: str) -> StdioMCPClient | None:
        return self._clients.get(name)

    async def integrate(self) -> None:
        """Start (or refresh) every configured server; errors stay per-server."""
        servers = {
            server.name: server
            for server in self._servers_getter()
            if isinstance(server, MCPStdio)
        }
        for name in list(self._clients):
            if name not in servers:
                await self._clients.pop(name).stop()
                self._errors.pop(name, None)
        for name, server in servers.items():
            existing = self._clients.get(name)
            if existing is not None and existing.server == server:
                continue
            if existing is not None:
                await existing.stop()
            client = StdioMCPClient(server)
            try:
                await client.start()
            except MCPClientError as exc:
                self._errors[name] = str(exc)
                self._clients.pop(name, None)
            else:
                self._errors.pop(name, None)
                self._clients[name] = client
        self._started = True

    async def stop(self) -> None:
        for client in self._clients.values():
            await client.stop()
        self._clients.clear()

    async def reconfigure(self) -> None:
        await self.integrate()

    def iter_tool_classes(self) -> Iterator[type[BaseTool]]:
        for client in self._clients.values():
            if client.server.disabled:
                continue
            for tool in client.tools:
                if tool.name in client.server.disabled_tools:
                    continue
                yield _build_mcp_tool_class(client.name, tool)

    def clear_errors(self) -> None:
        self._errors.clear()

    def pop_errors(self) -> dict[str, str]:
        errors = self._errors
        self._errors = {}
        return errors


def _snake(value: str) -> str:
    value = re.sub(r"[^0-9a-zA-Z]+", "_", value)
    value = re.sub(r"(?<!^)(?=[A-Z])", "_", value)
    return re.sub(r"_+", "_", value).strip("_").lower()


def _tool_class_name(server_name: str, tool: MCPToolDescriptor) -> str:
    return f"mcp_{_snake(server_name)}__{_snake(tool.name)}"


def _build_mcp_tool_class(server_name: str, tool: MCPToolDescriptor) -> type[BaseTool]:
    class _MCPStdioTool(
        BaseTool[_MCPToolArgs, _MCPToolResult, _MCPToolConfig, _MCPToolState]
    ):
        description: ClassVar[str] = tool.description or f"MCP tool {tool.name}"
        selection_priority: ClassVar[int] = 0

        @classmethod
        def get_name(cls) -> str:
            return f"mcp_{_snake(server_name)}_{_snake(tool.name)}"

        async def run(
            self, args: _MCPToolArgs, ctx: InvokeContext | None = None
        ) -> AsyncGenerator[ToolStreamEvent | _MCPToolResult, None]:
            pool: MCPClientPool | None = ctx.mcp_pool if ctx is not None else None
            client = pool.get_client(server_name) if pool is not None else None
            if client is None:
                yield _MCPToolResult(
                    output=f"MCP server '{server_name}' is not running"
                )
                return
            try:
                result = await client.call_tool(tool.name, args.arguments)
            except MCPClientError as exc:
                yield _MCPToolResult(output=str(exc))
                return
            yield _MCPToolResult(output=_render_result(result))

    return type(_tool_class_name(server_name, tool), (_MCPStdioTool,), {})


def _render_result(result: Any) -> str:
    if not isinstance(result, dict):
        return "" if result is None else str(result)
    parts: list[str] = []
    for content in result.get("content") or []:
        if isinstance(content, dict):
            text = content.get("text")
            if text is not None:
                parts.append(str(text))
    structured = result.get("structuredContent")
    if structured is not None and not parts:
        import json

        parts.append(json.dumps(structured, indent=2))
    if result.get("isError") and parts:
        return f"Tool error: {' '.join(parts)}"
    return "\n".join(parts) if parts else ""


__all__ = ["MCPClientError", "MCPClientPool", "MCPToolError"]
