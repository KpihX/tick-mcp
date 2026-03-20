"""
Configuration for the TickTick MCP Server.

━━━ Authentication overview ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

V1 — Official Open API  (TICKTICK_API_TOKEN)  [REQUIRED]
  Base URL : https://api.ticktick.com/open/v1
  Docs     : https://developer.ticktick.com/docs#/openapi
  Auth     : Bearer token in Authorization header
  Scope    : Tasks + Projects CRUD only
  Stable   : Yes — versioned, officially maintained

V2 — Unofficial Web API  [OPTIONAL — unlocks most features]
  Base URL : https://api.ticktick.com/api/v2
  Auth     : Session cookie `t=<token>` + X-Device header
  Scope    : Full — tags, habits, focus/pomodoro, folders, columns,
             batch ops, completed/deleted tasks, sync, user stats
  Stable   : Fragile — reverse-engineered from the web app, no versioning.
             Session token typically expires after ~30 days.

━━━ Secrets loading order (2-tier fallback) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Tier 1 — .env file in this package + inherited os.environ.
            When bw-env is active, os.environ already contains all secrets
            (injected by load.sh via .zshrc at shell startup).

  Tier 2 — If tokens are missing from os.environ:
            1. Run `bw-env restart` (triggers a Zenity password popup if locked).
            2. Wait a configurable delay for the daemon to sync.
            3. Spawn a login shell (`zsh -l -c ...`) to re-read the freshly
               injected env vars — respecting bw-env's public API only.
            4. If still missing → raise SecretsUnavailableError with diagnostics.

  For TICKTICK_SESSION_TOKEN: values resolved from Tier 2 are written back
  to .env (local cache) so subsequent cold starts don't need the vault.
  TICKTICK_API_TOKEN is NEVER written to .env (sensitive — vault only).

  If bw-env is not installed (command not found) → Tier 2 is a silent no-op.

See .env.example for the full list of variables and step-by-step instructions.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
import yaml
from pathlib import Path
from functools import lru_cache
from dotenv import load_dotenv

# ─── Paths ────────────────────────────────────────────────────────────────────
_PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = _PACKAGE_DIR / "config.yaml"
_DOTENV_PATH = _PACKAGE_DIR / ".env"

# ─── Logging ──────────────────────────────────────────────────────────────────
_log = logging.getLogger("k_tick_mcp.config")

# ─── .env loading ─────────────────────────────────────────────────────────────
# override=True: values from .env overwrite any already-set os.environ entries.
# If .env doesn't exist this is a no-op, falling back to plain os.environ.
load_dotenv(_DOTENV_PATH, override=True)


@lru_cache(maxsize=1)
def load_config(config_path=CONFIG_PATH) -> dict:
    """Load configuration from YAML. Cached to hit disk only once per process."""
    if not config_path.exists():
        return {}
    with open(config_path, "r") as f:
        try:
            return yaml.safe_load(f) or {}
        except yaml.YAMLError:
            return {}


# ─── Global typed constants ───────────────────────────────────────────────────
_config = load_config()
_api = _config.get("api", {})

# ── URLs ──────────────────────────────────────────────────────────────────────
API_V1_BASE_URL: str = _api.get("v1_base_url", "https://api.ticktick.com/open/v1")
API_V2_BASE_URL: str = _api.get("v2_base_url", "https://api.ticktick.com/api/v2")
WEB_ORIGIN: str = _api.get("web_origin", "https://ticktick.com")
# Kept for backward compatibility
API_BASE_URL: str = API_V1_BASE_URL

# V2 login endpoints (derived from base URL + sub-paths)
V2_SIGNON_URL: str = f"{API_V2_BASE_URL}{_api.get('v2_signon_path', '/user/signon')}"
V2_MFA_VERIFY_URL: str = f"{API_V2_BASE_URL}{_api.get('v2_mfa_verify_path', '/user/sign/mfa/code/verify')}"
# Signon query parameters
SIGNON_PARAMS: dict[str, str] = _api.get("signon_params", {"wc": "true", "remember": "true"})

# ── HTTP headers ──────────────────────────────────────────────────────────────
API_TIMEOUT: int = _api.get("timeout", 15)
USER_AGENT: str = _api.get("user_agent", "Mozilla/5.0 (X11; Linux x86_64; rv:145.0) Gecko/20100101 Firefox/145.0")
SESSION_COOKIE_NAME: str = _api.get("session_cookie_name", "t")

SERVER_NAME: str = _config.get("server", {}).get("name", "TickTick-MCP")
STATE_DIRECTORY: Path = Path(
    _config.get("server", {}).get("state_directory", "~/.mcps/ticktick")
).expanduser()

# ── V2 device fingerprint (X-Device header) ──────────────────────────────────
_device = _api.get("device", {})
V2_DEVICE_ID: str = _device.get("id", "6790a0b0c1d2e3f4a5b6c7d8")
V2_DEVICE_HEADER: str = (
    '{"platform":"%(platform)s","os":"%(os)s","device":"%(browser)s",'
    '"name":"","version":%(version)d,"id":"%(id)s",'
    '"channel":"website","campaign":"","websocket":""}'
) % {
    "platform": _device.get("platform", "web"),
    "os": _device.get("os", "Linux x86_64"),
    "browser": _device.get("browser", "Firefox 145.0"),
    "version": _device.get("version", 8006),
    "id": V2_DEVICE_ID,
}

# Prebuilt headers dict for V2 login requests (shared by client.py & cli.py)
V2_LOGIN_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "User-Agent": USER_AGENT,
    "X-Device": V2_DEVICE_HEADER,
    "Origin": WEB_ORIGIN,
    "Referer": f"{WEB_ORIGIN}/",
}

# ── Environment variable names (single source of truth) ──────────────────────
_env_vars = _config.get("env_vars", {})
ENV_API_TOKEN: str = _env_vars.get("api_token", "TICKTICK_API_TOKEN")
ENV_SESSION_TOKEN: str = _env_vars.get("session_token", "TICKTICK_SESSION_TOKEN")
ENV_USERNAME: str = _env_vars.get("username", "TICKTICK_USERNAME")
ENV_PASSWORD: str = _env_vars.get("password", "TICKTICK_PASSWORD")

# ─── Secrets manager fallback (bw-env) ───────────────────────────────────────
_secrets_cfg = _config.get("secrets", {})
_BWENV_CMD: str = _secrets_cfg.get("bwenv_command", "bw-env")
_SHELL: str = _secrets_cfg.get("shell", "zsh")
_RESTART_WAIT: int = _secrets_cfg.get("restart_wait", 20)

# Keys that bw-env is expected to provide for this MCP.
_MANAGED_KEYS: tuple[str, ...] = (ENV_API_TOKEN, ENV_SESSION_TOKEN)


# ═══════════════════════════════════════════════════════════════════════════════
#  Custom Error Classes
# ═══════════════════════════════════════════════════════════════════════════════

class SecretsUnavailableError(RuntimeError):
    """
    Raised when a required secret cannot be resolved from any source.

    Carries structured diagnostics: which key, what was tried, and what the
    user should check.
    """

    def __init__(self, key: str, *, tried: list[str], hints: list[str]) -> None:
        self.key = key
        self.tried = tried
        self.hints = hints
        bullet = "\n  • "
        msg = (
            f"{key} is not available.\n"
            f"\nResolution steps attempted:{bullet}{bullet.join(tried)}"
            f"\n\nPossible causes:{bullet}{bullet.join(hints)}"
        )
        super().__init__(msg)


class SessionTokenExpiredError(RuntimeError):
    """
    Raised when the V2 session token is confirmed stale (401) and no fresh
    value could be obtained from the vault.
    """

    def __init__(self, *, tried: list[str]) -> None:
        bullet = "\n  • "
        msg = (
            f"{ENV_SESSION_TOKEN} has expired and no fresh value was found.\n"
            f"\nRefresh steps attempted:{bullet}{bullet.join(tried)}"
            "\n\nTo fix:\n"
            "  1. Log into TickTick in your browser and copy the new session cookie.\n"
            "  2. Update the value in your Vaultwarden vault (global_env item).\n"
            "  3. Wait ≤5 min for bw-env daemon to sync, or run: bw-env sync\n"
            "  4. Or set it directly: ticktick-admin session set <token>"
        )
        super().__init__(msg)


# ═══════════════════════════════════════════════════════════════════════════════
#  Tier 2: bw-env interaction (encapsulated — CLI only, no internal files)
# ═══════════════════════════════════════════════════════════════════════════════

def _bwenv_available() -> bool:
    """Check if the bw-env command is installed (on PATH)."""
    return shutil.which(_BWENV_CMD) is not None


def _shell_read_env(key: str) -> str | None:
    """
    Spawn a login shell to read a single env var injected by bw-env.

    A login shell sources .zshrc → load.sh → /dev/shm secrets, giving us the
    freshly-loaded value without knowing anything about bw-env internals.
    Returns None if the var is unset or the shell fails.
    """
    try:
        result = subprocess.run(
            [_SHELL, "-l", "-c", f'printf "%s" "${{{key}}}"'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        val = result.stdout.strip()
        return val if val else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        _log.debug("Login shell read for %s failed: %s", key, exc)
        return None


def _try_bwenv_restart() -> bool:
    """
    Run `bw-env restart` and wait for the daemon to sync.

    bw-env restart triggers `systemctl --user restart bw-env-sync.service`,
    which may display a Zenity password popup if the vault is locked.

    Returns True if after waiting, at least one of the managed keys becomes
    available via a login shell.  Returns False otherwise (user cancelled,
    wrong password, daemon error, timeout …).
    """
    if not _bwenv_available():
        _log.debug("bw-env not found on PATH — skipping restart.")
        return False

    _log.info(
        "TickTick tokens not found in environment. "
        "Running '%s restart' (may prompt for vault password)…",
        _BWENV_CMD,
    )
    try:
        subprocess.run(
            [_BWENV_CMD, "restart"],
            timeout=10,
            capture_output=True,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        _log.warning("'%s restart' failed: %s", _BWENV_CMD, exc)
        return False

    # Wait for the daemon to complete its sync cycle.
    _log.info("Waiting up to %ds for daemon to sync secrets…", _RESTART_WAIT)
    deadline = time.monotonic() + _RESTART_WAIT
    while time.monotonic() < deadline:
        time.sleep(2)
        # Check if any of our keys are now available via login shell
        for key in _MANAGED_KEYS:
            if _shell_read_env(key):
                _log.info("Secrets available after daemon sync.")
                return True

    _log.warning("Timeout: secrets still unavailable after %ds.", _RESTART_WAIT)
    return False


# ═══════════════════════════════════════════════════════════════════════════════
#  Dotenv write-back (session token only — not for sensitive API token)
# ═══════════════════════════════════════════════════════════════════════════════

def _write_to_dotenv(key: str, value: str) -> None:
    """
    Insert or update *key=value* in the package .env file.

    Uses atomic write (tmp → rename) to avoid partial reads.
    """
    _DOTENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    found = False

    if _DOTENV_PATH.is_file():
        for line in _DOTENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}=") or line.startswith(f"export {key}="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)

    if not found:
        lines.append(f"{key}={value}")

    tmp = _DOTENV_PATH.with_suffix(".env.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.rename(_DOTENV_PATH)
    _log.debug("Wrote %s to .env (write-back from vault).", key)


# ═══════════════════════════════════════════════════════════════════════════════
#  Core resolver: 2-tier fallback
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_env(
    key: str,
    *,
    required: bool = False,
    cache_to_dotenv: bool = False,
    skip_tier1: bool = False,
) -> str | None:
    """
    Resolve an environment variable through the 2-tier chain.

    Parameters
    ----------
    key
        Environment variable name (e.g. ``TICKTICK_API_TOKEN``).
    required
        If True and resolution fails, raise SecretsUnavailableError.
    cache_to_dotenv
        If True, write Tier-2 values back to .env for future cold starts.
        Only used for non-sensitive tokens (session token).
    skip_tier1
        If True, skip os.environ (Tier 1) — used when we know the current
        value is stale (e.g. after a 401) and want a fresh vault read.
    """
    tried: list[str] = []

    # ── Tier 1: os.environ (.env already loaded at import time) ──
    if not skip_tier1:
        tried.append("Tier 1: os.environ / .env file")
        val = os.environ.get(key)
        if val:
            _log.debug("%s resolved from Tier 1 (os.environ).", key)
            return val

    # ── Tier 2: bw-env via login shell (+ restart if needed) ──
    if _bwenv_available():
        # 2a: maybe bw-env already synced but this process missed it
        tried.append("Tier 2a: login shell read (bw-env already synced)")
        val = _shell_read_env(key)
        if val:
            _log.info("%s resolved from Tier 2a (login shell).", key)
            os.environ[key] = val
            if cache_to_dotenv:
                _write_to_dotenv(key, val)
            return val

        # 2b: trigger daemon restart → wait → re-read
        tried.append(
            f"Tier 2b: '{_BWENV_CMD} restart' + wait {_RESTART_WAIT}s + login shell read"
        )
        if _try_bwenv_restart():
            val = _shell_read_env(key)
            if val:
                _log.info("%s resolved from Tier 2b (after daemon restart).", key)
                os.environ[key] = val
                if cache_to_dotenv:
                    _write_to_dotenv(key, val)
                return val
    else:
        tried.append("Tier 2: skipped — bw-env not installed")

    # ── Not found anywhere ──
    if required:
        raise SecretsUnavailableError(
            key,
            tried=tried,
            hints=[
                "Vault is locked — the Zenity password popup may have been dismissed or the password was incorrect.",
                "Maximum authentication attempts reached (bw-env locks after 3 failures).",
                f"bw-env daemon not running or crashed — check: {_BWENV_CMD} status",
                f"Daemon sync failed — check logs: {_BWENV_CMD} logs -n 30",
                f"The variable '{key}' is not defined in your Vaultwarden vault's global_env item.",
                "Network issue — Vaultwarden server unreachable during sync.",
                f"Manual fix: ticktick-admin token set <value>  or add {key}=<value> to .env",
            ],
        )
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Public token getters
# ═══════════════════════════════════════════════════════════════════════════════

def get_api_token() -> str:
    """
    Reads the V1 OAuth2 Bearer token.

    Resolution: os.environ → bw-env login shell → daemon restart.
    Raises SecretsUnavailableError if the token cannot be found anywhere.
    NEVER written back to .env (sensitive secret stays in vault only).
    """
    return _resolve_env(ENV_API_TOKEN, required=True)  # type: ignore[return-value]


def get_session_token() -> str | None:
    """
    Reads the V2 session cookie token.

    Resolution with write-back: if found via bw-env but absent from .env,
    the value is cached to .env for future cold starts (non-sensitive).
    Returns None if not set; client.py will fall back to auto-login.
    """
    return _resolve_env(ENV_SESSION_TOKEN, cache_to_dotenv=True)


def refresh_session_from_vault() -> str | None:
    """
    Force re-read of the V2 session token from bw-env (skip current env).

    Called by client.py after a 401: we assume the current value is stale
    and go straight to a fresh login shell read.
    If found AND different from the current value → updates .env + os.environ.
    Returns None if no fresh value is available.
    """
    current = os.environ.get(ENV_SESSION_TOKEN)
    fresh = _resolve_env(
        ENV_SESSION_TOKEN,
        cache_to_dotenv=True,
        skip_tier1=True,
    )
    if fresh and fresh != current:
        _log.info("Session token refreshed from vault (different from current).")
        return fresh
    _log.debug("Vault session token is unchanged or missing — no refresh.")
    return None


def get_username() -> str | None:
    """Reads the TickTick username for V2 auto-login."""
    return _resolve_env(ENV_USERNAME)


def get_password() -> str | None:
    """Reads the TickTick password for V2 auto-login."""
    return _resolve_env(ENV_PASSWORD)


def has_v2_auth() -> bool:
    """Return True if V2 auth is possible: token present OR credentials present."""
    return bool(get_session_token()) or bool(get_username() and get_password())
