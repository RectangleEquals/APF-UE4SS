"""
InstalledController — install state queries and uninstall dispatch for Tab 4.

Handles all service interactions so InstalledTab view never imports services directly.
"""
from __future__ import annotations

from typing import Optional, Tuple

from ......core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)


class InstalledController:
    """Non-Kivy controller for InstalledTab."""

    def __init__(self, host) -> None:
        self._host = host

    # -----------------------------------------------------------------------
    # Mod scanning
    # -----------------------------------------------------------------------

    def scan_mods(self) -> list:
        """Return all mods from the mods service."""
        mods_svc = self._host.get_service("mods")
        return mods_svc.scan() if mods_svc else []

    def rescan_mods(self) -> list:
        mods_svc = self._host.get_service("mods")
        return mods_svc.rescan() if mods_svc else []

    # -----------------------------------------------------------------------
    # Install state
    # -----------------------------------------------------------------------

    def get_install_map(self, game_id: str) -> dict:
        """
        Return {folder_name: InstallRecord} for all tracked installs.
        Returns empty dict if game_id is empty or state file is missing.
        """
        if not game_id:
            return {}
        try:
            from ....models.state.install import InstallStateManager
            from ....models.state.pipeline import InstallRecord
            return {
                d.get("folder_name", ""): InstallRecord.from_dict(d)
                for d in InstallStateManager(game_id).get_all()
                if d.get("folder_name")
            }
        except Exception as exc:
            logger.warning(f"get_install_map failed: {exc}")
            return {}

    def get_install_record(self, folder_name: str, game_id: str):
        """Return the InstallRecord for a specific folder, or None."""
        return self.get_install_map(game_id).get(folder_name)

    # -----------------------------------------------------------------------
    # Deploy service access (for InstalledRowWidget + mods.txt queries)
    # -----------------------------------------------------------------------

    def get_deploy_svc(self):
        return self._host.get_service("deploy")

    def get_mods_txt(self):
        deploy_svc = self.get_deploy_svc()
        return deploy_svc.mods_txt if deploy_svc else None

    # -----------------------------------------------------------------------
    # Uninstall
    # -----------------------------------------------------------------------

    def get_uninstall_impact(self, mod) -> dict:
        """
        Return impact dict for uninstalling a mod.
        Keys: dependents (list[str]), components (list[str]), is_framework (bool).
        """
        deploy_svc = self.get_deploy_svc()
        if not deploy_svc:
            return {"dependents": [], "components": [], "is_framework": False}
        if hasattr(deploy_svc, "get_framework_uninstall_impact"):
            from ....controllers.mods.service import _FRAMEWORK_MOD_RE
            if mod.mod_id and _FRAMEWORK_MOD_RE.match(mod.mod_id):
                return deploy_svc.get_framework_uninstall_impact(mod)
        if hasattr(deploy_svc, "get_uninstall_impact"):
            return deploy_svc.get_uninstall_impact(mod)
        return {"dependents": [], "components": list(getattr(mod, "components", [])),
                "is_framework": False}

    def do_uninstall(self, install_record, detection, game_id: str) -> Tuple[bool, str]:
        """
        Uninstall a tracked mod.

        Returns (success, error_message).
        Notifies 'install' state change on success.
        """
        deploy_svc = self.get_deploy_svc()
        if not deploy_svc or not detection:
            return False, "Deploy service or detection unavailable"
        try:
            deploy_svc.undeploy_content(install_record, detection, game_id)
            mods_svc = self._host.get_service("mods")
            if mods_svc:
                mods_svc.rescan()
            self._host.notify_state_change("install")
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def do_remove_nonap(self, mod, detection) -> Tuple[bool, str]:
        """Remove a non-AP mod folder from the game directory."""
        import shutil
        try:
            folder_path = getattr(mod, "folder_path", None)
            if folder_path and folder_path.is_dir():
                shutil.rmtree(folder_path)
            mods_svc = self._host.get_service("mods")
            if mods_svc:
                mods_svc.rescan()
            self._host.notify_state_change("install")
            return True, ""
        except Exception as exc:
            return False, str(exc)

    # -----------------------------------------------------------------------
    # Counts (used by pipeline panel badges)
    # -----------------------------------------------------------------------

    def get_installed_count(self) -> Tuple[int, int]:
        """Return (total_ap_mods, orphaned_count)."""
        mods = self.scan_mods()
        ap_mods  = [m for m in mods if m.is_ap_mod]
        orphaned = sum(1 for m in ap_mods if getattr(m, "is_orphaned", False))
        return len(ap_mods), orphaned

    # -----------------------------------------------------------------------
    # Game ID derivation
    # -----------------------------------------------------------------------

    def get_game_id(self, profile) -> str:
        if self._host.has_service("registry"):
            svc = self._host.get_service("registry")
            gid = svc._get_game_id() if hasattr(svc, "_get_game_id") else ""
            if gid:
                return gid
        if profile:
            name = getattr(profile, "display_name", None) or getattr(profile, "name", "")
            return name.lower().replace(" ", "_") if name else ""
        return ""
