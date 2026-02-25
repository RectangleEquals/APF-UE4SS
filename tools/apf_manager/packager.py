"""
APF Manager — packaging utilities.

PackageBuilder:    Creates distributable release zips for testers.
ApworldPackager:   Creates .apworld file from worlds/apf/.
LogPackager:       Collects and sanitizes logs for developer support.
ReadmeGenerator:   Generates README_INSTALL.txt for release zips.
"""

from __future__ import annotations

import datetime
import json
import platform
import zipfile
from pathlib import Path
from typing import Callable

from .config import APFConfig
from .discovery import ModDiscovery
from .ue4ss import UE4SSDetectionResult


class ApworldPackager:
    def __init__(self, config: APFConfig):
        self.config = config.resolve()

    def build(self, output_dir: Path) -> Path:
        """Zip worlds/apf/ into output_dir/apf.apworld."""
        src = Path(self.config.source_project) / "worlds" / "apf"
        if not src.is_dir():
            raise FileNotFoundError(f"apworld source not found: {src}")
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "apf.apworld"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in src.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(src.parent))
        return out


class ReadmeGenerator:
    TEMPLATE = """\
AP Framework for Palworld — Installation Guide
===============================================
Version: {version}
Generated: {date}

PREREQUISITES
-------------
  - Palworld with UE4SS installed (see https://github.com/UE4SS-RE/RE-UE4SS)
  - PalSchema mod installed in UE4SS/Mods/ (required by TechShuffle)
  - An Archipelago server (local or remote)

INSTALLATION
------------
1. Copy the contents of the Mods/ folder into:
     <Palworld>/Binaries/Win64/ue4ss/Mods/

2. Copy the contents of LogicMods/ into:
     <Palworld>/Pal/Content/Paks/LogicMods/
   (Create the LogicMods folder if it doesn't exist.)

3. Copy apworld/apf.apworld to your Archipelago server's worlds/ directory.

4. Edit APFrameworkMod/framework_config.json with your server details:
     "host": "your.server.address",
     "port": 38281,
     "slot_name": "YourPlayerName",
     "password": ""

5. Generate your YAML using the AP server, then generate a seed and start playing!

TROUBLESHOOTING
---------------
- Check <Palworld>/Binaries/Win64/ue4ss/ap_framework.log for errors.
- Check UE4SS.log in the same folder for mod loading issues.
- Ensure APFrameworkMod is listed before other AP mods in mods.txt.
- Make sure Keybinds : 1 remains at the bottom of mods.txt.
"""

    def generate(self, version: str) -> str:
        return self.TEMPLATE.format(
            version=version,
            date=datetime.datetime.now().strftime("%Y-%m-%d"),
        )


class LogPackager:
    def __init__(self, detection: UE4SSDetectionResult):
        self.detection = detection

    def build(self, output_dir: Path) -> Path:
        """Collect logs + sanitized config into a zip for developer support."""
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"apf_logs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            # Framework log
            fw_log = self.detection.mods_dir / "APFrameworkMod" / "ap_framework.log"
            if fw_log.exists():
                zf.write(fw_log, "ap_framework.log")
            # UE4SS log
            ue4ss_log = self.detection.binaries_dir / "UE4SS.log"
            if ue4ss_log.exists():
                zf.write(ue4ss_log, "UE4SS.log")
            # Sanitized config
            config_path = self.detection.mods_dir / "APFrameworkMod" / "framework_config.json"
            if config_path.exists():
                try:
                    cfg = json.loads(config_path.read_text(encoding="utf-8"))
                    cfg.pop("password", None)  # Remove password
                    zf.writestr("framework_config_sanitized.json",
                                json.dumps(cfg, indent=4))
                except Exception:
                    pass
            # System info
            info = (
                f"Platform: {platform.system()} {platform.version()}\n"
                f"Game root: {self.detection.game_root}\n"
                f"Mods dir: {self.detection.mods_dir}\n"
                f"Collected: {datetime.datetime.now().isoformat()}\n"
            )
            zf.writestr("system_info.txt", info)
        return out


class PackageBuilder:
    """Creates a distributable release zip for end users."""

    def __init__(self, config: APFConfig, discovery: ModDiscovery,
                 log: Callable[[str], None] | None = None):
        self.config = config.resolve()
        self.discovery = discovery
        self._log = log or print

    def build(self, version: str) -> Path:
        src = Path(self.config.source_project)
        build_dir = Path(self.config.build_dir)
        dist_dir = src / "tools" / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        out = dist_dir / f"APFramework_Palworld_{version}.zip"

        self._log(f"Building package {out.name}...")
        readme_gen = ReadmeGenerator()
        apworld_pkg = ApworldPackager(self.config)

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            # README
            zf.writestr("README_INSTALL.txt", readme_gen.generate(version))

            # Mods
            for mod in self.discovery.discover():
                if mod.is_stub:
                    continue
                mod_src = src / "Mods" / mod.folder_name
                for f in mod_src.rglob("*"):
                    if f.is_file() and f.suffix != ".db":  # skip large binary data files
                        zf.write(f, Path("Mods") / mod.folder_name / f.relative_to(mod_src))
                # Copy DLLs from build dir
                for dll_name in ("APFrameworkCore.dll", "APClientLib.dll"):
                    dll = build_dir / dll_name
                    if dll.exists():
                        zf.write(dll, Path("Mods") / mod.folder_name / "Scripts" / dll_name)

            # LogicMods .pak (if present in build dir)
            pak = build_dir / "APTracker.pak"
            if pak.exists():
                zf.write(pak, Path("LogicMods") / "APTracker.pak")
            else:
                self._log("  [WARN] APTracker.pak not found in build dir — skipping")

            # Templates (needed by APFrameworkMod at runtime)
            templates = src / "Templates"
            if templates.is_dir():
                for f in templates.rglob("*"):
                    if f.is_file():
                        zf.write(f, Path("Mods") / "APFrameworkMod" / "Templates"
                                 / f.relative_to(templates))

            # apworld
            try:
                apworld_out = apworld_pkg.build(dist_dir / "_tmp_apworld")
                zf.write(apworld_out, Path("apworld") / "apf.apworld")
            except FileNotFoundError as exc:
                self._log(f"  [WARN] Could not build apworld: {exc}")

        self._log(f"Package ready: {out}")
        return out
