"""
GitHubAuth — OAuth2 Device Flow login/logout for Developer Tools.

Uses githubkit's native OAuthDeviceAuthStrategy (RFC 8628):
  1. GitHub sends a user_code + verification_uri via the on_verification callback
  2. App shows the code to the user and opens the browser
  3. githubkit handles all polling internally until the user approves or the flow expires
  4. Token stored in ~/.apf_manager/github_token.json

CLIENT_ID: create a GitHub OAuth App at https://github.com/settings/developers
  → New OAuth App → set callback URL to http://localhost (unused for Device Flow)
  → Copy the Client ID and paste it below.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# TODO: Replace with your GitHub OAuth App's Client ID.
# Create one at: https://github.com/settings/developers → OAuth Apps → New OAuth App
# Callback URL: http://localhost (not used by Device Flow, but required by GitHub)
# The Client ID is NOT a secret — it is safe to hardcode here.
# ---------------------------------------------------------------------------
CLIENT_ID = "Ov23lijlXQq4YkbulXPH"

_USER_TOKEN_PATH = Path.home() / ".apf_manager" / "github_token.json"


class GitHubAuth:
    """
    Manages GitHub OAuth2 Device Flow authentication.

    Thread-safe: login_async() runs the flow in a background thread.
    All callbacks are called from that background thread — callers must
    dispatch UI updates to the main thread (e.g. via Clock.schedule_once).
    """

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._username: Optional[str] = None
        self._permission: Optional[str] = None   # "admin" | "write" | "read" | "none"
        self._load_saved_token()

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

    @property
    def is_logged_in(self) -> bool:
        return bool(self._token)

    @property
    def token(self) -> Optional[str]:
        return self._token

    @property
    def username(self) -> Optional[str]:
        return self._username

    @property
    def permission(self) -> Optional[str]:
        return self._permission

    @property
    def is_write_tier(self) -> bool:
        return self._permission in ("admin", "write")

    # -----------------------------------------------------------------------
    # Login
    # -----------------------------------------------------------------------

    def login_async(
        self,
        repo_owner: str,
        repo_name: str,
        on_code: Callable[[str, str], None],
        on_complete: Callable[[bool, str], None],
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Start Device Flow in a background thread.

        on_code(user_code, verification_uri) — called when the 8-char code is ready.
        on_complete(success, username_or_error) — called when auth finishes or fails.
        log_fn — optional thread-safe logger; used to report browser-open status.
        """
        if not CLIENT_ID:
            on_complete(False, "CLIENT_ID not set. See plugins/devtools/github_auth.py.")
            return

        _log = log_fn or (lambda msg: None)

        def _run():
            try:
                token = _do_device_flow(CLIENT_ID, on_code, _log)
                _USER_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
                _USER_TOKEN_PATH.write_text(
                    json.dumps({"token": token}, indent=2), encoding="utf-8"
                )
                self._token = token
                ok = self._fetch_user_info(token, repo_owner, repo_name)
                on_complete(ok, self._username or "unknown")
            except Exception as exc:
                on_complete(False, str(exc))

        threading.Thread(target=_run, daemon=True).start()

    # -----------------------------------------------------------------------
    # Logout
    # -----------------------------------------------------------------------

    def logout(self) -> None:
        if _USER_TOKEN_PATH.exists():
            try:
                _USER_TOKEN_PATH.unlink()
            except Exception:
                # Non-fatal — token is still cleared from memory below
                pass
        self._token = None
        self._username = None
        self._permission = None

    # -----------------------------------------------------------------------
    # Re-check permissions (call after login or on panel activate)
    # -----------------------------------------------------------------------

    def refresh_async(
        self,
        repo_owner: str,
        repo_name: str,
        on_complete: Callable[[bool], None],
    ) -> None:
        """Re-fetch username + permission for the stored token in a background thread."""
        if not self._token:
            on_complete(False)
            return

        def _run():
            ok = self._fetch_user_info(self._token, repo_owner, repo_name)
            on_complete(ok)

        threading.Thread(target=_run, daemon=True).start()

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _load_saved_token(self) -> None:
        if _USER_TOKEN_PATH.exists():
            try:
                data = json.loads(_USER_TOKEN_PATH.read_text(encoding="utf-8"))
                self._token = data.get("token", "").strip() or None
            except Exception:
                self._token = None

    def _fetch_user_info(self, token: str, repo_owner: str, repo_name: str) -> bool:
        """Synchronously fetch username + collaborator permission. Returns True on success."""
        try:
            from githubkit import GitHub, TokenAuthStrategy
            gh = GitHub(TokenAuthStrategy(token))

            user_resp = gh.rest.users.get_authenticated()
            self._username = user_resp.parsed_data.login

            try:
                perm_resp = gh.rest.repos.get_collaborator_permission_level(
                    repo_owner, repo_name, self._username
                )
                self._permission = perm_resp.parsed_data.permission
            except Exception:
                # Not a collaborator — treat as read-only
                self._permission = "read"

            return True
        except Exception:
            self._permission = "none"
            return False


# ---------------------------------------------------------------------------
# Device Flow — uses githubkit's native OAuthDeviceAuthStrategy
# ---------------------------------------------------------------------------

def _do_device_flow(
    client_id: str,
    on_code: Callable[[str, str], None],
    log_fn: Callable[[str], None],
) -> str:
    """
    Execute GitHub Device Flow and return the access token string.
    Raises on failure, access denial, or timeout.

    on_code(user_code, verification_uri) is called when the code is ready.
    log_fn is called if the browser cannot be opened automatically so the
    user knows to visit the URL manually.
    """
    from githubkit import GitHub
    from githubkit.auth.oauth import OAuthDeviceAuthStrategy

    def _on_verification(data: dict) -> None:
        uri = data.get("verification_uri", "https://github.com/login/device")
        on_code(data["user_code"], uri)
        try:
            webbrowser.open(uri)
        except Exception as exc:
            log_fn(
                f"[devtools] Could not open browser automatically ({exc}). "
                f"Please visit {uri} manually and enter the code shown."
            )

    gh = GitHub(OAuthDeviceAuthStrategy(client_id, _on_verification, scopes=["repo"]))
    # exchange_token() handles all polling, slow_down back-off, and expiry internally.
    # Raises RuntimeError on access_denied / expired_token, TimeoutError on expiry.
    token_strategy = gh.auth.exchange_token(gh)
    return token_strategy.token
