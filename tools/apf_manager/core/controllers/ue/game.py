"""UEGameDetector — identifies a UE4/UE5 game root directory."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...models.ue.game import UEGameInfo
from ._helpers import _find_dir_ci
from ..logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)


class UEGameDetector:
    """
    Detects whether a directory is the root of a UE4/UE5 game.

    Required indicators (all must be present):
      - <game_root>/Engine/                (verification — NOT the shortname dir)
      - <game_root>/<shortname>/Content/Paks/
      - <game_root>/<shortname>/Binaries/
    Optional verification:
      - <game_root>/*.exe                  (stub launcher)
    """

    @staticmethod
    def detect(game_root: Path) -> Optional[UEGameInfo]:
        if not game_root.is_dir():
            return None

        engine_dir = _find_dir_ci(game_root, "Engine")
        # stub .exe at game root (not required for detection, just noted)
        stub_exe: Optional[Path] = None
        try:
            stub_exe = next(
                (p for p in game_root.iterdir()
                 if p.is_file() and p.suffix.lower() == ".exe"),
                None,
            )
        except (PermissionError, OSError) as exc:
            logger.debug("[game_detect] Permission error scanning game root for stub exe: %s", exc)

        # Find the shortname subdir: has both Content/Paks and Binaries/
        try:
            for subdir in game_root.iterdir():
                if not subdir.is_dir():
                    continue
                if engine_dir and subdir == engine_dir:
                    continue
                content = _find_dir_ci(subdir, "Content")
                binaries = _find_dir_ci(subdir, "Binaries")
                if not (content and binaries):
                    continue
                paks = _find_dir_ci(content, "Paks")
                if paks:
                    return UEGameInfo(
                        game_root=game_root,
                        game_shortname=subdir.name,
                        shortname_dir=subdir,
                        engine_dir=engine_dir,
                        stub_exe=stub_exe,
                        content_dir=content,
                        content_paks_dir=paks,
                        binaries_dir=binaries,
                    )
        except (PermissionError, OSError) as exc:
            logger.debug("[game_detect] Permission error scanning game root subdirectories: %s", exc)

        return None
