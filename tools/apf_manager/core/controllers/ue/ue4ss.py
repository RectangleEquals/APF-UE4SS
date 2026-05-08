"""UE4SSInstallDetector — detects a UE4SS installation under a platform directory."""
from __future__ import annotations

from ...models.ue.game import UEGameInfo
from ...models.ue.platform import UEPlatformInfo
from ...models.ue.ue4ss import UE4SSInfo
from ._helpers import _find_dir_ci, _find_file_ci


class UE4SSInstallDetector:
    """
    Checks for UE4SS under <platform_dir>/ue4ss/.

    Required: ue4ss.dll inside the ue4ss/ directory.
    Optional: dwmapi.dll in platform_dir, Mods/ subdirectory, mods.txt.
    LogicMods: located at <game_shortname>/Content/Paks/LogicMods/ (BPModLoaderMod output).
    """

    @staticmethod
    def detect(platform_info: UEPlatformInfo, game_info: UEGameInfo) -> UE4SSInfo:
        info = UE4SSInfo()

        ue4ss_dir = _find_dir_ci(platform_info.platform_dir, "ue4ss")
        if not ue4ss_dir or not _find_file_ci(ue4ss_dir, "ue4ss.dll"):
            info.missing.append("UE4SS not installed")
            return info

        info.ue4ss_dir = ue4ss_dir
        info.has_dwmapi = _find_file_ci(platform_info.platform_dir, "dwmapi.dll") is not None

        mods_dir = _find_dir_ci(ue4ss_dir, "Mods")
        if mods_dir is None:
            info.missing.append("Mods directory")
        else:
            info.mods_dir = mods_dir
            mods_txt = _find_file_ci(mods_dir, "mods.txt")
            if mods_txt is None:
                info.missing.append("mods.txt")
            else:
                info.mods_txt = mods_txt

        # LogicMods only exists after BPModLoaderMod installs BP pak mods
        logicmods = _find_dir_ci(game_info.content_paks_dir, "LogicMods")
        if logicmods:
            info.logicmods_dir = logicmods

        return info
