"""framework_zip_controller.py — AP Framework binary zip detection controller."""
from __future__ import annotations

from ..base.zip import BaseZipFileController


class FrameworkZipFileController(BaseZipFileController):
    """Detects AP Framework Core binaries in a zip file (APFrameworkCore.dll)."""

    def classify(self, zf) -> bool:
        names = {info.filename.lower() for info in zf.infolist()}
        if any("apframeworkcore.dll" in n for n in names):
            self._detected_layout = "framework"
            return True
        return False

    def create_install_controller(self):
        from .install import FrameworkInstallController
        return FrameworkInstallController(self.content, zip_ctrl=self)
