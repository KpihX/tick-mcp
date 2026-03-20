from __future__ import annotations

import anyio

import tick_mcp.http_app as http_app


def test_health_route_exposes_http_transport(monkeypatch) -> None:
    monkeypatch.setattr(http_app.daemon, "read_pid", lambda: 4242)
    monkeypatch.setattr(http_app.daemon, "is_running", lambda pid: pid == 4242)

    response = anyio.run(http_app.health, None)
    payload = response.body
    assert response.status_code == 200
    data = __import__("json").loads(payload)
    assert data["product"] == "tick-mcp"
    assert data["transport"] == "streamable-http"
    assert data["running"] is True
    assert data["pid"] == 4242


def test_admin_status_mentions_ssh_and_telegram(monkeypatch) -> None:
    monkeypatch.setattr(http_app.daemon, "read_pid", lambda: None)

    response = anyio.run(http_app.admin_status, None)
    payload = response.body
    assert response.status_code == 200
    data = __import__("json").loads(payload)
    assert data["product"] == "tick-mcp"
    assert data["admin"]["ssh_admin"]["supported"] is True
    assert data["admin"]["telegram_admin"]["token_env"] == "TELEGRAM_TICK_HOMELAB_TOKEN"
