"""
Shared administrative service layer for tick-mcp.

This module is the single backend for:
  - tick-admin (CLI)
  - Telegram admin commands
  - future authenticated admin HTTP actions
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values, set_key

from ..config import (
    ADMIN_ENV_PATH,
    API_TIMEOUT,
    ENV_API_TOKEN,
    ENV_PASSWORD,
    ENV_SESSION_TOKEN,
    ENV_USERNAME,
    HTTP_FALLBACK_BASE_URL,
    HTTP_MCP_PATH,
    HTTP_PORT,
    HTTP_PUBLIC_BASE_URL,
    SIGNON_PARAMS,
    STATE_DIRECTORY,
    V2_LOGIN_HEADERS,
    V2_SIGNON_URL,
    WEB_ORIGIN,
)


_LOG_DIR = (ADMIN_ENV_PATH.parent if str(ADMIN_ENV_PATH.parent) not in ("", ".") else STATE_DIRECTORY) / "logs"
_LOG_FILE = _LOG_DIR / "ticktick_admin_debug.log"
SESSION_OBTAINED_AT_KEY = f"{ENV_SESSION_TOKEN}_OBTAINED_AT"
SESSION_EXPIRES_AT_KEY = f"{ENV_SESSION_TOKEN}_EXPIRES_AT"
API_EXPIRES_AT_KEY = f"{ENV_API_TOKEN}_EXPIRES_AT"
APPROX_SESSION_TTL = timedelta(days=30)


class AdminRefreshInteractionRequired(RuntimeError):
    """Raised when a session refresh requires MFA or link approval."""


class AdminActionError(RuntimeError):
    """Raised when an admin action fails."""


class _FlushingFileHandler(logging.FileHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def _setup_logger() -> logging.Logger:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("tick_mcp.admin")
    if not log.handlers:
        log.setLevel(logging.DEBUG)
        handler = _FlushingFileHandler(_LOG_FILE, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
        log.addHandler(handler)
    return log


_log = _setup_logger()


@dataclass(slots=True)
class StatusPayload:
    api_token_present: bool
    session_token_present: bool
    api_token_masked: str
    session_token_masked: str
    api_timing: str
    session_timing: str
    env_path: str


def _mask(value: str | None, *, show: int = 6) -> str:
    if not value:
        return "not set"
    if len(value) <= show * 2:
        return "*" * len(value)
    return f"{value[:show]}…{value[-show:]}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_epoch_string(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return str(int(dt.timestamp()))


def _parse_epoch(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(dt: datetime | None) -> str:
    if not dt:
        return "unknown"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _format_remaining(expires_at: datetime | None, *, approximate: bool = False) -> str:
    if not expires_at:
        return "unknown"
    remaining = expires_at - _now_utc()
    if remaining.total_seconds() <= 0:
        return "expired"
    total_seconds = int(remaining.total_seconds())
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    prefix = "≈ " if approximate else ""
    return f"{prefix}{' '.join(parts)}"


def _timing_summary(
    *,
    expires_at: datetime | None,
    obtained_at: datetime | None = None,
    approximate: bool = False,
) -> str:
    segments: list[str] = []
    if obtained_at:
        segments.append(f"obtained {_format_timestamp(obtained_at)}")
    if expires_at:
        segments.append(f"expires {_format_timestamp(expires_at)}")
        segments.append(f"left {_format_remaining(expires_at, approximate=approximate)}")
    return " | ".join(segments) if segments else "no expiration metadata"


def _dotenv_values() -> dict[str, str]:
    return dotenv_values(ADMIN_ENV_PATH) if ADMIN_ENV_PATH.exists() else {}


def _admin_env_view() -> dict[str, str]:
    env = _dotenv_values()
    for key in (
        ENV_API_TOKEN,
        ENV_SESSION_TOKEN,
        ENV_USERNAME,
        ENV_PASSWORD,
        API_EXPIRES_AT_KEY,
        SESSION_OBTAINED_AT_KEY,
        SESSION_EXPIRES_AT_KEY,
    ):
        value = os.environ.get(key)
        if value and not env.get(key):
            env[key] = value
    return env


def _write_env(key: str, value: str) -> None:
    ADMIN_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ADMIN_ENV_PATH.touch(exist_ok=True)
    success, _, _ = set_key(str(ADMIN_ENV_PATH), key, value, quote_mode="never")
    if not success:
        raise AdminActionError(f"Failed to write {key} to {ADMIN_ENV_PATH}")


def _write_optional_env(key: str, value: str | None) -> None:
    if value is None:
        return
    _write_env(key, value)


def _log_request(label: str, method: str, url: str, payload: dict[str, Any], headers: dict[str, str]) -> None:
    _log.debug("=" * 80)
    _log.debug("REQUEST  [%s]  %s %s", label, method.upper(), url)
    _log.debug("  params : %s", json.dumps(SIGNON_PARAMS))
    safe_payload = {k: ("***REDACTED***" if k == "password" else v) for k, v in payload.items()}
    _log.debug("  body   : %s", json.dumps(safe_payload))
    safe_headers = {k: ("***REDACTED***" if "auth" in k.lower() or "cookie" in k.lower() else v) for k, v in headers.items()}
    _log.debug("  headers: %s", json.dumps(safe_headers))


def _log_response(label: str, response: httpx.Response) -> None:
    _log.debug("RESPONSE [%s]  status=%s", label, response.status_code)
    _log.debug("  headers: %s", dict(response.headers))
    try:
        body = response.json()
        if isinstance(body, dict):
            safe_body = {k: ("***REDACTED***" if k in ("token", "password") else v) for k, v in body.items()}
            _log.debug("  body   : %s", json.dumps(safe_body, indent=2))
            _log.debug("  keys   : %s", list(body.keys()))
        else:
            _log.debug("  body   : %s", json.dumps(body))
    except Exception:
        _log.debug("  raw    : %s", response.text[:2000])


def _http_post(label: str, url: str, payload: dict[str, Any]) -> httpx.Response:
    headers = dict(V2_LOGIN_HEADERS)
    _log_request(label, "POST", url, payload, headers)
    response = httpx.post(
        url,
        params=SIGNON_PARAMS,
        json=payload,
        headers=headers,
        timeout=API_TIMEOUT,
    )
    _log_response(label, response)
    return response


def get_status_payload() -> StatusPayload:
    env = _admin_env_view()
    api_expires_at = _parse_epoch(env.get(API_EXPIRES_AT_KEY))
    session_obtained_at = _parse_epoch(env.get(SESSION_OBTAINED_AT_KEY))
    session_expires_at = _parse_epoch(env.get(SESSION_EXPIRES_AT_KEY))
    api_value = env.get(ENV_API_TOKEN)
    session_value = env.get(ENV_SESSION_TOKEN)
    return StatusPayload(
        api_token_present=bool(api_value),
        session_token_present=bool(session_value),
        api_token_masked=_mask(api_value),
        session_token_masked=_mask(session_value),
        api_timing=_timing_summary(expires_at=api_expires_at),
        session_timing=_timing_summary(
            expires_at=session_expires_at,
            obtained_at=session_obtained_at,
            approximate=True,
        ),
        env_path=str(ADMIN_ENV_PATH),
    )


def set_api_token(value: str, *, expires_at: str | None = None) -> dict[str, str]:
    _write_env(ENV_API_TOKEN, value.strip())
    parsed = _parse_iso_datetime(expires_at) if expires_at else None
    _write_optional_env(API_EXPIRES_AT_KEY, _to_epoch_string(parsed) if parsed else None)
    return {
        "key": ENV_API_TOKEN,
        "masked": _mask(value),
        "env_path": str(ADMIN_ENV_PATH),
        "timing": _timing_summary(expires_at=parsed),
    }


def set_session_token(
    value: str,
    *,
    ttl_days: int | None = None,
    expires_at: str | None = None,
) -> dict[str, str]:
    now = _now_utc()
    computed_expires_at = _parse_iso_datetime(expires_at) if expires_at else None
    if ttl_days is not None:
        computed_expires_at = now + timedelta(days=ttl_days)
    _write_env(ENV_SESSION_TOKEN, value.strip())
    _write_env(SESSION_OBTAINED_AT_KEY, _to_epoch_string(now))
    _write_optional_env(
        SESSION_EXPIRES_AT_KEY,
        _to_epoch_string(computed_expires_at) if computed_expires_at else None,
    )
    return {
        "key": ENV_SESSION_TOKEN,
        "masked": _mask(value),
        "env_path": str(ADMIN_ENV_PATH),
        "timing": _timing_summary(
            expires_at=computed_expires_at,
            obtained_at=now,
            approximate=True,
        ),
    }


def refresh_session_token_noninteractive(username: str, password: str) -> dict[str, str]:
    _log.info("=== non-interactive session refresh started for %s ===", username)
    try:
        response = _http_post("signon", V2_SIGNON_URL, {"username": username, "password": password})
    except httpx.ConnectError as exc:
        raise AdminActionError(f"Network error: could not reach {WEB_ORIGIN}") from exc
    if response.status_code != 200:
        raise AdminActionError(f"Login failed ({response.status_code}): {response.text[:300]}")
    data = response.json()
    token = data.get("token")
    if not token:
        expire_time = data.get("expireTime", 0)
        if data.get("authId"):
            if expire_time > 3600:
                raise AdminRefreshInteractionRequired(
                    "TickTick requires email-link device approval. Use SSH + tick-admin session refresh."
                )
            raise AdminRefreshInteractionRequired(
                "TickTick requires MFA code approval. Use SSH + tick-admin session refresh."
            )
        raise AdminActionError(f"Unexpected login response: {data}")
    return set_session_token(token, ttl_days=30)


def get_logs_text(lines: int = 50) -> str:
    if not _LOG_FILE.exists():
        return "No admin log file yet."
    chunk = _LOG_FILE.read_text(encoding="utf-8").splitlines()[-max(1, lines):]
    return "\n".join(chunk) if chunk else "No admin log lines available."


def health_summary() -> str:
    return "\n".join(
        [
            "tick-mcp health",
            f"- public: {HTTP_PUBLIC_BASE_URL}",
            f"- fallback: {HTTP_FALLBACK_BASE_URL}",
            f"- mcp: {HTTP_PUBLIC_BASE_URL}{HTTP_MCP_PATH}",
            f"- local port: {HTTP_PORT}",
        ]
    )


def urls_summary() -> str:
    return "\n".join(
        [
            "tick-mcp URLs",
            f"- public: {HTTP_PUBLIC_BASE_URL}",
            f"- fallback: {HTTP_FALLBACK_BASE_URL}",
            f"- MCP: {HTTP_PUBLIC_BASE_URL}{HTTP_MCP_PATH}",
            f"- admin status: {HTTP_PUBLIC_BASE_URL}/admin/status",
            f"- health: {HTTP_PUBLIC_BASE_URL}/health",
        ]
    )


def status_summary_text() -> str:
    status = get_status_payload()
    return "\n".join(
        [
            "tick-admin status",
            f"- env file: {status.env_path}",
            f"- {ENV_API_TOKEN}: {'set' if status.api_token_present else 'missing'} ({status.api_token_masked})",
            f"  timing: {status.api_timing}",
            f"- {ENV_SESSION_TOKEN}: {'set' if status.session_token_present else 'missing'} ({status.session_token_masked})",
            f"  timing: {status.session_timing}",
        ]
    )


def configured_refresh_credentials() -> tuple[str | None, str | None]:
    env = _admin_env_view()
    return env.get(ENV_USERNAME), env.get(ENV_PASSWORD)
