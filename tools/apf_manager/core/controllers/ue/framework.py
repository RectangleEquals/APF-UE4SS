"""FrameworkDetector — detects AP Framework binaries and the core framework mod."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from ...models.ue.platform import UEPlatformInfo
from ...models.ue.ue4ss import UE4SSInfo
from ...models.ue.framework import FrameworkBinariesInfo, FrameworkModInfo
from ._helpers import _find_file_ci
from ..logging.manager import APFLogManager
logger = APFLogManager.get_logger(__name__)

FRAMEWORK_MOD_RE = re.compile(r"^archipelago\.[^.]+\.framework$")


class FrameworkDetector:
    """
    Detects AP Framework components:
      - Binaries: APFrameworkCore.dll + APClientLib.dll in platform_dir
      - Core mod: manifest.json with archipelago.<game_id>.framework mod_id
    """

    @staticmethod
    def detect_binaries(platform_info: UEPlatformInfo) -> FrameworkBinariesInfo:
        d = platform_info.platform_dir
        return FrameworkBinariesInfo(
            has_core_dll=_find_file_ci(d, "APFrameworkCore.dll") is not None,
            has_client_dll=_find_file_ci(d, "APClientLib.dll") is not None,
        )

    @staticmethod
    def detect_mod(ue4ss_info: UE4SSInfo) -> Optional[FrameworkModInfo]:
        if not ue4ss_info.mods_dir:
            return None
        try:
            for mod_dir in ue4ss_info.mods_dir.iterdir():
                if not mod_dir.is_dir():
                    continue
                manifest_path = mod_dir / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    mod_id = manifest.get("mod_id", "")
                    if not FRAMEWORK_MOD_RE.match(mod_id):
                        continue
                    fw_cfg = mod_dir / "framework_config.json"
                    out_dir = mod_dir / "Output"
                    ss = out_dir / "session_state.json"
                    return FrameworkModInfo(
                        mod_dir=mod_dir,
                        mod_id=mod_id,
                        manifest_path=manifest_path,
                        framework_config_path=fw_cfg if fw_cfg.exists() else None,
                        has_scripts=(
                            (mod_dir / "Scripts" / "main.lua").exists()
                            or (mod_dir / "dlls" / "main.dll").exists()
                        ),
                        output_dir=out_dir if out_dir.exists() else None,
                        session_state_path=ss if ss.exists() else None,
                    )
                except Exception:
                    continue
        except (PermissionError, OSError) as exc:
            logger.debug("[framework] Permission/OS error scanning framework mod directory: %s", exc)
        return None
