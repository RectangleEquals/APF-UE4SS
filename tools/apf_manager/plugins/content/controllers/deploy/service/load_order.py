"""DeployLoadOrderMixin — mods.txt load order management for DeployService."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ......core.models.ue.result import DetectionResult


class DeployLoadOrderMixin:
    """Mixin for DeployService: get_load_order, set_enabled, reorder, ensure/remove_entry."""

    @property
    def mods_txt(self):
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

    def on_game_changed(self, profile, detection: "Optional[DetectionResult]") -> None:
        with self._lock:
            self._profile = profile
            self._detection = detection
            self._reload_mods_txt()

    def _reload_mods_txt(self) -> None:
        if self._detection and self._detection.ue4ss and self._detection.ue4ss.mods_txt:
            from ....models.mods.config import ModsTextManager
            self._mods_txt = ModsTextManager(self._detection.ue4ss.mods_txt)
            self._mods_txt.load()
        else:
            self._mods_txt = None

    def _get_framework_folder(self) -> Optional[str]:
        """Return the framework mod folder name (delegates to ModService for pattern-correct detection)."""
        mods_svc = self._host.get_service("mods")
        if not mods_svc:
            return None
        fw_dir = mods_svc.get_framework_mod_dir()
        return fw_dir.name if fw_dir else None

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
