"""
GitHubAuth — Single-flow Device Flow authentication for Developer Tools.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path
from typing import Callable, Optional

from ....core.controllers.logging.manager import APFLogManager
logger = APFLogManager.get_logger(__name__)

CLIENT_ID = "Iv23lit3nZrD90Tu2AG2"

_USER_TOKEN_PATH = Path.home() / ".apf_manager" / "github_token.json"


class GitHubAuth:
    """
    Manages GitHub Device Flow authentication (single-tier).

    Thread-safe: login_async() runs the flow in a background thread.
    All callbacks are called from that background thread — callers must
    dispatch UI updates to the main thread (e.g. via Clock.schedule_once).
    """

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._username: Optional[str] = None
        self._permission: Optional[str] = None
        self._load_saved_token()

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

    def login_async(
        self,
        repo_owner: str,
        repo_name: str,
        on_code: Callable[[str, str], None],
        on_complete: Callable[[bool, str], None],
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not CLIENT_ID:
            on_complete(False, "CLIENT_ID not set.")
            return

        _log = log_fn or (lambda msg: None)

        def _run():
            try:
                token = _do_device_flow(CLIENT_ID, on_code, _log, scopes=[])
                self._token = token
                self._save_token()
                ok = self._fetch_user_info(token, repo_owner, repo_name)
                on_complete(ok, self._username or "unknown")
            except Exception as exc:
                on_complete(False, str(exc))

        threading.Thread(target=_run, daemon=True).start()

    def logout(self) -> None:
        self._token = None
        self._username = None
        self._permission = None
        if _USER_TOKEN_PATH.exists():
            try:
                _USER_TOKEN_PATH.unlink()
            except Exception as exc:
                logger.warning("[auth] Failed to remove token file at %s: %s", _USER_TOKEN_PATH, exc)

    def refresh_async(
        self,
        repo_owner: str,
        repo_name: str,
        on_complete: Callable[[bool], None],
    ) -> None:
        if not self._token:
            on_complete(False)
            return

        token = self._token

        def _run():
            ok = self._fetch_user_info(token, repo_owner, repo_name)
            on_complete(ok)

        threading.Thread(target=_run, daemon=True).start()

    def _load_saved_token(self) -> None:
        if not _USER_TOKEN_PATH.exists():
            return
        try:
            data = json.loads(_USER_TOKEN_PATH.read_text(encoding="utf-8"))
            self._token = (data.get("token") or data.get("write") or "").strip() or None
        except Exception:
            self._token = None

    def _save_token(self) -> None:
        try:
            _USER_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            _USER_TOKEN_PATH.write_text(
                json.dumps({"token": self._token or ""}, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("[auth] Failed to persist token to %s: %s", _USER_TOKEN_PATH, exc)

    def _fetch_user_info(self, token: Optional[str], repo_owner: str, repo_name: str) -> bool:
        if not token:
            return False
        try:
            from ....core.controllers.remote.github_api import GitHubAPI
            api = GitHubAPI(repo_owner, repo_name, direct_token=token)

            username = api.get_authenticated_user()
            if not username:
                self._permission = "none"
                return False
            self._username = username

            permission = api.get_collaborator_permission(repo_owner, repo_name, username)
            self._permission = permission or "read"
            return True
        except Exception:
            self._permission = "none"
            return False


def _do_device_flow(
    client_id: str,
    on_code: Callable[[str, str], None],
    log_fn: Callable[[str], None],
    scopes: list[str],
) -> str:
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

    gh = GitHub(OAuthDeviceAuthStrategy(client_id, _on_verification, scopes=scopes))
    token_strategy = gh.auth.exchange_token(gh)
    return token_strategy.token
