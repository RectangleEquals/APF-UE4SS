"""ue4ss_install_controller.py — UE4SS installation controllers (official + custom layouts)."""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Optional

from .base_install_controller import BaseInstallController


class UE4SSInstallController(BaseInstallController):
    """Abstract base for all UE4SS install variants."""


class UE4SSOfficialInstallController(UE4SSInstallController):
    """
    Flat/stable layout (e.g. UE4SS v3.0.1 official release).

    UE4SS.dll and Mods/ sit at the zip root with no ue4ss/ subfolder:
      dwmapi.dll (if present) → platform_dir/            (proxy DLL stays at game root)
      all other files          → platform_dir/ue4ss/      (UE4SS runtime lives in ue4ss/)
    """

    def deploy(
        self,
        zip_path: Path,
        platform_dir: Path,
        logicmods_dir: Optional[Path] = None,
    ) -> None:
        ue4ss_dir = platform_dir / "ue4ss"
        ue4ss_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.filename.lower() == "dwmapi.dll":
                    zf.extract(info, str(platform_dir))
                else:
                    zf.extract(info, str(ue4ss_dir))


class UE4SSCustomInstallController(UE4SSInstallController):
    """
    Subfolder/experimental layout (e.g. UE4SS nightly or custom builds).

    The ue4ss/ subfolder is already present at the zip root:
      extractall → platform_dir/
      ue4ss/ structure is preserved; dwmapi.dll at zip root lands in platform_dir/
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
