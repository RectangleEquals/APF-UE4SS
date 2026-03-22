"""
LogPackager — collects diagnostic files and bundles them into a timestamped ZIP.

Collected files:
    ap_framework.log    from APFrameworkMod/  (if present)
    UE4SS.log           from ue4ss/           (if present)
    framework_config.json (sanitized — password replaced with [redacted])

Output: diagnostics_{game_name}_{timestamp}.zip
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.ue4ss import UE4SSResult
    from ...core.config import GameProfile


class LogPackager:
    def __init__(
        self,
        profile: "GameProfile",
        detection: "UE4SSResult",
    ) -> None:
        self._profile = profile
        self._detection = detection

    def collect(self, output_path: Path) -> list[str]:
        """
        Build the ZIP at output_path.
        Returns a list of included file names.
        """
        included: list[str] = []

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # ap_framework.log
            if self._detection.mods_dir:
                fw_log = self._detection.mods_dir / "APFrameworkMod" / "ap_framework.log"
                if fw_log.exists():
                    zf.write(fw_log, "ap_framework.log")
                    included.append("ap_framework.log")

            # UE4SS.log
            if self._detection.ue4ss_dir:
                ue4ss_log = self._detection.ue4ss_dir / "UE4SS.log"
                if ue4ss_log.exists():
                    zf.write(ue4ss_log, "UE4SS.log")
                    included.append("UE4SS.log")

            # framework_config.json (sanitized)
            if self._detection.mods_dir:
                cfg_path = (
                    self._detection.mods_dir / "APFrameworkMod" / "framework_config.json"
                )
                if cfg_path.exists():
                    sanitized = self._sanitize_config(cfg_path)
                    zf.writestr("framework_config.json", sanitized)
                    included.append("framework_config.json (sanitized)")

            # System info stub
            info = {
                "game": self._profile.display_name,
                "game_root": self._profile.game_root,
                "ue4ss_dir": str(self._detection.ue4ss_dir) if self._detection.ue4ss_dir else None,
                "mods_dir": str(self._detection.mods_dir) if self._detection.mods_dir else None,
                "missing": self._detection.missing,
            }
            zf.writestr("info.json", json.dumps(info, indent=2))
            included.append("info.json")

        return included

    @staticmethod
    def _sanitize_config(path: Path) -> str:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("server"), dict):
                data["server"]["password"] = "[redacted]"
            return json.dumps(data, indent=2)
        except Exception:
            return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def suggested_filename(game_name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in game_name)
        return f"diagnostics_{safe_name}_{ts}.zip"
