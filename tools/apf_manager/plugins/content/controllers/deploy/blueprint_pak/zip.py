"""blueprint_pak_zip_controller.py — Blueprint pak zip detection controller."""
from __future__ import annotations

from pathlib import Path

from ..base.zip import BaseZipFileController

_BP_EXTENSIONS = frozenset({".pak", ".ucas", ".utoc"})


class BlueprintPakZipFileController(BaseZipFileController):
    """
    Detects standalone blueprint pak zips.

    Classifies a zip as a blueprint pak bundle when ALL non-directory entries
    have extensions in (.pak, .ucas, .utoc). This handles both pure .pak bundles
    and paired .ucas/.utoc bundles (UcasLogicMod).
    These must be deployed to the game's LogicMods directory, not platform_dir.
    """

    def classify(self, zf) -> bool:
        non_dir = [
            info.filename for info in zf.infolist()
            if not info.filename.endswith("/")
        ]
        if bool(non_dir) and all(
            Path(n).suffix.lower() in _BP_EXTENSIONS for n in non_dir
        ):
            self._detected_layout = "blueprint_pak"
            return True
        return False

    def create_install_controller(self):
        from .install import BlueprintPakInstallController
        return BlueprintPakInstallController(self.content, zip_ctrl=self)
