from __future__ import annotations

import subprocess
import threading
import webbrowser
from typing import Callable, Optional, TYPE_CHECKING

from ..auth import GitHubAuth
from ..ci import CIManager
from .. import version as vm
from .....core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)

if TYPE_CHECKING:
    from .....core.controllers.plugin_host import PluginHost


class SourceControlController:
    def __init__(
        self,
        ci: CIManager,
        auth: GitHubAuth,
        host: "PluginHost",
        repo_owner: str,
        repo_name: str,
    ) -> None:
        self._ci = ci
        self._auth = auth
        self._host = host
        self._repo_owner = repo_owner
        self._repo_name = repo_name

    def get_current_branch(self) -> Optional[str]:
        return vm.get_current_branch()

    def open_pr_in_browser(self, branch: str, title: str) -> None:
        url = (
            f"https://github.com/{self._repo_owner}/{self._repo_name}"
            f"/compare/{branch}?expand=1"
        )
        if title:
            url += f"&title={title.replace(' ', '+')}"
        try:
            webbrowser.open(url)
            logger.info(f"Opened PR page for branch '{branch}'.")
        except Exception as exc:
            logger.warning(f"Could not open browser ({exc}). URL: {url}")

    def refresh_branches(
        self,
        on_done: Callable[[Optional[list], Optional[str]], None],
    ) -> None:
        token = self._auth.token
        if not token:
            return

        def _fetch():
            try:
                branches = self._ci.list_branches(token)
                on_done(branches, None)
            except Exception as exc:
                logger.error(f"Failed to fetch branches: {exc}")
                on_done(None, str(exc))

        threading.Thread(target=_fetch, daemon=True).start()

    def create_branch(
        self,
        name: str,
        on_done: Callable[[bool, str], None],
    ) -> None:
        token = self._auth.token
        if not token:
            return

        busy = self._host.get_service("busy")
        if busy:
            busy.set_busy("devtools.sc.branch", f"Creating branch '{name}'…")

        def _wrapped_done(ok: bool, result: str) -> None:
            if busy:
                busy.clear_busy("devtools.sc.branch")
            on_done(ok, result)

        def _run():
            try:
                sha = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(vm._REPO_ROOT), text=True, stderr=subprocess.STDOUT,
                ).strip()
                ok = self._ci.create_branch(name, sha, token)
                _wrapped_done(ok, name)
            except Exception as exc:
                logger.error(f"Error creating branch '{name}': {exc}")
                _wrapped_done(False, str(exc))

        threading.Thread(target=_run, daemon=True).start()

    def delete_branch(
        self,
        name: str,
        on_done: Callable[[bool, str], None],
    ) -> None:
        token = self._auth.token
        if not token:
            return

        busy = self._host.get_service("busy")
        if busy:
            busy.set_busy("devtools.sc.branch", f"Deleting branch '{name}'…")

        def _wrapped_done(ok: bool, result: str) -> None:
            if busy:
                busy.clear_busy("devtools.sc.branch")
            on_done(ok, result)

        def _run():
            try:
                ok = self._ci.delete_branch(name, token)
                _wrapped_done(ok, name)
            except Exception as exc:
                logger.error(f"Error deleting branch '{name}': {exc}")
                _wrapped_done(False, str(exc))

        threading.Thread(target=_run, daemon=True).start()
