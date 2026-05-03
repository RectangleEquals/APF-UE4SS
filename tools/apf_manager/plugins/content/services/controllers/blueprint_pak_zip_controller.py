"""blueprint_pak_zip_controller.py — Blueprint pak zip detection controller."""
from __future__ import annotations

from .base_zip_controller import BaseZipFileController


class BlueprintPakZipFileController(BaseZipFileController):
    """
    Detects standalone blueprint pak zips — all non-directory entries are .pak files.
    These must be deployed to the game's LogicMods directory, not platform_dir.
    """

    def classify(self, zf) -> bool:
        non_dir = [
            info.filename.lower() for info in zf.infolist()
            if not info.filename.endswith("/")
        ]
        if bool(non_dir) and all(n.endswith(".pak") for n in non_dir):
            self._detected_layout = "blueprint_pak"
            return True
        return False

    def create_install_controller(self):
        from .blueprint_pak_install_controller import BlueprintPakInstallController
        return BlueprintPakInstallController(self.content, zip_ctrl=self)
