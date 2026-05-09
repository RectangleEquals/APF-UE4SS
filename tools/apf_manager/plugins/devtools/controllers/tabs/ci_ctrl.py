from __future__ import annotations

import threading
from typing import Callable, Optional, TYPE_CHECKING

from ..auth import GitHubAuth
from ..ci import CIManager
from .. import version as vm
from .....core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)

if TYPE_CHECKING:
    from .....core.controllers.plugin_host import PluginHost


class CITabController:
    def __init__(self, ci: CIManager, auth: GitHubAuth, host: "PluginHost") -> None:
        self._ci = ci
        self._auth = auth
        self._host = host

    def get_current_branch(self) -> str:
        return vm.get_current_branch() or "master"

    def refresh_workflows(
        self,
        on_done: Callable[[Optional[list], Optional[str]], None],
    ) -> None:
        token = self._auth.token
        if not token:
            return
        logger.info("Fetching workflows...")

        def _fetch():
            try:
                workflows = self._ci.list_workflows(token)
                logger.info(f"list_workflows returned {len(workflows)} item(s).")
                on_done(workflows, None)
            except Exception as exc:
                logger.error(f"Failed to fetch workflows: {exc}")
                on_done(None, str(exc))

        threading.Thread(target=_fetch, daemon=True).start()

    def dispatch_workflow(
        self,
        wf_id: str,
        branch: str,
        on_status: Callable[[str], None],
    ) -> None:
        token = self._auth.token
        if not token:
            return
        self._ci.dispatch_workflow(wf_id, branch, token, on_status)

    def refresh_releases(
        self,
        on_done: Callable[[Optional[list], Optional[str]], None],
    ) -> None:
        token = self._auth.token
        if not token:
            return
        logger.info("Fetching releases...")

        def _fetch():
            try:
                releases = self._ci.list_releases(token)
                on_done(releases, None)
            except Exception as exc:
                logger.error(f"Failed to fetch releases: {exc}")
                on_done(None, str(exc))

        threading.Thread(target=_fetch, daemon=True).start()

    def fetch_unreleased_tags(
        self,
        on_done: Callable[[Optional[list], Optional[str]], None],
    ) -> None:
        token = self._auth.token
        if not token:
            return
        logger.info("Fetching tags for release dialog...")

        def _fetch():
            try:
                tags = self._ci.list_tags(token)
                releases = self._ci.list_releases(token)
                released = {r["tag_name"] for r in releases}
                unreleased = [t for t in tags if t not in released]
                on_done(unreleased, None)
            except Exception as exc:
                logger.error(f"Failed to fetch tags: {exc}")
                on_done(None, str(exc))

        threading.Thread(target=_fetch, daemon=True).start()

    def create_release(
        self,
        tag: str,
        name: str,
        notes: str,
        on_done: Callable[[bool, str, str], None],
    ) -> None:
        token = self._auth.token
        if not token:
            return
        logger.info(f"Creating release for tag '{tag}'...")

        def _run():
            try:
                rel = self._ci.create_release(tag, name, notes, token)
                url = rel.get("html_url", "")
                on_done(True, "", url)
            except Exception as exc:
                logger.error(f"Failed to create release '{tag}': {exc}")
                on_done(False, str(exc), "")

        threading.Thread(target=_run, daemon=True).start()
