from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

import tick_mcp.admin.service as admin_service
import tick_mcp.admin.cli as cli


runner = CliRunner()


def test_status_shows_session_remaining_time(monkeypatch, tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
    obtained = int(now.timestamp())
    expires = int((now + timedelta(days=10, hours=2)).timestamp())
    dotenv_path.write_text(
        "\n".join(
            [
                "TICKTICK_API_TOKEN=api_token_value",
                "TICKTICK_SESSION_TOKEN=session_token_value",
                f"TICKTICK_SESSION_TOKEN_OBTAINED_AT={obtained}",
                f"TICKTICK_SESSION_TOKEN_EXPIRES_AT={expires}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_DOTENV_PATH", dotenv_path)
    monkeypatch.setattr(admin_service, "ADMIN_ENV_PATH", dotenv_path)
    monkeypatch.setattr(cli, "_now_utc", lambda: now)
    monkeypatch.setattr(admin_service, "_now_utc", lambda: now)

    result = runner.invoke(cli.app, ["status"])

    assert result.exit_code == 0
    assert "TICKTICK_SESSION_TOKEN" in result.stdout
    assert "obtained 2026-03-20 12:00" in result.stdout
    assert "UTC | expires 2026-03-30" in result.stdout
    assert "14:00 UTC" in result.stdout
    assert "10d" in result.stdout
    assert "2h" in result.stdout


def test_token_set_can_store_optional_expiration(monkeypatch, tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    monkeypatch.setattr(cli, "_DOTENV_PATH", dotenv_path)
    monkeypatch.setattr(admin_service, "ADMIN_ENV_PATH", dotenv_path)

    result = runner.invoke(
        cli.app,
        [
            "token",
            "set",
            "api_value_123",
            "--expires-at",
            "2026-04-01T12:30:00+00:00",
        ],
    )

    assert result.exit_code == 0
    text = dotenv_path.read_text(encoding="utf-8")
    assert "TICKTICK_API_TOKEN=api_value_123" in text
    assert "TICKTICK_API_TOKEN_EXPIRES_AT=1775046600" in text


def test_session_set_can_store_ttl_metadata(monkeypatch, tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(cli, "_DOTENV_PATH", dotenv_path)
    monkeypatch.setattr(admin_service, "ADMIN_ENV_PATH", dotenv_path)
    monkeypatch.setattr(cli, "_now_utc", lambda: now)
    monkeypatch.setattr(admin_service, "_now_utc", lambda: now)

    result = runner.invoke(
        cli.app,
        ["session", "set", "session_value_123", "--ttl-days", "7"],
    )

    assert result.exit_code == 0
    text = dotenv_path.read_text(encoding="utf-8")
    assert "TICKTICK_SESSION_TOKEN=session_value_123" in text
    assert f"TICKTICK_SESSION_TOKEN_OBTAINED_AT={int(now.timestamp())}" in text
    assert f"TICKTICK_SESSION_TOKEN_EXPIRES_AT={int((now + timedelta(days=7)).timestamp())}" in text


def test_session_refresh_writes_token_and_approximate_expiration(monkeypatch, tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(cli, "_DOTENV_PATH", dotenv_path)
    monkeypatch.setattr(admin_service, "ADMIN_ENV_PATH", dotenv_path)
    monkeypatch.setattr(cli, "_now_utc", lambda: now)
    monkeypatch.setattr(admin_service, "_now_utc", lambda: now)
    monkeypatch.setattr(cli, "_v2_login", lambda username, password: "fresh_session_token")
    monkeypatch.setattr(cli.typer, "prompt", lambda *_args, **_kwargs: "secret-password")

    result = runner.invoke(cli.app, ["session", "refresh", "--username", "me@example.com"])

    assert result.exit_code == 0
    text = dotenv_path.read_text(encoding="utf-8")
    assert "TICKTICK_SESSION_TOKEN=fresh_session_token" in text
    assert f"TICKTICK_SESSION_TOKEN_OBTAINED_AT={int(now.timestamp())}" in text
    assert f"TICKTICK_SESSION_TOKEN_EXPIRES_AT={int((now + timedelta(days=30)).timestamp())}" in text
    assert "Approximate expiration: 2026-04-19 12:00 UTC" in result.stdout
