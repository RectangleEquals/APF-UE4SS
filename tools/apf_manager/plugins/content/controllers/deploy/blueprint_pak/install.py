"""blueprint_pak_install_controller.py — Blueprint pak installation controller."""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Optional

from ..base.install import BaseInstallController

# All file extensions that belong in LogicMods/
_BP_EXTENSIONS = frozenset({".pak", ".ucas", ".utoc"})


class BlueprintPakInstallController(BaseInstallController):
    """
    Deploys blueprint pak/ucas/utoc files to the game's LogicMods directory.

    Extracts ALL blueprint logic mod file types (.pak, .ucas, .utoc) from the zip
    so that UcasLogicMod pairs (which require both .ucas and .utoc) are deployed
    atomically.

    HARD ERROR if logicmods_dir is not provided — blueprint pak files must not
    be deployed to an unknown location. The RuntimeError propagates through
    DeployService to the UI content row's error state.
    """

    def deploy(
        self,
        zip_path: Path,
        platform_dir: Path,
        logicmods_dir: Optional[Path] = None,
    ) -> None:
        if not logicmods_dir or not logicmods_dir.parts:
            raise RuntimeError(
                f"[BlueprintPakInstallController] logicmods_dir is required but was not "
                f"provided for '{zip_path.name}'. Blueprint pak files cannot be deployed "
                "to an unknown location — verify that the game's "
                "Content/Paks/LogicMods/ directory was detected."
            )
        logicmods_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if Path(info.filename).suffix.lower() in _BP_EXTENSIONS:
                    zf.extract(info, str(logicmods_dir))
