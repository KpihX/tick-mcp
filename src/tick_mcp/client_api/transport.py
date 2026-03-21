"""
Low-level TickTick transport helpers and auth/session handling.
"""
from __future__ import annotations

import sys

import httpx

from ..config import (
    API_V1_BASE_URL, API_V2_BASE_URL, API_TIMEOUT,
    V2_SIGNON_URL, SIGNON_PARAMS, V2_LOGIN_HEADERS, SESSION_COOKIE_NAME,
    USER_AGENT, V2_DEVICE_HEADER,
    ENV_API_TOKEN, ENV_SESSION_TOKEN, ENV_USERNAME, ENV_PASSWORD,
    get_api_token, get_session_token, get_username, get_password, has_v2_auth,
    refresh_session_from_vault, SessionTokenExpiredError,
)
from ..models import TickTickAPIError

# ── V2 session token cache ────────────────────────────────────────────────────
# Module-level variable: survives for the lifetime of the MCP process.
# Initialised empty; populated lazily on the first V2 call.
_v2_session_token: str | None = None


def _client_override(name: str, default: object) -> object:
    facade = sys.modules.get("tick_mcp.client")
    if facade is None:
        return default
    return getattr(facade, name, default)


def _set_cached_token(token: str | None) -> None:
    global _v2_session_token
    _v2_session_token = token
    facade = sys.modules.get("tick_mcp.client")
    if facade is not None:
        setattr(facade, "_v2_session_token", token)


def _v2_invalidate() -> None:
    """Clear the in-process V2 token cache (called before re-login on 401)."""
    _set_cached_token(None)


def _v2_login() -> str:
    """
    Authenticate against the TickTick web API and cache the session token.

    POST /api/v2/user/signon?wc=true&remember=true
    Body : {"username": <email>, "password": <password>}
    Response includes a top-level "token" field — that is the V2 session cookie.

    Raises TickTickAPIError if credentials are missing or login fails.
    """
    global _v2_session_token
    username = _client_override("get_username", get_username)()
    password = _client_override("get_password", get_password)()
    if not username or not password:
        raise TickTickAPIError(
            0,
            "V2 auth unavailable. Provide either:\n"
            f"  • {ENV_SESSION_TOKEN} (session cookie from browser)\n"
            f"  • {ENV_USERNAME} + {ENV_PASSWORD} (auto-login)\n"
            "See .env.example for details."
        )
    with httpx.Client(timeout=API_TIMEOUT) as c:
        r = c.post(
            V2_SIGNON_URL,
            params=SIGNON_PARAMS,
            json={"username": username, "password": password},
            headers=V2_LOGIN_HEADERS,
        )
    if r.status_code != 200:
        raise TickTickAPIError(r.status_code, f"V2 login failed: {r.text[:200]}")
    data = r.json()
    token = data.get("token")
    if token:
        _set_cached_token(token)
        return token
    # TickTick requires a verification code (device/2FA check)
    if data.get("authId"):
        raise TickTickAPIError(
            0,
            "V2 login requires a verification code (device check / 2FA).\n"
            "The automated flow cannot handle interactive prompts.\n"
            "Fix: run  tick-admin session refresh  in your terminal —\n"
            "  it will prompt for the code interactively and save the token."
        )
    raise TickTickAPIError(
        0, f"V2 login succeeded but response has no 'token' field. Keys: {list(data.keys())}"
    )


def _get_v2_token() -> str:
    """
    Return a valid V2 session token, resolving in this priority order:
      1. In-process cache (_v2_session_token) — fastest path
      2. TICKTICK_SESSION_TOKEN env var — loaded once at startup
      3. Auto-login via TICKTICK_USERNAME + TICKTICK_PASSWORD
    """
    facade_cached = _client_override("_v2_session_token", None)
    if facade_cached:
        _set_cached_token(str(facade_cached))
        return str(facade_cached)
    if _v2_session_token:
        return _v2_session_token
    token = _client_override("get_session_token", get_session_token)()          # from env / .env file
    if token:
        _set_cached_token(str(token))
        return str(token)
    return _client_override("_v2_login", _v2_login)()                   # credentials-based auto-login


def _v1_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_client_override('get_api_token', get_api_token)()}",
        "Content-Type": "application/json",
    }


def _v2_headers() -> dict[str, str]:
    return {
        "Cookie": f"{SESSION_COOKIE_NAME}={_get_v2_token()}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-Device": V2_DEVICE_HEADER,
    }


def _require_v2() -> None:
    """Raise a clear error if V2 auth is not possible at all."""
    if not _client_override("has_v2_auth", has_v2_auth)():
        raise TickTickAPIError(
            0,
            "This feature requires V2 API access. Provide either:\n"
            f"  • {ENV_SESSION_TOKEN} (session cookie from browser)\n"
            f"  • {ENV_USERNAME} + {ENV_PASSWORD} (auto-login)\n"
            "See .env.example for details."
        )


def _v2_call(
    method: str,
    endpoint: str,
    *,
    params: dict | None = None,
    payload: dict | list | None = None,
) -> dict | list:
    """
    Execute a V2 HTTP request with automatic token refresh on 401.

    Flow:
      1. Try request with current token.
      2. If 401 → invalidate cache → re-login → retry ONCE.
      3. If still 401 → raise TickTickAPIError(401, ...).
    """
    url = f"{API_V2_BASE_URL}{endpoint}"

    def _do() -> httpx.Response:
        with httpx.Client(timeout=API_TIMEOUT) as c:
            kwargs: dict = {"headers": _v2_headers(), "params": params}
            if method in ("post", "put", "patch"):
                kwargs["json"] = payload
            return getattr(c, method)(url, **kwargs)

    tried: list[str] = []
    r = _do()
    if r.status_code == 401:
        tried.append("Initial request with cached/env token → 401")
        # ── Attempt 1: check if the login shell exposes a fresher token ──
        fresh = _client_override("refresh_session_from_vault", refresh_session_from_vault)()
        if fresh:
            _set_cached_token(str(fresh))
            tried.append("Login-shell refresh returned a NEW token → retrying")
            r = _do()
        else:
            tried.append("Login-shell refresh: same token or unavailable")
            # ── Attempt 2: fallback to credentials-based re-login ──
            _v2_invalidate()   # stale token → discard
            tried.append("Credentials re-login attempted")
            r = _do()          # re-login triggered via _get_v2_token → _v2_login
    if r.status_code == 401:
        raise SessionTokenExpiredError(tried=tried)
    return _handle(r)


def _handle(r: httpx.Response) -> dict | list:
    """Translate HTTP status codes into structured errors."""
    if r.status_code == 401:
        raise TickTickAPIError(
            401,
            f"V1 API token expired or invalid ({ENV_API_TOKEN}).\n"
            "Fix: run  tick-admin token set <new_token>  in your terminal,\n"
            "  or copy the token from TickTick → Settings → Integrations → API\n"
            "  and set it in src/tick_mcp/.env."
        )
    if r.status_code == 403:
        raise TickTickAPIError(403, "Forbidden — insufficient permissions for this resource.")
    if r.status_code == 404:
        raise TickTickAPIError(404, "Not found — check project_id and task_id.")
    if r.status_code == 429:
        raise TickTickAPIError(429, "Rate limit exceeded — wait a moment before retrying.")
    if r.status_code >= 500:
        raise TickTickAPIError(r.status_code, f"TickTick server error. Body: {r.text[:200]}")
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError:
        raise TickTickAPIError(r.status_code, r.text[:300])
    # 204 No Content (DELETE) or empty response
    if r.status_code == 204 or not r.content:
        return {}
    return r.json()


# ── V1 HTTP helpers ───────────────────────────────────────────────────────────

def _v1_get(endpoint: str) -> dict | list:
    url = f"{API_V1_BASE_URL}{endpoint}"
    with httpx.Client(timeout=API_TIMEOUT) as c:
        return _handle(c.get(url, headers=_v1_headers()))


def _v1_post(endpoint: str, payload: dict) -> dict | list:
    url = f"{API_V1_BASE_URL}{endpoint}"
    with httpx.Client(timeout=API_TIMEOUT) as c:
        return _handle(c.post(url, json=payload, headers=_v1_headers()))


def _v1_delete(endpoint: str) -> None:
    url = f"{API_V1_BASE_URL}{endpoint}"
    with httpx.Client(timeout=API_TIMEOUT) as c:
        _handle(c.delete(url, headers=_v1_headers()))


# ── V2 HTTP helpers ───────────────────────────────────────────────────────────

def _v2_get(endpoint: str, params: dict | None = None) -> dict | list:
    _require_v2()
    return _v2_call("get", endpoint, params=params)


def _v2_post(endpoint: str, payload: dict | list | None = None) -> dict | list:
    _require_v2()
    return _v2_call("post", endpoint, payload=payload)


def _v2_put(endpoint: str, payload: dict | None = None) -> dict | list:
    _require_v2()
    return _v2_call("put", endpoint, payload=payload)


def _v2_delete(endpoint: str, params: dict | None = None) -> dict | list:
    _require_v2()
    return _v2_call("delete", endpoint, params=params)

__all__ = [
    '_v2_invalidate', '_v2_login', '_get_v2_token',
    '_v1_headers', '_v2_headers', '_require_v2',
    '_v2_call', '_handle', '_v1_get', '_v1_post', '_v1_delete',
    '_v2_get', '_v2_post', '_v2_put', '_v2_delete',
]
