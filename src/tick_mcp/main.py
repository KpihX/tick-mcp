import os
import sys
import signal
import typer
from rich.console import Console
# Import the public server facade so all @mcp.tool decorators are registered.
from .server import mcp
from . import daemon
from .config import HTTP_HOST, HTTP_PORT, HTTP_MCP_PATH

console = Console(stderr=True)          # ALL CLI output → stderr (stdout = MCP stdio)
app = typer.Typer(
    name="tick-mcp",
    help="TickTick MCP Server — task and notes access via Model Context Protocol.",
    invoke_without_command=True,         # bare `tick-mcp` → serve
)


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context):
    """When called without a subcommand, default to 'serve'."""
    if ctx.invoked_subcommand is None:
        serve()


@app.command()
def serve():
    """Start the TickTick MCP server in stdio mode (blocks until killed)."""
    pid = os.getpid()
    daemon.write_pid(pid)
    console.print(f"[green]TickTick MCP Server starting (PID {pid})...[/green]")
    try:
        mcp.run(transport="stdio")
    finally:
        daemon.clear_pid()


@app.command("serve-http")
def serve_http():
    """Start the TickTick MCP server in streamable HTTP mode."""
    import uvicorn
    from .http_app import app as http_app, ensure_telegram_admin_started

    pid = os.getpid()
    daemon.write_pid(pid)
    console.print(
        f"[green]TickTick MCP HTTP Server starting (PID {pid}) on {HTTP_HOST}:{HTTP_PORT}{HTTP_MCP_PATH}...[/green]"
    )
    try:
        ensure_telegram_admin_started()
        uvicorn.run(http_app, host=HTTP_HOST, port=HTTP_PORT, reload=False)
    finally:
        daemon.clear_pid()


@app.command()
def status():
    """Check whether the MCP server process is currently running."""
    pid = daemon.read_pid()
    if pid and daemon.is_running(pid):
        console.print(f"[green]Running (PID {pid})[/green]")
    else:
        console.print("[red]Stopped — no PID file found.[/red]")
        raise typer.Exit(1)


@app.command()
def stop():
    """Send SIGTERM to the running server via the PID file."""
    pid = daemon.read_pid()
    if not pid or not daemon.is_running(pid):
        console.print("[yellow]Server is not running.[/yellow]")
        raise typer.Exit(1)
    os.kill(pid, signal.SIGTERM)
    daemon.clear_pid()
    console.print(f"[green]Sent SIGTERM to PID {pid}.[/green]")


def main():
    app()


if __name__ == "__main__":
    main()
