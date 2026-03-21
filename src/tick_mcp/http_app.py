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
from .admin.service import (
    admin_help_text,
    configured_refresh_credentials,
    get_logs_text,
    refresh_session_token_noninteractive,
    set_api_token,
    set_password,
    set_session_token,
    set_username,
    status_summary_text,
    unset_api_token,
    unset_password,
    unset_session_token,
    unset_username,
)
from .config import (
    APP_VERSION,
    ENV_API_TOKEN,
    ENV_PASSWORD,
    ENV_SESSION_TOKEN,
    ENV_TELEGRAM_CHAT_IDS,
    ENV_TELEGRAM_TICK_HOMELAB_TOKEN,
    ENV_USERNAME,
    HTTP_FALLBACK_BASE_URL,
    HTTP_MCP_PATH,
    HTTP_PORT,
    HTTP_PUBLIC_BASE_URL,
    has_v2_auth_in_environment,
)
from .server import mcp
from .admin.telegram import (
    start_telegram_admin,
    telegram_admin_enabled,
    telegram_admin_runtime_status,
)


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


def _auth_probe_payload() -> dict[str, object]:
    api_present = bool(os.environ.get(ENV_API_TOKEN))
    session_present = bool(os.environ.get(ENV_SESSION_TOKEN))
    username_present = bool(os.environ.get(ENV_USERNAME))
    password_present = bool(os.environ.get(ENV_PASSWORD))
    return {
        "api_token_env": ENV_API_TOKEN,
        "api_token_present": api_present,
        "session_token_env": ENV_SESSION_TOKEN,
        "session_token_present": session_present,
        "username_env": ENV_USERNAME,
        "username_present": username_present,
        "password_env": ENV_PASSWORD,
        "password_present": password_present,
        "v2_available": has_v2_auth_in_environment(),
    }


async def health(_request) -> JSONResponse:
    payload = _base_payload()
    payload["auth"] = _auth_probe_payload()
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
            "supported": True,
            "token_env": ENV_TELEGRAM_TICK_HOMELAB_TOKEN,
            "allowed_chat_ids_env": ENV_TELEGRAM_CHAT_IDS,
            "configured": bool(os.environ.get(ENV_TELEGRAM_TICK_HOMELAB_TOKEN)),
            "enabled": telegram_admin_enabled(),
            "runtime": telegram_admin_runtime_status(),
        },
        "auth_probe": _auth_probe_payload(),
        "status_summary": status_summary_text(),
    }
    payload["routes"] = {
        "health": "/health",
        "admin_status": "/admin/status",
        "admin_help": "/admin/help",
        "admin_logs": "/admin/logs?lines=40",
        "mcp": HTTP_MCP_PATH,
    }
    return JSONResponse(payload)


async def admin_help(_request) -> JSONResponse:
    payload = _base_payload()
    payload["help"] = {
        "text": admin_help_text(),
        "routes": {
            "health": "/health",
            "admin_status": "/admin/status",
            "admin_help": "/admin/help",
            "admin_logs": "/admin/logs?lines=40",
            "mcp": HTTP_MCP_PATH,
        },
    }
    return JSONResponse(payload)


async def admin_logs(request) -> JSONResponse:
    lines = int(request.query_params.get("lines", "40"))
    return JSONResponse({"text": get_logs_text(lines), "lines": lines})


async def admin_api_set(request) -> JSONResponse:
    body = await request.json()
    result = set_api_token(body.get("value", ""), expires_at=body.get("expires_at"))
    return JSONResponse({"ok": True, "action": "api.set", **result})


async def admin_api_unset(_request) -> JSONResponse:
    result = unset_api_token()
    return JSONResponse({"ok": True, "action": "api.unset", **result})


async def admin_session_set(request) -> JSONResponse:
    body = await request.json()
    result = set_session_token(
        body.get("value", ""),
        ttl_days=body.get("ttl_days"),
        expires_at=body.get("expires_at"),
    )
    return JSONResponse({"ok": True, "action": "session.set", **result})


async def admin_session_unset(_request) -> JSONResponse:
    result = unset_session_token()
    return JSONResponse({"ok": True, "action": "session.unset", **result})


async def admin_session_refresh(_request) -> JSONResponse:
    username, password = configured_refresh_credentials()
    if not username or not password:
        return JSONResponse(
            {
                "ok": False,
                "action": "session.refresh",
                "error": "Missing TICKTICK_USERNAME or TICKTICK_PASSWORD in admin sources.",
            },
            status_code=400,
        )
    result = refresh_session_token_noninteractive(username, password)
    return JSONResponse({"ok": True, "action": "session.refresh", **result})


async def admin_user_set(request) -> JSONResponse:
    body = await request.json()
    result = set_username(body.get("value", ""))
    return JSONResponse({"ok": True, "action": "user.set", **result})


async def admin_user_unset(_request) -> JSONResponse:
    result = unset_username()
    return JSONResponse({"ok": True, "action": "user.unset", **result})


async def admin_pass_set(request) -> JSONResponse:
    body = await request.json()
    result = set_password(body.get("value", ""))
    return JSONResponse({"ok": True, "action": "pass.set", **result})


async def admin_pass_unset(_request) -> JSONResponse:
    result = unset_password()
    return JSONResponse({"ok": True, "action": "pass.unset", **result})


def _restart_process() -> None:
    time.sleep(1.0)
    os._exit(0)


def ensure_telegram_admin_started() -> None:
    start_telegram_admin(_restart_process)


app = mcp.streamable_http_app()
app.add_event_handler("startup", ensure_telegram_admin_started)
app.router.routes.insert(0, Route("/health", health))
app.router.routes.insert(1, Route("/admin/status", admin_status))
app.router.routes.insert(2, Route("/admin/help", admin_help))
app.router.routes.insert(3, Route("/admin/logs", admin_logs))
app.router.routes.insert(4, Route("/admin/api/set", admin_api_set, methods=["POST"]))
app.router.routes.insert(5, Route("/admin/api/unset", admin_api_unset, methods=["POST"]))
app.router.routes.insert(6, Route("/admin/session/set", admin_session_set, methods=["POST"]))
app.router.routes.insert(7, Route("/admin/session/unset", admin_session_unset, methods=["POST"]))
app.router.routes.insert(8, Route("/admin/session/refresh", admin_session_refresh, methods=["POST"]))
app.router.routes.insert(9, Route("/admin/user/set", admin_user_set, methods=["POST"]))
app.router.routes.insert(10, Route("/admin/user/unset", admin_user_unset, methods=["POST"]))
app.router.routes.insert(11, Route("/admin/pass/set", admin_pass_set, methods=["POST"]))
app.router.routes.insert(12, Route("/admin/pass/unset", admin_pass_unset, methods=["POST"]))
