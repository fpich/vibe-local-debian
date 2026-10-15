"""Local stdio MCP client.

Newline-delimited JSON-RPC 2.0 over the subprocess stdin/stdout, implemented
without the upstream ``mcp`` SDK. Only stdio transport is supported (ADR 0002);
no network I/O happens in this module.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import itertools
import os
from typing import Any

from vibe.core.config.models import MCPStdio

_JSONRPC_VERSION = "2.0"
_PROTOCOL_VERSION = "2024-11-05"
_MAX_LINE_BYTES = 4 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024

_id_counter = itertools.count(1)


class MCPClientError(Exception):
    """Raised when a local stdio MCP server cannot be reached or answers badly."""


@dataclass(slots=True)
class MCPToolDescriptor:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _ServerInfo:
    name: str
    version: str = ""


async def _read_json_line(stream: asyncio.StreamReader, buffer: list[bytes]) -> bytes:
    """Read one newline-delimited JSON-RPC message of arbitrary size.

    ``StreamReader.readline()`` raises once a line exceeds its 64 KiB stream
    buffer; MCP servers routinely send multi-hundred-KiB tool lists, so read
    in bounded chunks until the delimiter instead. Leftover bytes after the
    delimiter are kept in ``buffer`` for the next call.
    """
    pending = buffer[0] if buffer else b""
    while True:
        newline = pending.find(b"\n")
        if newline != -1:
            line = pending[:newline]
            buffer[0] = pending[newline + 1 :]
            return line
        chunk = await stream.read(_READ_CHUNK_BYTES)
        if not chunk:
            buffer[0] = b""
            return pending
        pending += chunk


class StdioMCPClient:
    """One running local MCP subprocess plus its JSON-RPC conversation."""

    def __init__(self, server: MCPStdio) -> None:
        self._server = server
        self._process: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._server_info: _ServerInfo | None = None
        self._tools: tuple[MCPToolDescriptor, ...] = ()
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def server(self) -> MCPStdio:
        return self._server

    @property
    def name(self) -> str:
        return self._server.name

    @property
    def server_info(self) -> _ServerInfo | None:
        return self._server_info

    @property
    def tools(self) -> tuple[MCPToolDescriptor, ...]:
        return self._tools

    async def start(self) -> None:
        """Spawn the subprocess and perform the MCP initialize handshake."""
        if self._process is not None:
            return
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._server.argv(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=self._server.cwd or None,
                env={**os.environ, **self._server.env},
            )
        except (OSError, ValueError) as exc:
            raise MCPClientError(
                f"Failed to start local MCP server '{self.name}': {exc}"
            ) from exc
        self._reader_task = asyncio.create_task(
            self._read_responses(), name=f"mcp-stdio-{self.name}"
        )
        try:
            result = await asyncio.wait_for(
                self._request(
                    "initialize",
                    {
                        "protocolVersion": _PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "vibe-local", "version": "1"},
                    },
                ),
                timeout=self._server.startup_timeout_sec,
            )
            await self._notify("notifications/initialized")
        except (TimeoutError, MCPClientError) as exc:
            await self.stop()
            raise MCPClientError(
                f"MCP server '{self.name}' failed to initialize: {exc}"
            ) from exc
        info = result.get("serverInfo") or {}
        self._server_info = _ServerInfo(
            name=str(info.get("name") or self.name),
            version=str(info.get("version") or ""),
        )
        await self.refresh_tools()

    async def refresh_tools(self) -> None:
        result = await asyncio.wait_for(
            self._request("tools/list", {}), timeout=self._server.tool_timeout_sec
        )
        raw_tools = result.get("tools") or []
        descriptors: list[MCPToolDescriptor] = []
        for raw in raw_tools:
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            input_schema = raw.get("inputSchema")
            descriptors.append(
                MCPToolDescriptor(
                    name=str(raw["name"]),
                    description=str(raw.get("description") or ""),
                    input_schema=(
                        input_schema if isinstance(input_schema, dict) else {}
                    ),
                )
            )
        self._tools = tuple(descriptors)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        try:
            return await asyncio.wait_for(
                self._request(
                    "tools/call", {"name": tool_name, "arguments": arguments}
                ),
                timeout=self._server.tool_timeout_sec,
            )
        except TimeoutError as exc:
            raise MCPClientError(
                f"MCP tool '{self.name}.{tool_name}' timed out after "
                f"{self._server.tool_timeout_sec}s"
            ) from exc

    async def stop(self) -> None:
        """Terminate the subprocess; safe to call more than once."""
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        process = self._process
        self._process = None
        if process is None or process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": _JSONRPC_VERSION, "method": method}
        if params is not None:
            message["params"] = params
        await self._send(message)

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        process = self._process
        if process is None or self._closed:
            raise MCPClientError(f"MCP server '{self.name}' is not running")
        request_id = next(_id_counter)
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[request_id] = future
        await self._send({
            "jsonrpc": _JSONRPC_VERSION,
            "id": request_id,
            "method": method,
            "params": params,
        })
        return await future

    async def _send(self, message: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or self._closed:
            raise MCPClientError(f"MCP server '{self.name}' is not running")
        payload = _dumps(message)
        process.stdin.write(payload + b"\n")
        await process.stdin.drain()

    async def _read_responses(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        leftover: list[bytes] = [b""]
        try:
            while not self._closed:
                line = await _read_json_line(process.stdout, leftover)
                if not line:
                    break
                if len(line) > _MAX_LINE_BYTES:
                    continue
                text = line.strip()
                if not text or text.startswith(b"#"):
                    continue
                self._dispatch_response(_loads(text))
        except asyncio.CancelledError:
            pass
        finally:
            error = MCPClientError(f"MCP server '{self.name}' closed the connection")
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

    def _dispatch_response(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return
        future = self._pending.pop(request_id, None)
        if future is None or future.done():
            return
        if "error" in message:
            error = message["error"] or {}
            future.set_exception(
                MCPClientError(
                    f"MCP server '{self.name}' error: "
                    f"{error.get('message') or error} (code {error.get('code')})"
                )
            )
            return
        future.set_result(message.get("result") or {})


def _dumps(message: dict[str, Any]) -> bytes:
    import json

    return json.dumps(message).encode("utf-8")


def _loads(text: bytes) -> dict[str, Any]:
    import json

    return json.loads(text.decode("utf-8"))


__all__ = ["MCPClientError", "MCPToolDescriptor", "StdioMCPClient"]
