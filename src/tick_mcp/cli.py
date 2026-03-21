"""
tick-admin — Admin CLI for the TickTick MCP server.

Manage credentials stored in .env (src/tick_mcp/.env) without going through
the LLM. All writes go through python-dotenv's set_key(), which safely creates
or updates a single line without touching the rest of the file.

Usage examples:
    tick-admin status
    tick-admin token set eyJhbGciOiJIUzI1NiJ9...
    tick-admin session set <cookie-value-from-browser>
    tick-admin session refresh          # interactive: prompts username + password
    tick-admin session refresh --username me@email.com
"""

import sys
import json
import logging
import httpx
import typer
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Annotated, Optional
from dotenv import set_key, dotenv_values
from rich.console import Console
from rich.table import Table
from rich import box
from .admin_service import (
    API_EXPIRES_AT_KEY,
    APPROX_SESSION_TTL,
    SESSION_EXPIRES_AT_KEY,
    SESSION_OBTAINED_AT_KEY,
    get_status_payload,
    set_api_token as service_set_api_token,
    set_session_token as service_set_session_token,
)
from .config import (
    ADMIN_ENV_PATH,
    V2_SIGNON_URL, V2_MFA_VERIFY_URL, V2_LOGIN_HEADERS,
    SIGNON_PARAMS, API_TIMEOUT, WEB_ORIGIN,
    ENV_API_TOKEN, ENV_SESSION_TOKEN,
)

# ─── Paths ────────────────────────────────────────────────────────────────────────────
_PACKAGE_DIR = Path(__file__).resolve().parent
_DOTENV_PATH = ADMIN_ENV_PATH
_LOG_DIR = _PACKAGE_DIR.parent.parent.parent / "logs"   # repo root / logs/
_LOG_FILE = _LOG_DIR / "ticktick_admin_debug.log"

# ─── Debug logger ─────────────────────────────────────────────────────────────────────
class _FlushingFileHandler(logging.FileHandler):
    """FileHandler that flushes after every record — prevents empty log on Ctrl+C."""
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()

def _setup_logger() -> logging.Logger:
    _LOG_DIR.mkdir(exist_ok=True)
    log = logging.getLogger("ticktick_admin")
    if not log.handlers:
        log.setLevel(logging.DEBUG)
        fh = _FlushingFileHandler(_LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
        log.addHandler(fh)
    return log

_log = _setup_logger()


def _log_request(label: str, method: str, url: str, params: dict, payload: dict, headers: dict):
    _log.debug("=" * 80)
    _log.debug(f"REQUEST  [{label}]  {method.upper()} {url}")
    _log.debug(f"  params : {json.dumps(params)}")
    # Redact password in log
    safe_payload = {k: ("***REDACTED***" if k == "password" else v) for k, v in payload.items()}
    _log.debug(f"  body   : {json.dumps(safe_payload)}")
    safe_headers = {k: ("***REDACTED***" if "auth" in k.lower() or "cookie" in k.lower() else v)
                    for k, v in headers.items()}
    _log.debug(f"  headers: {json.dumps(safe_headers)}")


def _log_response(label: str, r: httpx.Response):
    _log.debug(f"RESPONSE [{label}]  status={r.status_code}")
    _log.debug(f"  headers: {dict(r.headers)}")
    try:
        body = r.json()
        # Redact token in log
        safe_body = {k: ("***REDACTED***" if k in ("token", "password") else v)
                     for k, v in (body.items() if isinstance(body, dict) else {}.items())}
        _log.debug(f"  body   : {json.dumps(safe_body, indent=2)}")
        # Log the raw keys always so we can see unknown fields
        if isinstance(body, dict):
            _log.debug(f"  keys   : {list(body.keys())}")
    except Exception:
        _log.debug(f"  raw    : {r.text[:2000]}")


# ─── Typer + Rich setup ───────────────────────────────────────────────────────
app = typer.Typer(
    name="tick-admin",
    help="Admin CLI — manage TickTick MCP credentials (API token, V2 session token).",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)
token_app = typer.Typer(help=f"Manage the V1 API token ({ENV_API_TOKEN}).", no_args_is_help=True)
session_app = typer.Typer(help=f"Manage the V2 session token ({ENV_SESSION_TOKEN}).", no_args_is_help=True)
app.add_typer(token_app, name="token")
app.add_typer(session_app, name="session")

console = Console()
err = Console(stderr=True)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _mask(value: str | None, *, show: int = 6) -> str:
    """Return a partially masked version of a secret value."""
    if not value:
        return "[dim]not set[/dim]"
    if len(value) <= show * 2:
        return "[bold yellow]" + "*" * len(value) + "[/bold yellow]"
    return f"[bold yellow]{value[:show]}{'…' + value[-show:]}[/bold yellow]"


def _env_value(key: str) -> str | None:
    """Read a variable from .env on disk (not the process environment)."""
    return dotenv_values(_DOTENV_PATH).get(key)


def _write_env(key: str, value: str) -> None:
    """Write or update a key in .env, creating the file if needed."""
    _DOTENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DOTENV_PATH.touch(exist_ok=True)
    success, _, _ = set_key(str(_DOTENV_PATH), key, value, quote_mode="never")
    if not success:
        err.print(f"[red]Failed to write {key} to {_DOTENV_PATH}[/red]")
        raise typer.Exit(1)


def _write_optional_env(key: str, value: str | None) -> None:
    """Write an env key only when a value is explicitly provided."""
    if value is None:
        return
    _write_env(key, value)


def _now_utc() -> datetime:
    """Return the current UTC timestamp as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def _to_epoch_string(dt: datetime) -> str:
    """Serialize a timezone-aware datetime to epoch seconds."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return str(int(dt.timestamp()))


def _parse_epoch(value: str | None) -> datetime | None:
    """Parse epoch seconds stored in .env metadata."""
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime option to a timezone-aware UTC datetime."""
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        err.print("[red]Invalid datetime format.[/red] Use ISO-8601, e.g. 2026-04-20T18:30:00+00:00")
        raise typer.Exit(1)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(dt: datetime | None) -> str:
    """Render a UTC datetime for human-readable status output."""
    if not dt:
        return "[dim]unknown[/dim]"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _format_remaining(expires_at: datetime | None, *, approximate: bool = False) -> str:
    """Render human-readable time remaining until expiration."""
    if not expires_at:
        return "[dim]unknown[/dim]"
    remaining = expires_at - _now_utc()
    if remaining.total_seconds() <= 0:
        return "[red]expired[/red]"
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
    return f"[green]{prefix}{' '.join(parts)}[/green]"


def _timing_summary(
    *,
    expires_at: datetime | None,
    obtained_at: datetime | None = None,
    approximate: bool = False,
) -> str:
    """Build a compact status string for token timing metadata."""
    segments = []
    if obtained_at:
        segments.append(f"obtained {_format_timestamp(obtained_at)}")
    if expires_at:
        segments.append(f"expires {_format_timestamp(expires_at)}")
        segments.append(f"left {_format_remaining(expires_at, approximate=approximate)}")
    return " | ".join(segments) if segments else "[dim]no expiration metadata[/dim]"


def _http_post(label: str, url: str, payload: dict, *, extra_headers: dict | None = None) -> httpx.Response:
    """Shared POST helper with standard V2 headers — logs everything."""
    headers = {**V2_LOGIN_HEADERS, **(extra_headers or {})}
    _log_request(label, "POST", url, SIGNON_PARAMS, payload, headers)
    r = httpx.post(
        url,
        params=SIGNON_PARAMS,
        json=payload,
        headers=headers,
        timeout=API_TIMEOUT,
    )
    _log_response(label, r)
    return r


def _describe_verif_target(data: dict) -> str:
    """Extract a human-readable description of where the code was/will be sent."""
    hints = []
    for key in ("bindEmail", "email", "bindPhone", "phone", "bindInfo"):
        v = data.get(key)
        if v:
            hints.append(f"{key}: [bold]{v}[/bold]")
    vtype = data.get("verifyType") or data.get("type")
    type_label = {1: "SMS", 2: "email", 3: "authenticator app"}.get(vtype, f"type={vtype}") if vtype else None
    if type_label:
        hints.append(f"method: [bold]{type_label}[/bold]")
    return "  " + "  |  ".join(hints) if hints else "  [dim](check your authenticator app, email, and SMS)[/dim]"


def _v2_login(username: str, password: str) -> str:
    """
    POST to /api/v2/user/signon and return the session token.

    Two verification flows depending on expireTime in the authId response:
      - expireTime ≤ 600  (typ. 300s = 5 min)  → TOTP code from authenticator app
      - expireTime > 3600 (typ. 86400s = 24 h)  → device-trust link sent by email
    All HTTP exchanges are logged to logs/ticktick_admin_debug.log.
    """
    _log.info("=== session refresh started for %s ===", username)
    console.print(f"[dim]Debug log: {_LOG_FILE}[/dim]")

    try:
        r = _http_post("signon", V2_SIGNON_URL, {"username": username, "password": password})
    except httpx.ConnectError:
        err.print(f"[red]Network error: could not reach {WEB_ORIGIN}[/red]")
        raise typer.Exit(1)

    if r.status_code != 200:
        _log.error("signon: HTTP %s  body=%s", r.status_code, r.text[:500])
        err.print(f"[red]Login failed ({r.status_code}):[/red] {r.text[:300]}")
        raise typer.Exit(1)

    data = r.json()
    _log.debug("signon response keys: %s | safe: %s",
               list(data.keys()),
               json.dumps({k: ("***" if k in ("token", "password") else v) for k, v in data.items()}))

    token = data.get("token")
    if token:
        _log.info("signon: token returned directly (no 2FA)")
        return token

    auth_id = data.get("authId")
    if not auth_id:
        _log.error("signon: no 'token' and no 'authId'. data=%s", data)
        err.print("[red]Unexpected response — no 'token' or 'authId'.[/red]")
        err.print(f"[dim]Full response: {data}[/dim]")
        err.print(f"[dim]See {_LOG_FILE} for details.[/dim]")
        raise typer.Exit(1)

    expire_time = data.get("expireTime", 0)
    _log.info("signon: authId=%r  expireTime=%s  other_keys=%s",
              auth_id, expire_time, [k for k in data if k not in ("authId", "expireTime")])

    # Route based on expireTime:
    #   ≤ 600  = short TTL → TOTP/MFA code (authenticator app)
    #   > 3600 = long TTL  → device-trust email link (click to authorize)
    if expire_time > 3600:
        return _handle_link_flow(username, password, auth_id, data)
    else:
        return _handle_code_flow(username, password, auth_id, data)


def _handle_link_flow(username: str, password: str, auth_id: str, signon_data: dict) -> str:
    """
    Device-trust flow (expireTime ≈ 86400s).

    TickTick sent an email with a clickable authorization link — NOT a numeric code.
    After the user clicks the link, we retry signon; the device is now trusted
    and signon should return a token directly.
    """
    _log.info("flow=link (expireTime=86400): waiting for user to click email link")

    console.print()
    console.print("[yellow bold]⚠  Device authorization required[/yellow bold]")
    console.print()
    console.print("  TickTick does not recognize this device/IP.")
    console.print("  An authorization [bold]email[/bold] was sent to your registered address.")
    console.print()
    console.print("  [bold]Steps:[/bold]")
    console.print("    1. Open your email inbox (check [bold]spam / promotions[/bold])")
    console.print("    2. Find a TickTick email — subject like [italic]'Login Verification'[/italic] or [italic]'Authorize Login'[/italic]")
    console.print("    3. Click the button / link inside the email (opens your browser)")
    console.print("    4. Come back here and press [bold]Enter[/bold]")
    console.print()
    console.print("  [dim]Note: there is NO numeric code — you must click the link.[/dim]")
    console.print("  [dim]The link is valid for 24 hours.[/dim]")
    console.print("  [dim]authId (for reference): %s[/dim]" % auth_id)
    console.print()

    typer.prompt("Press Enter once you have clicked the link in the email",
                 default="", show_default=False, prompt_suffix=" ▶ ")

    _log.info("user confirmed link clicked — retrying signon")
    console.print("[dim]Retrying login…[/dim]", end=" ")

    try:
        r2 = _http_post("signon_after_link", V2_SIGNON_URL,
                        {"username": username, "password": password})
    except httpx.ConnectError:
        _log.error("signon_after_link: ConnectError")
        err.print("[red]Network error on retry.[/red]")
        raise typer.Exit(1)

    if r2.status_code != 200:
        _log.error("signon_after_link: HTTP %s  body=%s", r2.status_code, r2.text[:500])
        err.print(f"[red]Login failed on retry ({r2.status_code}):[/red] {r2.text[:300]}")
        raise typer.Exit(1)

    data2 = r2.json()
    _log.debug("signon_after_link keys: %s", list(data2.keys()))

    token = data2.get("token")
    if token:
        _log.info("signon_after_link: token obtained — device now trusted")
        return token

    if data2.get("authId"):
        new_expire = data2.get("expireTime", 0)
        _log.warning("signon_after_link: still got authId (expireTime=%s) — device not yet trusted", new_expire)
        err.print()
        err.print("[red]TickTick still requires verification — device not yet authorized.[/red]")
        err.print()
        err.print("  Possible reasons:")
        err.print("  • You haven't received the email yet (wait a few minutes and try again)")
        err.print("  • The email went to spam — check all folders")
        err.print("  • You need to click the link, not just open the email")
        err.print()
        err.print("  [dim]Alternative: extract the session cookie from your browser after logging in:[/dim]")
        err.print("  [dim]  tick-admin session set[/dim]")
        raise typer.Exit(1)

    _log.error("signon_after_link: unexpected response: %s", data2)
    err.print(f"[red]Unexpected response:[/red] {data2}")
    raise typer.Exit(1)


def _handle_code_flow(username: str, password: str, auth_id: str, signon_data: dict) -> str:
    """
    TOTP / MFA code flow (expireTime ≈ 300s).

    TickTick requires a 6-digit code from an authenticator app (or SMS/email).
    The code is submitted to /api/v2/user/sign/mfa/code/verify with the
    authId in the x-verify-id request header.
    """
    _log.info("flow=code (expireTime<=600): prompting for TOTP/MFA code")

    console.print()
    console.print("[yellow bold]⚠  2FA verification required[/yellow bold]")
    console.print("[dim]TickTick requires a 6-digit code (authenticator app / SMS / email).[/dim]")
    console.print(_describe_verif_target(signon_data))
    console.print()
    console.print("[dim]Type [bold]resend[/bold] to request a new code  |  Ctrl+C to abort[/dim]")
    console.print()

    while True:
        raw = typer.prompt("6-digit code (or 'resend')")
        code = raw.strip()

        if code.lower() == "resend":
            _log.info("user requested resend")
            console.print("[dim]Requesting new code…[/dim]", end=" ")
            try:
                rs = _http_post("resend", V2_SIGNON_URL,
                                {"username": username, "password": password})
                rs_data = rs.json()
                _log.info("resend keys=%s | %s", list(rs_data.keys()),
                          json.dumps({k: ("***" if k in ("token",) else v) for k, v in rs_data.items()}))
                if rs_data.get("token"):
                    _log.info("resend returned token directly")
                    return rs_data["token"]
                new_id = rs_data.get("authId")
                if new_id:
                    auth_id = new_id
                    console.print("[green]✓ New code requested.[/green]")
                    console.print(_describe_verif_target(rs_data))
                else:
                    _log.warning("resend: unexpected: %s", rs_data)
                    console.print(f"[yellow]Unexpected resend response: {rs_data}[/yellow]")
            except httpx.ConnectError:
                _log.error("resend: ConnectError")
                console.print("[red]Network error during resend.[/red]")
            continue

        if not code:
            console.print("[dim]Enter a 6-digit code or type 'resend'.[/dim]")
            continue

        _log.info("submitting code len=%d via mfa/code/verify", len(code))
        try:
            r2 = _http_post(
                "verify",
                V2_MFA_VERIFY_URL,
                {"code": code, "method": "app"},
                extra_headers={"x-verify-id": auth_id},
            )
        except httpx.ConnectError:
            _log.error("verify: ConnectError")
            err.print("[red]Network error during verification.[/red]")
            raise typer.Exit(1)

        if r2.status_code != 200:
            _log.warning("verify: HTTP %s  body=%s", r2.status_code, r2.text[:500])
            err.print(f"[red]Verification failed ({r2.status_code}):[/red] {r2.text[:300]}")
            err.print("[dim]Try again or type 'resend'.[/dim]")
            continue

        data2 = r2.json()
        _log.debug("verify keys=%s | %s", list(data2.keys()),
                   json.dumps({k: ("***" if k in ("token",) else v) for k, v in data2.items()}))

        token = data2.get("token")
        if token:
            _log.info("verify: token obtained")
            return token

        err_msg = data2.get("errorMessage") or data2.get("errorCode") or str(data2)
        _log.warning("verify: code rejected: %s", data2)
        err.print(f"[red]Code rejected:[/red] {err_msg}")
        err.print("[dim]Try again or type 'resend'.[/dim]")


# ─── status ───────────────────────────────────────────────────────────────────

@app.command()
def status():
    """Show current credential status (.env on disk + runtime fallback)."""

    tbl = Table(
        title=f".env status  [dim]({_DOTENV_PATH})[/dim]",
        box=box.ROUNDED,
        show_lines=True,
        highlight=True,
    )
    tbl.add_column("Variable", style="bold cyan", no_wrap=True)
    tbl.add_column("Status")
    tbl.add_column("Value (masked)")
    tbl.add_column("Timing")

    def _row(key: str, present: bool, masked: str, *, timing: str = "[dim]n/a[/dim]"):
        status_str = "[green]✓ set[/green]" if present else "[red]✗ missing[/red]"
        tbl.add_row(key, status_str, masked, timing if present else "[dim]n/a[/dim]")

    service_status = get_status_payload()
    _row(
        ENV_API_TOKEN,
        service_status.api_token_present,
        service_status.api_token_masked,
        timing=service_status.api_timing,
    )
    _row(
        ENV_SESSION_TOKEN,
        service_status.session_token_present,
        service_status.session_token_masked,
        timing=service_status.session_timing,
    )

    console.print()
    console.print(tbl)
    console.print()

    if not _DOTENV_PATH.exists():
        console.print(f"[yellow]No .env file found at {_DOTENV_PATH}[/yellow]")
        if service_status.api_token_present or service_status.session_token_present:
            console.print("[dim]Using runtime environment fallback from the current process.[/dim]")
        else:
            console.print("[dim]Run any 'set' or 'refresh' command to create it.[/dim]")


# ─── token ────────────────────────────────────────────────────────────────────

@token_app.command("set")
def token_set(
    value: Annotated[Optional[str], typer.Argument(help="The API token value. Prompted if omitted.")] = None,
    expires_at: Annotated[
        Optional[str],
        typer.Option("--expires-at", help="Optional ISO-8601 expiration timestamp for the API token."),
    ] = None,
):
    """Set the V1 API token in .env (official API)."""
    if not value:
        value = typer.prompt(ENV_API_TOKEN, hide_input=True)
    result = service_set_api_token(value.strip(), expires_at=expires_at)
    console.print(f"[green]✓[/green] {ENV_API_TOKEN} updated in [dim]{result['env_path']}[/dim]")
    if expires_at:
        console.print(f"[dim]Expiration metadata saved: {result['timing']}[/dim]")


# ─── session ──────────────────────────────────────────────────────────────────

@session_app.command("set")
def session_set(
    value: Annotated[Optional[str], typer.Argument(help="The session cookie value. Prompted if omitted.")] = None,
    ttl_days: Annotated[
        Optional[int],
        typer.Option("--ttl-days", min=1, help="Optional session validity window in days for status reporting."),
    ] = None,
    expires_at: Annotated[
        Optional[str],
        typer.Option("--expires-at", help="Optional ISO-8601 expiration timestamp for the session token."),
    ] = None,
):
    """
    Set the V2 session token directly in .env (web API).

    Use this when you have already fetched the token yourself
    (e.g., from browser DevTools → Application → Cookies → 't').
    """
    if not value:
        value = typer.prompt(ENV_SESSION_TOKEN, hide_input=True)
    result = service_set_session_token(value.strip(), ttl_days=ttl_days, expires_at=expires_at)
    console.print(f"[green]✓[/green] {ENV_SESSION_TOKEN} updated in [dim]{result['env_path']}[/dim]")
    if result["timing"] != "no expiration metadata":
        console.print(f"[dim]Expiration metadata saved: {result['timing']}[/dim]")


@session_app.command("refresh")
def session_refresh(
    username: Annotated[Optional[str], typer.Option("--username", "-u", help="TickTick account email.")] = None,
):
    """
    Fetch a fresh V2 session token by logging in with username + password.

    Credentials are [bold]never stored[/bold] — only the resulting token is
    written to .env. On next expiration (~30 days), run this command again.

    The password is always prompted interactively (not echoed to the terminal).
    """
    console.print()
    console.print("[bold]V2 Session Token — Auto-refresh[/bold]")
    console.print("[dim]Credentials are used once and then discarded. Only the token is saved.[/dim]")
    console.print()

    if not username:
        username = typer.prompt("TickTick username (email)")

    password = typer.prompt("TickTick password", hide_input=True)

    console.print("[dim]Logging in…[/dim]", end=" ")
    token = _v2_login(username.strip(), password)
    console.print("[green]✓[/green]")

    now = _now_utc()
    expires_at = now + APPROX_SESSION_TTL
    result = service_set_session_token(token, ttl_days=30)
    console.print(f"[green]✓[/green] {ENV_SESSION_TOKEN} updated in [dim]{result['env_path']}[/dim]")
    console.print(f"[dim]Token value: {_mask(token)}[/dim]")
    console.print(f"[dim]Approximate expiration: {_format_timestamp(expires_at)} ({_format_remaining(expires_at, approximate=True)} left)[/dim]")
    console.print()
    console.print("[dim]The MCP server will pick it up automatically on next restart (or hot-reload if supported).[/dim]")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()
