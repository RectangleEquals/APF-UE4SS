"""ModDetector — scans ue4ss/Mods/ and classifies each mod folder."""
from __future__ import annotations

import json
import re

from ...models.ue.ue4ss import UE4SSInfo
from ...models.ue.mod import ModDetectionInfo
from .framework import FRAMEWORK_MOD_RE

# archipelago.<game_id>.<mod_name> — two dots after "archipelago"
PRIORITY_AP_MOD_RE = re.compile(r"^archipelago\.[^.]+\.[^.]+$")


class ModDetector:
    """
    Scans ue4ss/Mods/ and classifies each subdirectory as a mod type.

    A folder is only considered a mod if it contains Scripts/main.lua
    or dlls/main.dll. Folders without either (e.g. "shared/") are skipped.

    Classification:
      - Framework mod:  mod_id matches archipelago.<game_id>.framework
      - Priority AP:    mod_id matches archipelago.<game_id>.<name> (framework is a sub-case)
      - Regular AP:     mod_id present, does NOT match archipelago.* pattern
      - Non-AP mod:     no manifest.json
    """

    @staticmethod
    def scan(ue4ss_info: UE4SSInfo) -> list[ModDetectionInfo]:
        if not ue4ss_info.mods_dir:
            return []
        results: list[ModDetectionInfo] = []
        try:
            for mod_dir in ue4ss_info.mods_dir.iterdir():
                if not mod_dir.is_dir():
                    continue
                has_lua = (mod_dir / "Scripts" / "main.lua").exists()
                has_cpp = (mod_dir / "dlls" / "main.dll").exists()
                if not (has_lua or has_cpp):
                    continue

                mod_id: str | None = None
                is_priority_ap = False
                is_framework = False
                manifest_path = mod_dir / "manifest.json"
                if manifest_path.exists():
                    try:
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        mod_id = manifest.get("mod_id") or None
                        if mod_id:
                            is_priority_ap = bool(PRIORITY_AP_MOD_RE.match(mod_id))
                            is_framework = bool(FRAMEWORK_MOD_RE.match(mod_id))
                    except Exception:
                        pass

                results.append(ModDetectionInfo(
                    folder_name=mod_dir.name,
                    mod_dir=mod_dir,
                    mod_id=mod_id,
                    is_ap_mod=mod_id is not None,
                    is_priority_ap=is_priority_ap,
                    is_framework=is_framework,
                    has_lua=has_lua,
                    has_cpp=has_cpp,
                ))
        except (PermissionError, OSError):
            pass
        return results
