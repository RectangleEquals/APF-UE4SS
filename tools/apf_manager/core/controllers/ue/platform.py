"""UEPlatformDetector — finds the Binaries/<arch>/ directory."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...models.ue.game import UEGameInfo
from ...models.ue.platform import UEPlatformInfo
from ._helpers import _find_dir_ci
from ..logging.manager import APFLogManager
logger = APFLogManager.get_logger(__name__)

_KNOWN_ARCHES = ("Win64", "WinGDK", "Win32")


class UEPlatformDetector:
    """Locates the platform architecture directory (e.g. Win64/) inside Binaries/."""

    @staticmethod
    def detect(game_info: UEGameInfo) -> Optional[UEPlatformInfo]:
        for arch in _KNOWN_ARCHES:
            d = _find_dir_ci(game_info.binaries_dir, arch)
            if d:
                return UEPlatformInfo(platform_dir=d, arch=arch)
        # Fallback: take the first subdirectory of Binaries/
        try:
            for d in game_info.binaries_dir.iterdir():
                if d.is_dir():
                    return UEPlatformInfo(platform_dir=d, arch=d.name)
        except (PermissionError, OSError) as exc:
            logger.debug("[platform] Permission/OS error scanning Binaries/ directory: %s", exc)
        return None
