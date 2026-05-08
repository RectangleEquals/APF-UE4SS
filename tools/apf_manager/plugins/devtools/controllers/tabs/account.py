from __future__ import annotations

from typing import Callable, Optional, Tuple, TYPE_CHECKING

from ..auth import GitHubAuth

if TYPE_CHECKING:
    from .....core.controllers.plugin_host import PluginHost


class AccountController:
    def __init__(
        self,
        auth: GitHubAuth,
        host: "PluginHost",
        repo_owner: str,
        repo_name: str,
    ) -> None:
        self._auth = auth
        self._host = host
        self._repo_owner = repo_owner
        self._repo_name = repo_name

    @property
    def is_logged_in(self) -> bool:
        return self._auth.is_logged_in

    @property
    def is_write_tier(self) -> bool:
        return self._auth.is_write_tier

    @property
    def username(self) -> Optional[str]:
        return self._auth.username

    @property
    def permission(self) -> Optional[str]:
        return self._auth.permission

    @property
    def token(self) -> Optional[str]:
        return self._auth.token

    def refresh_async(self, on_complete: Callable[[bool], None]) -> None:
        self._auth.refresh_async(self._repo_owner, self._repo_name, on_complete)

    def start_login(
        self,
        on_code: Callable[[str, str], None],
        on_complete: Callable[[bool, str], None],
    ) -> None:
        self._auth.login_async(
            self._repo_owner, self._repo_name,
            on_code=on_code,
            on_complete=on_complete,
            log_fn=self._host.log,
        )

    def logout(self) -> None:
        self._auth.logout()

    def propagate_token(self) -> None:
        try:
            svc = self._host.get_service("docs_viewer")
            if svc and hasattr(svc, "_api") and svc._api:
                svc._api.refresh_auth()
        except Exception as exc:
            self._host.log(f"[devtools] Could not propagate token: {exc}")

    def propagate_token_clear(self) -> None:
        try:
            svc = self._host.get_service("docs_viewer")
            if svc and hasattr(svc, "_api") and svc._api:
                svc._api.clear_user_token()
        except Exception as exc:
            self._host.log(f"[devtools] Could not clear token: {exc}")

    def get_rate_limit_info(self) -> Tuple:
        from .....core.controllers.remote.github_api import GitHubAPI
        return (
            GitHubAPI.get_global_rate_limit_info(),
            GitHubAPI.get_global_search_rate_limit_info(),
        )
