"""framework_install_controller.py — AP Framework binary installation controller."""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Optional

from ..base.install import BaseInstallController


class FrameworkInstallController(BaseInstallController):
    """
    Installs AP Framework Core binaries by extracting all contents to platform_dir.
    The zip structure is expected to place DLLs directly at the root.
    """

    def deploy(
        self,
        zip_path: Path,
        platform_dir: Path,
        logicmods_dir: Optional[Path] = None,
    ) -> None:
        platform_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(str(platform_dir))
