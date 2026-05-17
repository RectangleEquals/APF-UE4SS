"""UE4SSInstallDetector — detects a UE4SS installation under a platform directory."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...models.ue.game import UEGameInfo
from ...models.ue.platform import UEPlatformInfo
from ...models.ue.ue4ss import UE4SSInfo
from ._helpers import _find_dir_ci, _find_file_ci


def _read_pe_file_version(dll_path: Path) -> Optional[str]:
    """Read FileVersion from a Windows PE DLL using ctypes (no external deps)."""
    try:
        import ctypes
        import ctypes.wintypes

        class _VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [
                ("dwSignature",        ctypes.c_uint32),
                ("dwStrucVersion",     ctypes.c_uint32),
                ("dwFileVersionMS",    ctypes.c_uint32),
                ("dwFileVersionLS",    ctypes.c_uint32),
                ("dwProductVersionMS", ctypes.c_uint32),
                ("dwProductVersionLS", ctypes.c_uint32),
                ("dwFileFlagsMask",    ctypes.c_uint32),
                ("dwFileFlags",        ctypes.c_uint32),
                ("dwFileOS",           ctypes.c_uint32),
                ("dwFileType",         ctypes.c_uint32),
                ("dwFileSubtype",      ctypes.c_uint32),
                ("dwFileDateMS",       ctypes.c_uint32),
                ("dwFileDateLS",       ctypes.c_uint32),
            ]

        path_str = str(dll_path)
        dummy = ctypes.c_uint32(0)
        size = ctypes.windll.version.GetFileVersionInfoSizeW(path_str, ctypes.byref(dummy))
        if not size:
            return None
        buf = (ctypes.c_char * size)()
        if not ctypes.windll.version.GetFileVersionInfoW(path_str, 0, size, buf):
            return None
        p_info = ctypes.c_void_p()
        l_info = ctypes.c_uint32()
        if not ctypes.windll.version.VerQueryValueW(
            buf, "\\", ctypes.byref(p_info), ctypes.byref(l_info)
        ):
            return None
        ffi = ctypes.cast(p_info, ctypes.POINTER(_VS_FIXEDFILEINFO)).contents
        if ffi.dwSignature != 0xFEEF04BD:
            return None
        ms, ls = ffi.dwFileVersionMS, ffi.dwFileVersionLS
        major, minor, patch, build = ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF
        if build:
            return f"{major}.{minor}.{patch}.{build}"
        if patch:
            return f"{major}.{minor}.{patch}"
        return f"{major}.{minor}"
    except Exception:
        return None


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

        # Read version from the DLL (works for both official and custom UE4SS builds)
        ue4ss_dll = _find_file_ci(ue4ss_dir, "ue4ss.dll")
        if ue4ss_dll:
            info.version = _read_pe_file_version(ue4ss_dll)

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
