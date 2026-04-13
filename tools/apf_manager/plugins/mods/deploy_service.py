"""
DeployService — service API for mod deployment operations.

Registered as the "deploy" service by the mods plugin.

Owns the shared ModsTextManager instance so all tabs share the same in-memory state.
"""

from __future__ import annotations

import shutil
import threading
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.config import GameProfile
    from ...core.ue4ss import UE4SSResult
    from .mods_txt import ModsTextManager
    from .mod_service import ModInfo


class DeployService:
    def __init__(self, host) -> None:
        self._host = host
        self._mods_txt: Optional["ModsTextManager"] = None
        self._detection: Optional["UE4SSResult"] = None
        self._profile: Optional["GameProfile"] = None
        self._lock = threading.Lock()

    # Called by PluginHost when game context changes
    def on_game_changed(self, profile: Optional["GameProfile"], detection: Optional["UE4SSResult"]) -> None:
        with self._lock:
            self._profile = profile
            self._detection = detection
            self._reload_mods_txt()

    def _reload_mods_txt(self) -> None:
        if self._detection and self._detection.mods_txt:
            from .mods_txt import ModsTextManager
            self._mods_txt = ModsTextManager(self._detection.mods_txt)
            self._mods_txt.load()
        else:
            self._mods_txt = None

    # -----------------------------------------------------------------------
    # Public API (inter-plugin)
    # -----------------------------------------------------------------------

    @property
    def mods_txt(self) -> Optional["ModsTextManager"]:
        return self._mods_txt

    def get_load_order(self) -> list[str]:
        with self._lock:
            return self._mods_txt.get_order() if self._mods_txt else []

    def set_enabled(self, folder_name: str, enabled: bool) -> None:
        with self._lock:
            if self._mods_txt:
                self._mods_txt.set_enabled(folder_name, enabled)
                self._mods_txt.save()

    def ensure_entry(self, folder_name: str, enabled: bool = True) -> None:
        with self._lock:
            if self._mods_txt:
                self._mods_txt.ensure_entry(folder_name, enabled)
                self._mods_txt.save()

    def reorder(self, order: list[str]) -> None:
        with self._lock:
            if self._mods_txt:
                enforced = self._enforce_framework_order(order)
                self._mods_txt.reorder(enforced)
                self._mods_txt.save()

    def _get_framework_folder(self) -> Optional[str]:
        """Find the framework mod folder name via ModService (mod_id ends with .framework)."""
        mods_svc = self._host.get_service("mods")
        if not mods_svc:
            return None
        for mod in mods_svc.get_ap_mods():
            if mod.mod_id and mod.mod_id.endswith(".framework"):
                return mod.folder_name
        return None

    def _enforce_framework_order(self, order: list[str]) -> list[str]:
        """
        Ensure the framework mod precedes all other AP mods in the order list.
        This is a safety net; the UI cascade logic should maintain the invariant.
        """
        fw_folder = self._get_framework_folder()
        if not fw_folder or fw_folder not in order:
            return order

        mods_svc = self._host.get_service("mods")
        if not mods_svc:
            return order

        ap_folders = {mod.folder_name for mod in mods_svc.get_ap_mods()}
        result = list(order)
        fw_idx = result.index(fw_folder)

        # Find the first non-framework AP mod that appears before the framework mod
        for i in range(fw_idx):
            if result[i] in ap_folders and result[i] != fw_folder:
                # Move framework mod to just before that AP mod
                result.pop(fw_idx)
                result.insert(i, fw_folder)
                break

        return result

    def remove_entry(self, folder_name: str) -> None:
        """Remove a mod entry from mods.txt and save."""
        with self._lock:
            if self._mods_txt:
                self._mods_txt.remove_entry(folder_name)
                self._mods_txt.save()

    def reload(self) -> None:
        """Force re-read mods.txt from disk."""
        with self._lock:
            self._reload_mods_txt()

    # -----------------------------------------------------------------------
    # Deploy / undeploy
    # -----------------------------------------------------------------------

    def undeploy_mod(self, mod_info: "ModInfo", detection: Optional["UE4SSResult"]) -> None:
        """
        Remove all deployed components for a mod from the install target.
        Does not touch the download cache. Does not remove dependency DLLs.
        """
        if not detection:
            return

        components = getattr(mod_info, "components", ["lua"])

        if any(c in components for c in ("lua", "cpp")):
            shutil.rmtree(str(mod_info.folder_path), ignore_errors=True)
            with self._lock:
                if self._mods_txt:
                    self._mods_txt.remove_entry(mod_info.folder_name)
                    self._mods_txt.save()

        if "blueprint" in components and detection.logicmods_dir:
            for pak in getattr(mod_info, "bp_pak_files", []):
                pak_path = detection.logicmods_dir / pak
                try:
                    pak_path.unlink(missing_ok=True)
                except Exception:
                    pass

        if self._profile:
            from .install_state import InstallStateManager
            InstallStateManager(self._profile.game_id).remove(mod_info.folder_name)

    def get_component_status(self, mod_info: "ModInfo", detection: Optional["UE4SSResult"]) -> dict:
        """
        Return per-component presence status for a deployed mod.
        Keys: "lua", "cpp", "blueprint" — values: bool.
        """
        if not detection:
            return {}

        components = getattr(mod_info, "components", ["lua"])
        bp_pak_files = getattr(mod_info, "bp_pak_files", [])
        status = {}

        if "lua" in components:
            status["lua"] = (
                detection.mods_dir / mod_info.folder_name / "scripts" / "main.lua"
            ).exists()

        if "cpp" in components:
            status["cpp"] = (
                detection.mods_dir / mod_info.folder_name / "dlls" / "main.dll"
            ).exists()

        if "blueprint" in components:
            if bp_pak_files and detection.logicmods_dir:
                status["blueprint"] = all(
                    (detection.logicmods_dir / f).exists() for f in bp_pak_files
                )
            else:
                status["blueprint"] = False

        return status
