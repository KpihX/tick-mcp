from __future__ import annotations

import tick_mcp.admin.telegram as telegram_admin


def test_dispatch_status(monkeypatch) -> None:
    bot = telegram_admin.TelegramAdminBot(token="dummy", allowed_chat_ids=("1",))
    monkeypatch.setattr(telegram_admin, "status_summary_text", lambda: "status-ok")

    assert bot._dispatch("/status", []) == "status-ok"


def test_dispatch_session_refresh_without_credentials(monkeypatch) -> None:
    bot = telegram_admin.TelegramAdminBot(token="dummy", allowed_chat_ids=("1",))
    monkeypatch.setattr(telegram_admin, "configured_refresh_credentials", lambda: (None, None))

    assert "Missing TICKTICK_USERNAME or TICKTICK_PASSWORD" in bot._dispatch("/session_refresh", [])
