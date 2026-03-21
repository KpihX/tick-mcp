"""Configuration and secret resolution for tick-mcp."""
from __future__ import annotations

import logging
import os
import subprocess
import tomllib
import yaml
from pathlib import Path
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as pkg_version
from dotenv import load_dotenv

# ─── Paths ────────────────────────────────────────────────────────────────────
_PACKAGE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_DIR.parent.parent
_PYPROJECT_PATH = _PROJECT_ROOT / "pyproject.toml"
CONFIG_PATH = _PACKAGE_DIR / "config.yaml"
_DEFAULT_DOTENV_PATH = _PACKAGE_DIR / ".env"

# ─── Logging ──────────────────────────────────────────────────────────────────
_log = logging.getLogger("tick_mcp.config")

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


@lru_cache(maxsize=1)
def _load_project_metadata(pyproject_path: Path = _PYPROJECT_PATH) -> dict[str, str]:
    """Read project metadata directly from pyproject.toml."""
    if not pyproject_path.exists():
        return {}
    with pyproject_path.open("rb") as handle:
        data = tomllib.load(handle)
    project = data.get("project", {})
    name = str(project.get("name", "")).strip()
    version = str(project.get("version", "")).strip()
    result: dict[str, str] = {}
    if name:
        result["name"] = name
    if version:
        result["version"] = version
    return result


# ─── Global typed constants ───────────────────────────────────────────────────
_config = load_config()
_project_meta = _load_project_metadata()
_api = _config.get("api", {})
_server = _config.get("server", {})
_server_http = _server.get("http", {})


def _read_env_override(name: str, default: str) -> str:
    """Read a runtime override from the environment, falling back to config."""
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _package_version(default: str) -> str:
    """Read the installed package version, or fall back to pyproject metadata."""
    try:
        return pkg_version("tick-mcp")
    except PackageNotFoundError:
        return default

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

SERVER_NAME: str = _project_meta.get("name", "tick-mcp")
APP_VERSION: str = _package_version(_project_meta.get("version", "0.0.0"))
STATE_DIRECTORY: Path = Path(
    _server.get("state_directory", "~/.mcps/ticktick")
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
ENV_HTTP_HOST: str = _env_vars.get("http_host", "TICK_MCP_HTTP_HOST")
ENV_HTTP_PORT: str = _env_vars.get("http_port", "TICK_MCP_HTTP_PORT")
ENV_HTTP_MCP_PATH: str = _env_vars.get("http_mcp_path", "TICK_MCP_HTTP_MCP_PATH")
ENV_PUBLIC_BASE_URL: str = _env_vars.get("public_base_url", "TICK_MCP_PUBLIC_BASE_URL")
ENV_FALLBACK_BASE_URL: str = _env_vars.get("fallback_base_url", "TICK_MCP_FALLBACK_BASE_URL")
ENV_ADMIN_ENV_FILE: str = _env_vars.get("admin_env_file", "TICK_MCP_ADMIN_ENV_FILE")
ENV_TELEGRAM_TICK_HOMELAB_TOKEN: str = _env_vars.get(
    "telegram_tick_homelab_token",
    "TELEGRAM_TICK_HOMELAB_TOKEN",
)
ENV_TELEGRAM_CHAT_IDS: str = _env_vars.get(
    "telegram_chat_ids",
    "TELEGRAM_CHAT_IDS",
)

_DOTENV_PATH = Path(
    os.environ.get(ENV_ADMIN_ENV_FILE, str(_DEFAULT_DOTENV_PATH))
).expanduser()

# ─── .env loading ─────────────────────────────────────────────────────────────
# override=True: values from .env overwrite any already-set os.environ entries.
# If .env doesn't exist this is a no-op, falling back to plain os.environ.
load_dotenv(_DOTENV_PATH, override=True)

HTTP_HOST: str = _read_env_override(ENV_HTTP_HOST, str(_server_http.get("host", "127.0.0.1")))
HTTP_PORT: int = int(_read_env_override(ENV_HTTP_PORT, str(_server_http.get("port", 8091))))
HTTP_MCP_PATH: str = _read_env_override(ENV_HTTP_MCP_PATH, str(_server_http.get("mcp_path", "/mcp")))
HTTP_PUBLIC_BASE_URL: str = _read_env_override(
    ENV_PUBLIC_BASE_URL,
    str(_server_http.get("public_base_url", "https://tick.kpihx-labs.com")),
)
HTTP_FALLBACK_BASE_URL: str = _read_env_override(
    ENV_FALLBACK_BASE_URL,
    str(_server_http.get("fallback_base_url", "https://tick.homelab")),
)
ADMIN_ENV_PATH: Path = _DOTENV_PATH
TELEGRAM_TICK_HOMELAB_TOKEN: str | None = os.environ.get(ENV_TELEGRAM_TICK_HOMELAB_TOKEN)
TELEGRAM_CHAT_IDS_RAW: str = os.environ.get(
    ENV_TELEGRAM_CHAT_IDS,
    "",
)
TELEGRAM_CHAT_IDS: tuple[str, ...] = tuple(
    chat_id.strip()
    for chat_id in TELEGRAM_CHAT_IDS_RAW.split(",")
    if chat_id.strip()
)

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
            "  2. Refresh your environment secrets in a login shell.\n"
            "  3. Or set it directly: tick-admin session set <token>"
        )
        super().__init__(msg)


# ═══════════════════════════════════════════════════════════════════════════════
#  Tier 2: login-shell environment re-read
# ═══════════════════════════════════════════════════════════════════════════════

def _shell_read_env(key: str) -> str | None:
    """
    Spawn a login shell to read a single environment variable.

    This is the canonical fallback when the current process environment is
    missing a required secret but the user's login shell knows how to load it.
    Returns None if the var is unset or the shell fails.
    """
    try:
        result = subprocess.run(
            ["zsh", "-l", "-c", f'printf "%s" "${{{key}}}"'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        val = result.stdout.strip()
        return val if val else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        _log.debug("Login shell read for %s failed: %s", key, exc)
        return None

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

    # ── Tier 2: login shell environment ──
    tried.append("Tier 2: login shell read via zsh -l -c")
    val = _shell_read_env(key)
    if val:
        _log.info("%s resolved from Tier 2 (login shell).", key)
        os.environ[key] = val
        if cache_to_dotenv:
            _write_to_dotenv(key, val)
        return val

    # ── Not found anywhere ──
    if required:
        raise SecretsUnavailableError(
            key,
            tried=tried,
            hints=[
                f"The variable '{key}' is not available in the current process environment.",
                "Your login shell does not expose the variable either.",
                "Open a fresh login shell and confirm the variable is exported there.",
                f"Manual fix: tick-admin token set <value>  or add {key}=<value> to .env",
            ],
        )
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Public token getters
# ═══════════════════════════════════════════════════════════════════════════════

def get_api_token() -> str:
    """
    Reads the V1 OAuth2 Bearer token.

    Resolution: os.environ → login shell fallback.
    Raises SecretsUnavailableError if the token cannot be found anywhere.
    NEVER written back to .env (sensitive secret stays in vault only).
    """
    return _resolve_env(ENV_API_TOKEN, required=True)  # type: ignore[return-value]


def get_session_token() -> str | None:
    """
    Reads the V2 session cookie token.

    Resolution with write-back: if found via login shell but absent from .env,
    the value is cached to .env for future cold starts (non-sensitive).
    Returns None if not set; client.py will fall back to auto-login.
    """
    return _resolve_env(ENV_SESSION_TOKEN, cache_to_dotenv=True)


def refresh_session_from_vault() -> str | None:
    """
    Force re-read of the V2 session token from the login shell (skip current env).

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


def has_v2_auth_in_environment() -> bool:
    """
    Return True if V2 auth material is already present in the current process env.

    This helper is intentionally non-interactive: it must never trigger login-
    shell reads. It is safe for `/health` style probes.
    """
    return bool(os.environ.get(ENV_SESSION_TOKEN)) or bool(
        os.environ.get(ENV_USERNAME) and os.environ.get(ENV_PASSWORD)
    )
