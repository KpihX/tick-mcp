"""
HTTP surface for tick-mcp.

This app exposes:
  - `/health`        : readiness and deployment probe
  - `/admin/status`  : operator-oriented metadata for future Telegram/admin flows
  - `/mcp`           : streamable HTTP MCP transport
"""
from __future__ import annotations

import os
import threading
import time

from starlette.responses import JSONResponse
from starlette.routing import Route

from . import daemon
from .admin.service import status_summary_text
from .config import (
    APP_VERSION,
    ENV_API_TOKEN,
    ENV_SESSION_TOKEN,
    ENV_TELEGRAM_CHAT_IDS,
    ENV_TELEGRAM_TICK_HOMELAB_TOKEN,
    HTTP_FALLBACK_BASE_URL,
    HTTP_MCP_PATH,
    HTTP_PORT,
    HTTP_PUBLIC_BASE_URL,
    has_v2_auth_in_environment,
)
from .server import mcp
from .admin.telegram import start_telegram_admin, telegram_admin_enabled


def _base_payload() -> dict[str, object]:
    pid = daemon.read_pid()
    running = bool(pid and daemon.is_running(pid))
    return {
        "ok": True,
        "product": "tick-mcp",
        "service": "TickTick MCP transport bridge",
        "version": APP_VERSION,
        "transport": "streamable-http",
        "mcp_path": HTTP_MCP_PATH,
        "public_base_url": HTTP_PUBLIC_BASE_URL,
        "fallback_base_url": HTTP_FALLBACK_BASE_URL,
        "listen_port": HTTP_PORT,
        "pid": pid,
        "running": running,
    }


async def health(_request) -> JSONResponse:
    payload = _base_payload()
    payload["auth"] = {
        "api_token_env": ENV_API_TOKEN,
        "session_token_env": ENV_SESSION_TOKEN,
        "v2_available": has_v2_auth_in_environment(),
    }
    return JSONResponse(payload)


async def admin_status(_request) -> JSONResponse:
    payload = _base_payload()
    payload["admin"] = {
        "ssh_admin": {
            "supported": True,
            "examples": [
                "docker compose exec -T tick-mcp tick-admin status",
                "docker compose logs --tail=100 tick-mcp",
            ],
        },
        "telegram_admin": {
            "planned": False,
            "token_env": ENV_TELEGRAM_TICK_HOMELAB_TOKEN,
            "allowed_chat_ids_env": ENV_TELEGRAM_CHAT_IDS,
            "configured": bool(os.environ.get(ENV_TELEGRAM_TICK_HOMELAB_TOKEN)),
            "enabled": telegram_admin_enabled(),
        },
        "status_summary": status_summary_text(),
    }
    payload["routes"] = {
        "health": "/health",
        "admin_status": "/admin/status",
        "mcp": HTTP_MCP_PATH,
    }
    return JSONResponse(payload)


def _restart_process() -> None:
    time.sleep(1.0)
    os._exit(0)


app = mcp.streamable_http_app()
app.add_event_handler("startup", lambda: start_telegram_admin(_restart_process))
app.router.routes.insert(0, Route("/health", health))
app.router.routes.insert(1, Route("/admin/status", admin_status))
