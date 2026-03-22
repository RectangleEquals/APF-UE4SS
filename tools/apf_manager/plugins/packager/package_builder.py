"""
PackageBuilder  — builds a release ZIP for distribution.
ApworldPackager — builds an .apworld from worlds/apf/.

Release ZIP contents:
    Mods/<mod_folder>/          Each AP mod folder
    APFrameworkCore.dll         From build_dir
    APClientLib.dll             From build_dir
    Templates/                  From source_project/Templates/ (if present)
    README.md                   From source_project/README.md (if present)
    apf.apworld                 Built by ApworldPackager (if worlds/apf/ present)
"""

from __future__ import annotations

import zipfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.config import GameProfile
    from ...core.ue4ss import UE4SSResult


class PackageBuilder:
    def __init__(
        self,
        profile: "GameProfile",
        detection: "UE4SSResult",
        version: str,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._profile = profile
        self._detection = detection
        self._version = version
        self._log = log_fn or (lambda msg: None)

    def build(self, output_dir: Path) -> Optional[Path]:
        """
        Build the release ZIP into output_dir.
        Returns the path to the created ZIP, or None on failure.
        """
        source = Path(self._profile.source_project)
        build = Path(self._profile.build_dir)

        if not source.is_dir():
            self._log(f"source_project not found: {source}")
            return None

        ts = datetime.now().strftime("%Y%m%d")
        zip_name = f"APFramework_v{self._version}_{ts}.zip"
        zip_path = output_dir / zip_name
        output_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            # Mods/ folder
            if self._detection.mods_dir and self._detection.mods_dir.is_dir():
                mods_svc = None  # type: ignore
                for mod_folder in self._detection.mods_dir.iterdir():
                    if not mod_folder.is_dir():
                        continue
                    manifest = mod_folder / "manifest.json"
                    if not manifest.exists():
                        continue
                    self._add_tree(zf, mod_folder, Path("Mods") / mod_folder.name)
                    self._log(f"  + Mods/{mod_folder.name}/")

            # DLLs from build_dir
            for dll in ("APFrameworkCore.dll", "APClientLib.dll"):
                dll_path = build / dll
                if dll_path.exists():
                    zf.write(dll_path, dll)
                    self._log(f"  + {dll}")
                else:
                    self._log(f"  ! Missing: {dll}")

            # Templates/
            templates = source / "Templates"
            if templates.is_dir():
                self._add_tree(zf, templates, Path("Templates"))
                self._log("  + Templates/")

            # README.md
            readme = source / "README.md"
            if readme.exists():
                zf.write(readme, "README.md")
                self._log("  + README.md")

            # .apworld
            worlds_apf = source / "worlds" / "apf"
            if worlds_apf.is_dir():
                apworld_data = ApworldPackager.build_bytes(worlds_apf, self._log)
                if apworld_data:
                    zf.writestr("apf.apworld", apworld_data)
                    self._log("  + apf.apworld")

        self._log(f"Release package: {zip_path}")
        return zip_path

    @staticmethod
    def _add_tree(zf: zipfile.ZipFile, src: Path, arcname: Path) -> None:
        for f in src.rglob("*"):
            if f.is_file():
                zf.write(f, arcname / f.relative_to(src))


class ApworldPackager:
    @staticmethod
    def build(worlds_apf_dir: Path, output_path: Path, log_fn=None) -> bool:
        """Build worlds/apf/ → output_path (.apworld)."""
        log = log_fn or (lambda msg: None)
        data = ApworldPackager.build_bytes(worlds_apf_dir, log)
        if data is None:
            return False
        output_path.write_bytes(data)
        log(f"apworld: {output_path}")
        return True

    @staticmethod
    def build_bytes(worlds_apf_dir: Path, log_fn=None) -> Optional[bytes]:
        import io
        log = log_fn or (lambda msg: None)
        if not worlds_apf_dir.is_dir():
            log(f"worlds/apf/ not found: {worlds_apf_dir}")
            return None

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for f in sorted(worlds_apf_dir.rglob("*")):
                if f.is_file():
                    arcname = Path("apf") / f.relative_to(worlds_apf_dir)
                    zf.write(f, arcname)
        return buf.getvalue()
