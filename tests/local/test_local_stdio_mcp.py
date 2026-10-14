"""End-to-end tests for local stdio MCP support (ADR 0002)."""

from __future__ import annotations

import sys
import textwrap

import pytest

from vibe.core.config.models import MCPStdio
from vibe.core.mcp.client import MCPClientError, MCPToolDescriptor, StdioMCPClient
from vibe.core.mcp.pool import MCPClientPool, _build_mcp_tool_class, _MCPToolResult
from vibe.core.tools.base import InvokeContext

_ECHO_SERVER = textwrap.dedent(
    """
    import json
    import sys

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        message = json.loads(line)
        if message.get("method") == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "rea-test", "version": "0.1"},
            }
        elif message.get("method") == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "search",
                        "description": "Search things",
                        "inputSchema": {"type": "object"},
                    }
                ]
            }
        elif message.get("method") == "tools/call":
            result = {
                "content": [{"type": "text", "text": "found 3 items"}],
                "isError": False,
            }
        else:
            result = {}
        sys.stdout.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": message.get("id"), "result": result}
            )
            + "\\n"
        )
        sys.stdout.flush()
    """
)


@pytest.fixture
def server_command(tmp_path):
    script = tmp_path / "rea_mcp_server.py"
    script.write_text(_ECHO_SERVER)
    return [sys.executable, str(script)]


@pytest.mark.asyncio
async def test_stdio_client_handshake_and_tools(server_command) -> None:
    server = MCPStdio(
        name="rea", transport="stdio", command=server_command, startup_timeout_sec=15.0
    )
    client = StdioMCPClient(server)
    await client.start()
    try:
        assert client.server_info is not None
        assert client.server_info.name == "rea-test"
        assert [tool.name for tool in client.tools] == ["search"]
        result = await client.call_tool("search", {"q": "hello"})
        assert result["content"][0]["text"] == "found 3 items"
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_stdio_client_reports_missing_binary() -> None:
    server = MCPStdio(
        name="gone", transport="stdio", command="definitely-not-a-real-binary-xyz"
    )
    client = StdioMCPClient(server)
    with pytest.raises(MCPClientError):
        await client.start()


@pytest.mark.asyncio
async def test_pool_integrates_and_exposes_tool_classes(server_command) -> None:
    server = MCPStdio(name="rea", transport="stdio", command=server_command)
    pool = MCPClientPool(lambda: [server])
    await pool.integrate()
    try:
        classes = list(pool.iter_tool_classes())
        assert len(classes) == 1
        tool_class = classes[0]
        assert tool_class.get_name() == "mcp_rea_search"
        instance = tool_class.from_config(lambda: tool_class._get_tool_config_class()())
        results = [
            item
            async for item in instance.invoke(
                InvokeContext(tool_call_id="t1", mcp_pool=pool), arguments={"q": "x"}
            )
        ]
        assert len(results) == 1
        assert isinstance(results[0], _MCPToolResult)
        assert "found 3 items" in results[0].output
    finally:
        await pool.stop()


@pytest.mark.asyncio
async def test_pool_collects_start_errors_per_server() -> None:
    broken = MCPStdio(
        name="broken", transport="stdio", command="definitely-not-a-real-binary-xyz"
    )
    pool = MCPClientPool(lambda: [broken])
    await pool.integrate()
    assert "broken" in pool.errors
    assert "mcp" in pool.errors["broken"].lower()
    errors = pool.pop_errors()
    assert errors
    assert not pool.errors


@pytest.mark.asyncio
async def test_pool_respects_disabled_tools(server_command) -> None:
    server = MCPStdio(
        name="rea", transport="stdio", command=server_command, disabled_tools=["search"]
    )
    pool = MCPClientPool(lambda: [server])
    await pool.integrate()
    try:
        assert list(pool.iter_tool_classes()) == []
    finally:
        await pool.stop()


def test_mcp_tool_class_names_are_normalized() -> None:
    tool = MCPToolDescriptor(name="Weird-Name", description="x")
    tool_class = _build_mcp_tool_class("my server", tool)
    assert tool_class.get_name() == "mcp_my_server_weird_name"


def test_schema_rejects_http_transport() -> None:
    from vibe.core.config import VibeConfigSchema

    field = VibeConfigSchema.model_fields["mcp_servers"]
    assert field is not None
    annotation = str(field.annotation)
    assert "MCPHttp" in annotation


@pytest.mark.asyncio
async def test_render_result_flattens_content() -> None:
    from vibe.core.mcp.pool import _render_result

    payload = {
        "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    }
    assert _render_result(payload) == "a\nb"
    assert _render_result({"isError": True, "content": [{"text": "boom"}]}) == (
        "Tool error: boom"
    )
    assert _render_result(None) == ""
    assert _render_result("plain") == "plain"
