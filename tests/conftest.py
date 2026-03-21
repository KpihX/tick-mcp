"""
Shared fixtures for the TickTick MCP test suite.

Fixture hierarchy:
  - Unit tests   → mock everything, no I/O.
  - Integration  → real login-shell environment, real .env, real os.environ (no network).
  - Live tests   → hit the actual TickTick API (opt-in via `pytest -m live`).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tick_mcp.config import ENV_API_TOKEN, ENV_SESSION_TOKEN, ENV_USERNAME, ENV_PASSWORD


# ─── Paths ────────────────────────────────────────────────────────────────────
PACKAGE_DIR = Path(__file__).resolve().parent.parent / "src" / "tick_mcp"
DOTENV_PATH = PACKAGE_DIR / ".env"


# ═══════════════════════════════════════════════════════════════════════════════
#  Unit-level fixtures (isolated, no side-effects)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def clean_env(monkeypatch):
    """
    Wipe all TICKTICK_* env vars for isolated tests.
    Restores originals automatically after the test.
    """
    tt_keys = [k for k in os.environ if k.startswith("TICKTICK_")]
    for k in tt_keys:
        monkeypatch.delenv(k, raising=False)
    return tt_keys


@pytest.fixture()
def fake_env(monkeypatch):
    """
    Inject known fake values so Tier 1 always succeeds.
    Returns a dict of the injected values.
    """
    tokens = {
        ENV_API_TOKEN: "fake_api_token_0123456789abcdef",
        ENV_SESSION_TOKEN: "fake_session_token_abcdef0123456789",
        ENV_USERNAME: "test@example.com",
        ENV_PASSWORD: "hunter2",
    }
    for k, v in tokens.items():
        monkeypatch.setenv(k, v)
    return tokens


@pytest.fixture()
def no_bwenv(monkeypatch):
    """Disable Tier 2 login-shell reads for isolated unit tests."""
    import tick_mcp.config as config_mod

    monkeypatch.setattr(config_mod, "_shell_read_env", lambda _key: None)


@pytest.fixture()
def mock_bwenv(monkeypatch):
    """Keep a named fixture for tests that explicitly stub login-shell reads."""
    import tick_mcp.config as config_mod

    monkeypatch.setattr(config_mod, "_shell_read_env", lambda _key: None)


# ═══════════════════════════════════════════════════════════════════════════════
#  Integration-level fixtures (real system, real login-shell environment)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def require_bwenv():
    """Skip the test if zsh is not available for login-shell resolution."""
    if shutil.which("zsh") is None:
        pytest.skip("zsh is not installed — skipping integration test")


@pytest.fixture()
def require_api_token():
    """Skip if API token is not available from any source."""
    from tick_mcp.config import _shell_read_env
    val = os.environ.get(ENV_API_TOKEN) or _shell_read_env(ENV_API_TOKEN)
    if not val:
        pytest.skip(f"{ENV_API_TOKEN} not available — skipping")
    return val


@pytest.fixture()
def require_session_token():
    """Skip if session token is not available from any source."""
    from tick_mcp.config import _shell_read_env
    val = os.environ.get(ENV_SESSION_TOKEN) or _shell_read_env(ENV_SESSION_TOKEN)
    if not val:
        pytest.skip(f"{ENV_SESSION_TOKEN} not available — skipping")
    return val


# ═══════════════════════════════════════════════════════════════════════════════
#  .env backup/restore (for tests that modify .env)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def backup_dotenv():
    """
    Back up .env before the test and restore it after.
    Safe for tests that call _write_to_dotenv().
    """
    backup = DOTENV_PATH.with_suffix(".env.bak")
    had_file = DOTENV_PATH.exists()
    if had_file:
        shutil.copy2(DOTENV_PATH, backup)
    yield DOTENV_PATH
    if had_file:
        shutil.copy2(backup, DOTENV_PATH)
        backup.unlink(missing_ok=True)
    elif DOTENV_PATH.exists():
        DOTENV_PATH.unlink()
