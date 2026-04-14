"""
UpdatesService — checks for and surfaces updates to the app, framework binaries, and APWorld.

Registered as the "updates" service. Works for all users (player/dev/devtools).

Three independently versioned components:
  - Manager (APF Manager app):  manager/vX.Y.Z tag → .exe installer asset
  - Framework (C++ DLLs):       framework/vX.Y.Z tag → zip of binaries
  - APWorld (.apworld file):    apworld/vX.Y.Z tag → .apworld asset
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, Callable


_WORLDS_DIR = Path.home() / ".apf_manager" / "worlds"
_CHECK_INTERVAL = 3600  # 1 hour in-memory cache for update checks


class UpdatesService:
    def __init__(self, host) -> None:
        self._host = host
        self._lock = threading.Lock()
        self._last_check_time: float = 0.0
        self._app_update: Optional[dict] = None
        self._framework_update: Optional[dict] = None
        self._apworld_update: Optional[dict] = None

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def check_all(self, on_done: Optional[Callable] = None) -> None:
        """Run all update checks in the background. Calls on_done() on completion."""
        def _bg():
            import time
            with self._lock:
                now = time.time()
                if now - self._last_check_time < _CHECK_INTERVAL:
                    if on_done:
                        _ui(on_done)
                    return

            self._check_app_update()
            self._check_apworld_update()
            # Framework update is game-specific — checked separately via check_framework_update()

            with self._lock:
                import time as _t
                self._last_check_time = _t.time()

            if on_done:
                _ui(on_done)

        threading.Thread(target=_bg, daemon=True).start()

    def check_framework_update(self, game_id: str, on_done: Optional[Callable] = None) -> None:
        """Check for framework update for the current game. Separate from check_all()."""
        def _bg():
            self._check_framework_update_bg(game_id)
            if on_done:
                _ui(on_done)

        threading.Thread(target=_bg, daemon=True).start()

    def get_app_update(self) -> Optional[dict]:
        """Return app update info or None if current / not yet checked."""
        with self._lock:
            return self._app_update

    def get_framework_update(self) -> Optional[dict]:
        """Return framework update info or None if current / not yet checked / no UE4SS."""
        with self._lock:
            return self._framework_update

    def get_apworld_update(self) -> Optional[dict]:
        """Return APWorld update info or None if current / not yet checked."""
        with self._lock:
            return self._apworld_update

    def get_framework_other_entries(self) -> list:
        """Return _OtherEntry objects for available framework binary releases.
        Called by content_tab to populate the Other section alongside UE4SS entries.
        Returns up to 3 latest releases tagged framework/vX.Y.Z."""
        try:
            from ..mods.registry_service import _OtherEntry
            api = self._make_api()
            releases = api.list_releases(tag_prefix="framework/")
            entries = []
            for release in releases[:3]:
                full_tag = release.get("tag_name", "")
                asset = self._find_asset(release, ".zip")
                if not asset:
                    continue
                ver = full_tag[len("framework/"):] if full_tag.startswith("framework/") else full_tag
                entries.append(_OtherEntry(
                    name         = f"APF Framework Binaries {ver}",
                    note         = (release.get("body") or "")[:200],
                    type         = "github_release",
                    owner        = "RectangleEquals",
                    repo         = "APF-UE4SS",
                    tag          = full_tag,
                    url          = "",
                    install_type = "framework_binary",
                ))
            return entries
        except Exception:
            return []

    def download_update(
        self,
        component: str,
        dest: Path,
        progress_cb: Optional[Callable[[float], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        """
        Download an update asset for the given component ("app", "framework", "apworld").
        Runs in background; calls on_done(success, message) on completion.
        """
        with self._lock:
            info = {
                "app": self._app_update,
                "framework": self._framework_update,
                "apworld": self._apworld_update,
            }.get(component)

        if not info:
            if on_done:
                _ui(lambda: on_done(False, f"No update available for '{component}'."))
            return

        asset_url = info.get("asset_url", "")
        if not asset_url:
            if on_done:
                _ui(lambda: on_done(False, "No asset URL available."))
            return

        def _bg():
            try:
                api = self._make_api()
                dest.parent.mkdir(parents=True, exist_ok=True)
                api.download_asset(asset_url, dest, progress_cb=progress_cb)
                _ui(lambda: on_done(True, f"Downloaded to {dest.name}.") if on_done else None)
            except Exception as exc:
                _ui(lambda: on_done(False, str(exc)) if on_done else None)

        threading.Thread(target=_bg, daemon=True).start()

    # -----------------------------------------------------------------------
    # Internal checks
    # -----------------------------------------------------------------------

    def _check_app_update(self) -> None:
        try:
            from ...__version__ import __version__ as current_version
            from ...core.semver import SemVer
            latest_info = self._get_latest_release("manager")
            if not latest_info:
                return
            latest_ver = latest_info.get("tag_name", "").lstrip("v")
            current = SemVer.parse(current_version)
            latest = SemVer.parse(latest_ver)
            if current and latest and latest > current:
                asset = self._find_asset(latest_info, ".exe")
                with self._lock:
                    self._app_update = {
                        "current": current_version,
                        "latest": latest_ver,
                        "asset_url": asset.get("browser_download_url", "") if asset else "",
                        "changelog": latest_info.get("body", ""),
                    }
        except Exception:
            pass

    def _check_framework_update_bg(self, game_id: str) -> None:
        try:
            from ...core.semver import SemVer
            detection = self._host.get_detection()
            if not detection or not detection.valid:
                with self._lock:
                    self._framework_update = None
                return

            # Find installed framework version from mod service
            mods_svc = self._host.get_service("mods")
            current_version = "0.0.0"
            if mods_svc:
                for mod in mods_svc.get_ap_mods():
                    if mod.mod_id and mod.mod_id.endswith(".framework"):
                        current_version = mod.version or "0.0.0"
                        break

            latest_info = self._get_latest_release("framework")
            if not latest_info:
                return
            latest_ver = latest_info.get("tag_name", "").lstrip("v")
            current = SemVer.parse(current_version)
            latest = SemVer.parse(latest_ver)
            if current and latest and latest > current:
                asset = self._find_asset(latest_info, ".zip")
                with self._lock:
                    self._framework_update = {
                        "current": current_version,
                        "latest": latest_ver,
                        "asset_url": asset.get("browser_download_url", "") if asset else "",
                        "changelog": latest_info.get("body", ""),
                    }
        except Exception:
            pass

    def _check_apworld_update(self) -> None:
        try:
            from ...core.semver import SemVer
            # Find installed apworld version from worlds dir
            current_version = self._get_installed_apworld_version()

            latest_info = self._get_latest_release("apworld")
            if not latest_info:
                return
            latest_ver = latest_info.get("tag_name", "").lstrip("v")
            current = SemVer.parse(current_version)
            latest = SemVer.parse(latest_ver)
            if current and latest and latest > current:
                asset = self._find_asset(latest_info, ".apworld")
                with self._lock:
                    self._apworld_update = {
                        "current": current_version,
                        "latest": latest_ver,
                        "asset_url": asset.get("browser_download_url", "") if asset else "",
                        "changelog": latest_info.get("body", ""),
                    }
        except Exception:
            pass

    def _get_latest_release(self, component: str) -> Optional[dict]:
        """Fetch the latest GitHub release for the given component tag prefix."""
        try:
            api = self._make_api()
            releases = api.list_releases(tag_prefix=f"{component}/")
            return releases[0] if releases else None
        except Exception:
            return None

    def _get_installed_apworld_version(self) -> str:
        """Scan worlds dir for installed apworld and return its version string."""
        if not _WORLDS_DIR.is_dir():
            return "0.0.0"
        for f in _WORLDS_DIR.iterdir():
            if f.suffix == ".apworld":
                # Try to parse version from filename e.g. apf-1.2.3.apworld
                parts = f.stem.rsplit("-", 1)
                if len(parts) == 2:
                    return parts[1]
        return "0.0.0"

    @staticmethod
    def _find_asset(release_info: dict, suffix: str) -> Optional[dict]:
        for asset in release_info.get("assets", []):
            if asset.get("name", "").endswith(suffix):
                return asset
        return None

    def _make_api(self):
        from ...core.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH
        # Use the APF repo as the default owner/repo for release checks
        return GitHubAPI(
            repo_owner="RectangleEquals",
            repo_name="APF-UE4SS",
            token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
            on_status=lambda level, msg: None,
        )


def _ui(fn: Callable) -> None:
    from kivy.clock import Clock
    Clock.schedule_once(lambda dt: fn(), 0)
