from __future__ import annotations

from pathlib import Path

import tick_mcp.admin.service as admin_service


def test_set_session_token_writes_persistent_admin_env(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / "tick-admin.env"
    monkeypatch.setattr(admin_service, "ADMIN_ENV_PATH", env_path)

    result = admin_service.set_session_token("session-123456", ttl_days=30)

    content = env_path.read_text(encoding="utf-8")
    assert "TICKTICK_SESSION_TOKEN=session-123456" in content
    assert "TICKTICK_SESSION_TOKEN_OBTAINED_AT=" in content
    assert "TICKTICK_SESSION_TOKEN_EXPIRES_AT=" in content
    assert result["env_path"] == str(env_path)


def test_status_payload_reads_admin_env(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / "tick-admin.env"
    env_path.write_text(
        "\n".join(
            [
                "TICKTICK_API_TOKEN=api-abcdef123456",
                "TICKTICK_SESSION_TOKEN=session-abcdef123456",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(admin_service, "ADMIN_ENV_PATH", env_path)

    payload = admin_service.get_status_payload()

    assert payload.api_token_present is True
    assert payload.session_token_present is True
    assert payload.env_path == str(env_path)
    assert payload.api_token_masked.startswith("api-ab")
    assert payload.session_token_masked.startswith("sessio")
