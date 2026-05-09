from __future__ import annotations

import threading
from typing import Callable, Optional, TYPE_CHECKING

from ..auth import GitHubAuth
from ..ci import CIManager
from .. import version as vm
from .....core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)

_COMPONENTS = ("framework", "manager", "apworld")

if TYPE_CHECKING:
    from .....core.controllers.plugin_host import PluginHost


class VersionsController:
    def __init__(self, ci: CIManager, auth: GitHubAuth, host: "PluginHost") -> None:
        self._ci = ci
        self._auth = auth
        self._host = host
        self._local_versions: dict[str, Optional[str]] = {}
        self._bump_parts: dict[str, str] = {c: "patch" for c in _COMPONENTS}

    def is_repo_valid(self) -> bool:
        return vm.is_repo_valid()

    def load_local_versions(self) -> dict[str, Optional[str]]:
        self._local_versions = vm.get_all_versions()
        return dict(self._local_versions)

    def set_bump_part(self, component: str, part: str) -> None:
        self._bump_parts[component] = part

    def get_bump_part(self, component: str) -> str:
        return self._bump_parts.get(component, "patch")

    def refresh_remote_versions(
        self,
        on_done: Callable[[Optional[dict], Optional[str]], None],
    ) -> None:
        token = self._auth.token
        if not token:
            return

        def _fetch():
            try:
                tags = self._ci.list_tags(token)
                remote: dict[str, Optional[str]] = {}
                for component in _COMPONENTS:
                    prefix = f"{component}/v"
                    comp_tags = sorted(t for t in tags if t.startswith(prefix))
                    remote[component] = comp_tags[-1].removeprefix(prefix) if comp_tags else None
                on_done(remote, None)
            except Exception as exc:
                logger.error(f"Failed to fetch remote tags: {exc}")
                on_done(None, str(exc))

        threading.Thread(target=_fetch, daemon=True).start()

    def commit_and_tag(
        self,
        component: str,
        on_done: Callable[[bool, str, str], None],
    ) -> None:
        current = self._local_versions.get(component)
        if not current:
            on_done(False, f"Cannot read {component} version.", "")
            return
        part = self._bump_parts.get(component, "patch")
        new_ver = vm.bump_version(current, part)

        if not vm.set_version(component, new_ver):
            on_done(False, f"Failed to write {component} version.", "")
            return

        self._local_versions[component] = new_ver
        logger.info(f"{component}: {current} -> {new_ver} -- committing...")

        def _run():
            try:
                ok, err = vm.commit_and_tag(component, new_ver)
                on_done(ok, err, new_ver)
            except Exception as exc:
                on_done(False, str(exc), new_ver)

        threading.Thread(target=_run, daemon=True).start()
