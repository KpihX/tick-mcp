from __future__ import annotations

from tick_mcp.config import HTTP_MCP_PATH, HTTP_PORT
from tick_mcp.main import mcp


def test_main_entrypoint_registers_tools() -> None:
    """The CLI entrypoint must expose a fully registered MCP tool surface."""
    assert len(mcp._tool_manager._tools) > 0


def test_main_entrypoint_applies_http_settings() -> None:
    """The shared FastMCP instance should be ready for streamable HTTP transport."""
    assert mcp.settings.port == HTTP_PORT
    assert mcp.settings.streamable_http_path == HTTP_MCP_PATH
