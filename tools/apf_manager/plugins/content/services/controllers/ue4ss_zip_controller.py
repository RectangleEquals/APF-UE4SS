"""ue4ss_zip_controller.py — UE4SS zip content detection controller."""
from __future__ import annotations

from .base_zip_controller import BaseZipFileController


class UE4SSZipFileController(BaseZipFileController):
    """
    Detects UE4SS content in a zip file; stores the detected layout variant
    so create_install_controller() can return the correct concrete subclass.

    Layout A — flat/stable (e.g. UE4SS v3.0.1 official release):
      UE4SS.dll + Mods/ directory sit at the zip root.
      → UE4SSOfficialInstallController

    Layout B — subfolder/experimental (e.g. UE4SS nightly/custom builds):
      ue4ss/UE4SS.dll present; ue4ss/ subfolder at zip root.
      → UE4SSCustomInstallController

    Identifying factor: UE4SS.dll + Mods/ directory — NOT dwmapi.dll, which is
    absent in Steam Workshop variants of UE4SS.
    """

    def classify(self, zf) -> bool:
        names = {info.filename.lower() for info in zf.infolist()}
        if self._is_subfolder(names):
            self._detected_layout = "subfolder"
            return True
        if self._is_flat(names):
            self._detected_layout = "flat"
            return True
        return False

    @staticmethod
    def _is_flat(names: set) -> bool:
        """Flat: UE4SS.dll at root AND Mods/ directory at root."""
        return "ue4ss.dll" in names and any(n.startswith("mods/") for n in names)

    @staticmethod
    def _is_subfolder(names: set) -> bool:
        """Subfolder: ue4ss/UE4SS.dll present anywhere in the zip."""
        return any("ue4ss/ue4ss.dll" in n for n in names)

    def create_install_controller(self):
        from .ue4ss_install_controller import (
            UE4SSOfficialInstallController,
            UE4SSCustomInstallController,
        )
        if self._detected_layout == "flat":
            return UE4SSOfficialInstallController(self.content, zip_ctrl=self)
        if self._detected_layout == "subfolder":
            return UE4SSCustomInstallController(self.content, zip_ctrl=self)
        raise RuntimeError(
            "UE4SSZipFileController.create_install_controller() called before classify(), "
            "or classify() returned False"
        )
