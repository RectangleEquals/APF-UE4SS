"""
DeployService — public service API for the deploy plugin.

Registered as the "deploy" service so other plugins can call:
    svc = host.get_service("deploy")
    svc.set_enabled("MyMod", True)
    svc.reorder(["APFrameworkMod", "MyMod", "OtherMod"])
    svc.remove_entry("MyMod")

Also owns the shared ModsTextManager instance so all tabs share the same in-memory state.
"""

from __future__ import annotations

import threading
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.config import GameProfile
    from ...core.ue4ss import UE4SSResult
    from .mods_txt import ModsTextManager


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