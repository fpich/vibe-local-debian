"""Local stdio MCP support (ADR 0002)."""

from __future__ import annotations

from vibe.core.mcp.client import MCPClientError, MCPToolDescriptor, StdioMCPClient
from vibe.core.mcp.pool import MCPClientPool

__all__ = ["MCPClientError", "MCPClientPool", "MCPToolDescriptor", "StdioMCPClient"]
