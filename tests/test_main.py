from __future__ import annotations

from tick_mcp.main import mcp


def test_main_entrypoint_registers_tools() -> None:
    """The CLI entrypoint must expose a fully registered MCP tool surface."""
    assert len(mcp._tool_manager._tools) > 0
