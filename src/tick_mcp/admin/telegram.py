"""
Telegram admin bridge for tick-mcp.

Runs as an in-process background poller inside the HTTP service so operational
actions can affect the live server directly.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import httpx

from .service import (
    AdminActionError,
    AdminRefreshInteractionRequired,
    configured_refresh_credentials,
    get_logs_text,
    health_summary,
    refresh_session_token_noninteractive,
    set_api_token,
    set_session_token,
    status_summary_text,
    admin_help_text,
    urls_summary,
)
from ..config import TELEGRAM_CHAT_IDS, TELEGRAM_TICK_HOMELAB_TOKEN


_log = logging.getLogger("tick_mcp.telegram_admin")
_poller_started = False
_restart_callback: Callable[[], None] | None = None
_poller_thread: threading.Thread | None = None
_poller_state: dict[str, object | None] = {
    "started_at": None,
    "last_poll_at": None,
    "last_success_at": None,
    "last_update_id": None,
    "last_chat_id": None,
    "last_command": None,
    "last_reply_preview": None,
    "last_error": None,
}


class TelegramAdminBot:
    def __init__(self, token: str, allowed_chat_ids: tuple[str, ...]) -> None:
        self.token = token
        self.allowed_chat_ids = {str(chat_id) for chat_id in allowed_chat_ids}
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0

    def run_forever(self) -> None:
        _poller_state["started_at"] = int(time.time())
        _log.info("Telegram admin poller started for %d allowed chats.", len(self.allowed_chat_ids))
        with httpx.Client(timeout=35.0) as client:
            while True:
                try:
                    _poller_state["last_poll_at"] = int(time.time())
                    response = client.get(
                        f"{self.base_url}/getUpdates",
                        params={
                            "timeout": 25,
                            "offset": self.offset,
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    _poller_state["last_success_at"] = int(time.time())
                    _poller_state["last_error"] = None
                    for update in payload.get("result", []):
                        self.offset = max(self.offset, int(update["update_id"]) + 1)
                        _poller_state["last_update_id"] = int(update["update_id"])
                        self._handle_update(client, update)
                except Exception as exc:  # noqa: BLE001
                    _poller_state["last_error"] = str(exc)
                    _log.exception("Telegram poll loop error: %s", exc)
                    time.sleep(5)

    def _handle_update(self, client: httpx.Client, update: dict) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        text = (message.get("text") or "").strip()
        _poller_state["last_chat_id"] = chat_id or None
        if not text.startswith("/"):
            return
        if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
            _log.warning("Rejected Telegram command from unauthorized chat %s", chat_id)
            self._send_message(client, chat_id, "Unauthorized chat.")
            return

        command, *args = text.split()
        command = command.split("@", 1)[0].lower()
        _poller_state["last_command"] = command
        _log.info("Telegram command received: chat=%s command=%s args=%s", chat_id, command, args)
        try:
            reply = self._dispatch(command, args)
        except Exception as exc:  # noqa: BLE001
            _log.exception("Telegram command failed: %s", exc)
            reply = f"Command failed: {exc}"
        _poller_state["last_reply_preview"] = reply[:120]
        self._send_message(client, chat_id, reply)
        _log.info("Telegram reply sent: chat=%s preview=%r", chat_id, reply[:120])

    def _dispatch(self, command: str, args: list[str]) -> str:
        if command in {"/start", "/help"}:
            return admin_help_text()
        if command == "/status":
            return status_summary_text()
        if command == "/health":
            return health_summary()
        if command == "/urls":
            return urls_summary()
        if command == "/logs":
            lines = int(args[0]) if args else 40
            return get_logs_text(lines)
        if command == "/api_token_set":
            if not args:
                return "Usage: /api_token_set <token> [expires_at_iso]"
            result = set_api_token(args[0], expires_at=args[1] if len(args) > 1 else None)
            return f"{result['key']} updated\nmask: {result['masked']}\n{result['timing']}"
        if command == "/session_set":
            if not args:
                return "Usage: /session_set <token> [ttl_days]"
            ttl_days = int(args[1]) if len(args) > 1 else 30
            result = set_session_token(args[0], ttl_days=ttl_days)
            return f"{result['key']} updated\nmask: {result['masked']}\n{result['timing']}"
        if command == "/session_refresh":
            username, password = configured_refresh_credentials()
            if not username or not password:
                return "Missing TICKTICK_USERNAME or TICKTICK_PASSWORD in admin env."
            try:
                result = refresh_session_token_noninteractive(username, password)
            except AdminRefreshInteractionRequired as exc:
                return str(exc)
            return f"{result['key']} refreshed\nmask: {result['masked']}\n{result['timing']}"
        if command == "/restart":
            if _restart_callback is None:
                return "Restart callback is not configured."
            threading.Thread(target=_restart_callback, daemon=True).start()
            return "tick-mcp restart requested."
        return "Unknown command. Use /help."

    def _send_message(self, client: httpx.Client, chat_id: str, text: str) -> None:
        client.post(
            f"{self.base_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text[:4000],
            },
        ).raise_for_status()


def start_telegram_admin(restart_callback: Callable[[], None]) -> None:
    global _poller_started, _restart_callback, _poller_thread
    if _poller_started:
        return
    if not TELEGRAM_TICK_HOMELAB_TOKEN:
        _log.info("Telegram admin disabled: token missing.")
        return
    if not TELEGRAM_CHAT_IDS:
        _log.warning("Telegram admin disabled: allowed chat IDs missing.")
        return
    _restart_callback = restart_callback
    bot = TelegramAdminBot(
        token=TELEGRAM_TICK_HOMELAB_TOKEN,
        allowed_chat_ids=TELEGRAM_CHAT_IDS,
    )
    thread = threading.Thread(target=bot.run_forever, daemon=True, name="tick-mcp-telegram-admin")
    thread.start()
    _poller_thread = thread
    _poller_started = True


def telegram_admin_enabled() -> bool:
    return bool(TELEGRAM_TICK_HOMELAB_TOKEN and TELEGRAM_CHAT_IDS)


def telegram_admin_runtime_status() -> dict[str, object | None]:
    return {
        "enabled": telegram_admin_enabled(),
        "started": _poller_started,
        "thread_alive": bool(_poller_thread and _poller_thread.is_alive()),
        "allowed_chat_count": len(TELEGRAM_CHAT_IDS),
        "allowed_chat_ids": TELEGRAM_CHAT_IDS,
        **_poller_state,
    }
