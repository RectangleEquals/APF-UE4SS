"""
UpdatesService — checks for and surfaces updates to the app, framework
binaries, APWorld, and UE4SS.

Registered as the "updates" service by plugins/updates/__init__.py.
check_all() is triggered once on app startup (via __init__.py setup()).

Components tracked:
  - manager   (APF Manager app):   manager/vX.Y.Z tag  → .exe installer asset
  - framework (C++ DLLs):          framework/vX.Y.Z tag → zip of binaries
  - apworld   (.apworld file):      apworld/vX.Y.Z tag   → .apworld asset
  - ue4ss     (UE4SS runtime):      UE4SS-RE/RE-UE4SS latest stable + pre-release

Two GitHubAPI instances are used:
  - _make_apf_api()   → RectangleEquals/APF-UE4SS   (manager, framework, apworld)
  - _make_ue4ss_api() → UE4SS-RE/RE-UE4SS            (default UE4SS check)

Per-game / per-registry UE4SS overrides (arbitrary owner/repo) are handled
by _make_ue4ss_api(owner, repo) — created on demand, cached separately.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

from ...core.remote.github_release_manager import RepoRelease
from ..content.shared import GithubReleaseBinary, ContentAsset, ReleaseSource, GitHubRepo, ContentTags


_WORLDS_DIR      = Path.home() / ".apf_manager" / "worlds"


def _hash_other(owner: str, repo: str, tag: str, install_type: str) -> str:
    """Compute a short SHA-256 content hash matching _compute_other_entry_hash logic."""
    import hashlib
    fingerprint = "|".join([owner, repo, tag, install_type, "", "", "github_release"])
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:20]
_CHECK_INTERVAL  = 3600   # 1-hour in-memory TTL for update checks

# How many stable UE4SS releases to surface in the Content tab Other section
_UE4SS_STABLE_COUNT = 1


# ---------------------------------------------------------------------------
# UpdateInfo dataclass
# ---------------------------------------------------------------------------

@dataclass
class UpdateInfo:
    """Typed update state for a single component."""
    component: str                          # "manager" | "framework" | "apworld" | "ue4ss"
    current: str                            # installed version string, or "unknown"
    latest_stable: Optional[RepoRelease]    # None if not yet checked / unavailable
    latest_pre: Optional[RepoRelease]       # None if no pre-release available
    asset_url: str = ""                     # primary download URL (stable)
    is_update_available: bool = False       # True when latest_stable > current
    is_pre_available: bool = False          # True when latest_pre exists


# ---------------------------------------------------------------------------
# UpdatesService
# ---------------------------------------------------------------------------

class UpdatesService:
    def __init__(self, host) -> None:
        self._host = host
        self._lock = threading.Lock()
        self._last_check_time: float = 0.0

        # Per-component UpdateInfo (None = not yet checked)
        self._manager_info:   Optional[UpdateInfo] = None
        self._framework_info: Optional[UpdateInfo] = None
        self._apworld_info:   Optional[UpdateInfo] = None
        self._ue4ss_info:     Optional[UpdateInfo] = None

        # Cache for arbitrary UE4SS owner/repo overrides
        # key = "owner/repo" → UpdateInfo
        self._ue4ss_override_cache: dict[str, UpdateInfo] = {}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def check_all(self, on_done: Optional[Callable] = None) -> None:
        """
        Run all update checks in the background.
        Respects the 1-hour TTL — no-ops if checked recently.
        Calls on_done() on the Kivy main thread when complete.
        """
        def _bg():
            import time
            with self._lock:
                now = time.time()
                if now - self._last_check_time < _CHECK_INTERVAL:
                    if on_done:
                        _ui(on_done)
                    return

            self._check_manager()
            self._check_apworld()
            self._check_ue4ss()
            # Framework is game-specific — checked separately via check_framework()

            with self._lock:
                import time as _t
                self._last_check_time = _t.time()

            if on_done:
                _ui(on_done)

        threading.Thread(target=_bg, daemon=True).start()

    def check_framework(self, game_id: str,
                        on_done: Optional[Callable] = None) -> None:
        """Check for framework binary update for the current game."""
        def _bg():
            self._check_framework_bg(game_id)
            if on_done:
                _ui(on_done)
        threading.Thread(target=_bg, daemon=True).start()

    def get_update_info(self, component: str) -> Optional[UpdateInfo]:
        """
        Return typed UpdateInfo for the given component, or None if not yet checked.

        component: "manager" | "framework" | "apworld" | "ue4ss"
        """
        with self._lock:
            return {
                "manager":   self._manager_info,
                "framework": self._framework_info,
                "apworld":   self._apworld_info,
                "ue4ss":     self._ue4ss_info,
            }.get(component)

    def get_ue4ss_update_info_for(self, owner: str,
                                  repo: str) -> Optional[UpdateInfo]:
        """
        Return UpdateInfo for an arbitrary UE4SS owner/repo override.
        Returns None if not yet checked for this repo.
        """
        key = f"{owner}/{repo}"
        with self._lock:
            return self._ue4ss_override_cache.get(key)

    def check_ue4ss_for(self, owner: str, repo: str,
                        on_done: Optional[Callable] = None) -> None:
        """Check for a UE4SS update from an arbitrary owner/repo."""
        def _bg():
            info = self._run_ue4ss_check(owner, repo)
            key = f"{owner}/{repo}"
            with self._lock:
                self._ue4ss_override_cache[key] = info
            if on_done:
                _ui(on_done)
        threading.Thread(target=_bg, daemon=True).start()

    def get_framework_releases_for_content(self) -> list:
        """
        Return GithubReleaseBinary objects for available framework binary releases.
        Called by ContentTab to populate the Other section.
        Returns up to 3 latest stable releases tagged framework/vX.Y.Z.
        """
        try:
            api = self._make_apf_api()
            releases = api.list_releases(tag_prefix="framework/")
            entries = []
            for release in releases[:3]:
                full_tag = release.get("tag_name", "")
                asset = self._find_asset_dict(release, ".zip")
                if not asset:
                    continue
                ver = (full_tag[len("framework/"):]
                       if full_tag.startswith("framework/") else full_tag)
                body = (release.get("body") or "")
                _assets = [
                    ContentAsset(
                        name=a.get("name", ""),
                        url=a.get("browser_download_url", ""),
                        size_bytes=a.get("size", 0),
                        selected=False,
                    )
                    for a in release.get("assets", [])
                    if not (
                        a.get("name", "").endswith(".exe") or
                        a.get("name", "").endswith(".apworld")
                    )
                ]
                _hash = _hash_other("RectangleEquals", "APF-UE4SS", full_tag, "framework_binary")
                source = ReleaseSource(
                    repo=GitHubRepo(owner="RectangleEquals", repo="APF-UE4SS"),
                    tag=full_tag,
                    published_at=release.get("published_at", ""),
                    changelog=body[:2000],
                    is_prerelease=False,
                )
                _entry = GithubReleaseBinary(
                    name=f"APF Framework \u2022 {ver}",
                    version=ver,
                    game_id="",
                    install_type="framework_binary",
                    assets=_assets,
                    source=source,
                    tags=ContentTags(content_hash=_hash),
                )
                entries.append(_entry)
            return entries
        except Exception:
            return []

    def get_ue4ss_releases_for_content(self, owner: str = "UE4SS-RE",
                                        repo: str = "RE-UE4SS") -> list:
        """
        Return GithubReleaseBinary objects for UE4SS releases from owner/repo.
        Returns up to _UE4SS_STABLE_COUNT latest stable releases + latest
        experimental (pre-release) if one exists.

        Called by ContentTab to populate the Other section. Always returns
        entries even if no registry is configured (bootstrap path).
        """
        try:
            api = self._make_ue4ss_api(owner, repo)
            typed_releases = api.releases.fetch_all()

            stable       = [r for r in typed_releases if not r.prerelease and not r.draft]
            experimental = [r for r in typed_releases if r.prerelease and not r.draft]

            entries = []
            for r in stable[:_UE4SS_STABLE_COUNT]:
                _assets = [
                    ContentAsset(
                        name=a.name,
                        url=a.browser_download_url,
                        size_bytes=getattr(a, "size", 0),
                        selected=False,
                    )
                    for a in r.assets
                ]
                _hash = _hash_other(owner, repo, r.tag_name, "ue4ss")
                source = ReleaseSource(
                    repo=GitHubRepo(owner=owner, repo=repo),
                    tag=r.tag_name,
                    published_at=r.published_at.isoformat() if r.published_at else "",
                    changelog=(r.body or "")[:2000],
                    is_prerelease=False,
                )
                _entry = GithubReleaseBinary(
                    name=f"{repo} \u2022 {r.tag_name}",
                    version=r.tag_name.lstrip("v"),
                    game_id="",
                    install_type="ue4ss",
                    assets=_assets,
                    source=source,
                    tags=ContentTags(content_hash=_hash),
                )
                entries.append(_entry)

            if experimental:
                r = experimental[0]
                _assets = [
                    ContentAsset(
                        name=a.name,
                        url=a.browser_download_url,
                        size_bytes=getattr(a, "size", 0),
                        selected=False,
                    )
                    for a in r.assets
                ]
                _hash = _hash_other(owner, repo, r.tag_name, "ue4ss")
                source = ReleaseSource(
                    repo=GitHubRepo(owner=owner, repo=repo),
                    tag=r.tag_name,
                    published_at=r.published_at.isoformat() if r.published_at else "",
                    changelog=(r.body or "")[:2000],
                    is_prerelease=True,
                )
                _entry = GithubReleaseBinary(
                    name=f"{repo} \u2022 {r.tag_name}",
                    version=r.tag_name.lstrip("v"),
                    game_id="",
                    install_type="ue4ss",
                    assets=_assets,
                    source=source,
                    tags=ContentTags(content_hash=_hash),
                )
                entries.append(_entry)
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
        Download an update asset for the given component.
        component: "manager" | "framework" | "apworld"
        Runs in background; calls on_done(success, message) on main thread.
        """
        with self._lock:
            info_map = {
                "manager":   self._manager_info,
                "framework": self._framework_info,
                "apworld":   self._apworld_info,
            }
            info = info_map.get(component)

        if not info or not info.asset_url:
            if on_done:
                _ui(lambda: on_done(False, f"No update available for '{component}'."))
            return

        def _bg():
            try:
                api = self._make_apf_api()
                dest.parent.mkdir(parents=True, exist_ok=True)
                api.download_asset(info.asset_url, dest, progress_cb=progress_cb)
                _ui(lambda: on_done(True, f"Downloaded to {dest.name}.") if on_done else None)
            except Exception as exc:
                _ui(lambda: on_done(False, str(exc)) if on_done else None)

        threading.Thread(target=_bg, daemon=True).start()

    # -----------------------------------------------------------------------
    # Internal checks
    # -----------------------------------------------------------------------

    def _check_manager(self) -> None:
        try:
            from ...__version__ import __version__ as current_version
            from ...core.semver import SemVer
            api = self._make_apf_api()
            latest = api.get_latest_release_typed()
            latest_pre = api.releases.fetch_latest_prerelease()

            # Strip "manager/" prefix from tag if present
            def _ver(r: Optional[RepoRelease]) -> str:
                if not r:
                    return ""
                return r.tag_name.split("/")[-1].lstrip("v")

            latest_ver = _ver(latest)
            current = SemVer.parse(current_version)
            new_stable = SemVer.parse(latest_ver)
            is_update = bool(current and new_stable and new_stable > current)

            asset_url = ""
            if is_update and latest:
                asset = next((a for a in latest.assets if a.name.endswith(".exe")), None)
                if asset:
                    asset_url = asset.browser_download_url

            info = UpdateInfo(
                component="manager",
                current=current_version,
                latest_stable=latest,
                latest_pre=latest_pre,
                asset_url=asset_url,
                is_update_available=is_update,
                is_pre_available=bool(latest_pre),
            )
            with self._lock:
                self._manager_info = info
        except Exception:
            pass

    def _check_framework_bg(self, game_id: str) -> None:
        try:
            from ...core.semver import SemVer
            detection = self._host.get_detection()
            if not detection or not detection.valid:
                with self._lock:
                    self._framework_info = None
                return

            current_version = self._get_installed_framework_version()
            api = self._make_apf_api()
            releases = api.list_releases(tag_prefix="framework/")
            if not releases:
                return
            latest_dict = releases[0]
            latest_ver  = latest_dict.get("tag_name", "").split("/")[-1].lstrip("v")
            current = SemVer.parse(current_version)
            new_stable = SemVer.parse(latest_ver)
            is_update = bool(
                current_version != "unknown"
                and current and new_stable and new_stable > current
            )

            asset = self._find_asset_dict(latest_dict, ".zip")
            asset_url = (asset.get("browser_download_url", "") if asset else "")

            info = UpdateInfo(
                component="framework",
                current=current_version,
                latest_stable=None,   # dict-path for framework; typed not needed here
                latest_pre=None,
                asset_url=asset_url,
                is_update_available=is_update,
                is_pre_available=False,
            )
            with self._lock:
                self._framework_info = info
        except Exception:
            pass

    def _check_apworld(self) -> None:
        try:
            from ...core.semver import SemVer
            current_version = self._get_installed_apworld_version()
            api = self._make_apf_api()
            latest = api.get_latest_release_typed()
            latest_pre = api.releases.fetch_latest_prerelease()

            def _ver(r: Optional[RepoRelease]) -> str:
                if not r:
                    return ""
                return r.tag_name.split("/")[-1].lstrip("v")

            latest_ver = _ver(latest)
            current = SemVer.parse(current_version)
            new_stable = SemVer.parse(latest_ver)
            is_update = bool(
                current_version != "0.0.0"
                and current and new_stable and new_stable > current
            )

            asset_url = ""
            if is_update and latest:
                asset = next((a for a in latest.assets
                              if a.name.endswith(".apworld")), None)
                if asset:
                    asset_url = asset.browser_download_url

            info = UpdateInfo(
                component="apworld",
                current=current_version,
                latest_stable=latest,
                latest_pre=latest_pre,
                asset_url=asset_url,
                is_update_available=is_update,
                is_pre_available=bool(latest_pre),
            )
            with self._lock:
                self._apworld_info = info
        except Exception:
            pass

    def _check_ue4ss(self, owner: str = "UE4SS-RE",
                     repo: str = "RE-UE4SS") -> None:
        info = self._run_ue4ss_check(owner, repo)
        with self._lock:
            self._ue4ss_info = info

    def _run_ue4ss_check(self, owner: str, repo: str) -> UpdateInfo:
        try:
            from ...core.semver import SemVer
            api = self._make_ue4ss_api(owner, repo)
            latest = api.get_latest_release_typed()
            latest_pre = api.releases.fetch_latest_prerelease()

            current_version = self._get_installed_ue4ss_version()

            latest_ver = latest.tag_name.lstrip("v") if latest else ""
            is_update: bool
            if current_version == "unknown":
                is_update = False   # can't compare; show both options
            else:
                current = SemVer.parse(current_version)
                new_stable = SemVer.parse(latest_ver)
                is_update = bool(current and new_stable and new_stable > current)

            asset_url = ""
            if latest:
                asset = next((a for a in latest.assets
                              if a.name.endswith(".zip")), None)
                if asset:
                    asset_url = asset.browser_download_url

            return UpdateInfo(
                component="ue4ss",
                current=current_version,
                latest_stable=latest,
                latest_pre=latest_pre,
                asset_url=asset_url,
                is_update_available=is_update,
                is_pre_available=bool(latest_pre),
            )
        except Exception:
            return UpdateInfo(
                component="ue4ss",
                current="unknown",
                latest_stable=None,
                latest_pre=None,
            )

    # -----------------------------------------------------------------------
    # Version detection
    # -----------------------------------------------------------------------

    def _get_installed_ue4ss_version(self) -> str:
        """
        Detect the installed UE4SS version from InstallStateManager cache.

        Only reads from the install state cache — never reads ue4ss_config.ini
        or Changelog.md (both are unreliable for version detection).

        Returns the version string (e.g. "3.0.1") if a pipeline-managed install
        is tracked, or "unknown" for orphaned / manually installed UE4SS.
        """
        if not self._host.has_service("mods"):
            return "unknown"
        mods_svc = self._host.get_service("mods")
        # Try getting game_id from the current profile
        game_id = ""
        if hasattr(mods_svc, "_host"):
            host = mods_svc._host
            if hasattr(host, "get_current_profile"):
                profile = host.get_current_profile()
                if profile:
                    game_id = getattr(profile, "game_id", "")
        if not game_id:
            return "unknown"
        try:
            from ..content.shared import InstallStateManager
            state = InstallStateManager(game_id)
            for entry in state.get_all():
                if entry.get("install_type") == "ue4ss":
                    return entry.get("version", "unknown") or "unknown"
        except Exception:
            pass
        return "unknown"

    def _get_installed_framework_version(self) -> str:
        """Detect installed framework binary version from mod service."""
        if not self._host.has_service("mods"):
            return "unknown"
        mods_svc = self._host.get_service("mods")
        try:
            from ..content.utils.registry.resolver import _is_framework_mod_id
            for mod in mods_svc.get_ap_mods():
                if mod.mod_id and _is_framework_mod_id(mod.mod_id):
                    return mod.version or "unknown"
        except Exception:
            pass
        return "unknown"

    def _get_installed_apworld_version(self) -> str:
        """Scan worlds dir for installed apworld and return its version string."""
        if not _WORLDS_DIR.is_dir():
            return "0.0.0"
        for f in _WORLDS_DIR.iterdir():
            if f.suffix == ".apworld":
                parts = f.stem.rsplit("-", 1)
                if len(parts) == 2:
                    return parts[1]
        return "0.0.0"

    # -----------------------------------------------------------------------
    # API factory helpers
    # -----------------------------------------------------------------------

    def _make_apf_api(self):
        from ...core.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH
        return GitHubAPI(
            repo_owner="RectangleEquals",
            repo_name="APF-UE4SS",
            token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
            on_status=lambda level, msg: None,
        )

    def _make_ue4ss_api(self, owner: str = "UE4SS-RE",
                        repo: str = "RE-UE4SS"):
        from ...core.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH
        return GitHubAPI(
            repo_owner=owner,
            repo_name=repo,
            token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
            on_status=lambda level, msg: None,
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _find_asset_dict(release_dict: dict, suffix: str) -> Optional[dict]:
        for asset in release_dict.get("assets", []):
            if asset.get("name", "").endswith(suffix):
                return asset
        return None


def _ui(fn: Callable) -> None:
    from kivy.clock import Clock
    Clock.schedule_once(lambda dt: fn(), 0)
