"""framework_zip_controller.py — AP Framework binary zip detection controller."""
from __future__ import annotations

from .base_zip_controller import BaseZipFileController


class FrameworkZipFileController(BaseZipFileController):
    """Detects AP Framework Core binaries in a zip file (APFrameworkCore.dll)."""

    def classify(self, zf) -> bool:
        names = {info.filename.lower() for info in zf.infolist()}
        if any("apframeworkcore.dll" in n for n in names):
            self._detected_layout = "framework"
            return True
        return False

    def create_install_controller(self):
        from .framework_install_controller import FrameworkInstallController
        return FrameworkInstallController(self.content, zip_ctrl=self)
