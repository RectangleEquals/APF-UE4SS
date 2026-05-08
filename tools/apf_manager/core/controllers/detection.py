"""
UE4SSDetector — detects an existing UE4SS installation under a given game root.

Works for any UE4/UE5 game that uses UE4SS. Does not depend on game-specific paths.
Detection is based on:
  - ue4ss/UE4SS.dll (universal presence marker for all UE4SS versions)
  - Mods/ directory and mods.txt
  - Content/Paks/ (confirms UE4/UE5 packaging format)

Path structure (typical):
  <game_root>/<short_name>/Binaries/<arch>/ue4ss/UE4SS.dll
                           ^binaries_dir   ^platform_dir  ^ue4ss_dir
"""


from __future__ import annotations
import sys
from pathlib import Path
from ..models.ue4ss import UE4SSResult

MAX_SCAN_DEPTH = 6


def _find_file_ci(directory: Path, name: str) -> Path | None:
    """Case-insensitive file search within a directory (non-recursive)."""
    name_lower = name.lower()
    try:
        for entry in directory.iterdir():
            if entry.name.lower() == name_lower:
                return entry
    except (PermissionError, OSError):
        print(f"[APFManager] Failed to find '{name}' file from '{directory}'", file=sys.stderr)
    return None


def _find_dir_ci(directory: Path, name: str) -> Path | None:
    """Case-insensitive directory search within a directory (non-recursive)."""
    name_lower = name.lower()
    try:
        for entry in directory.iterdir():
            if entry.is_dir() and entry.name.lower() == name_lower:
                return entry
    except (PermissionError, OSError):
        print(f"[APFManager] Failed to find '{name}' directory from '{directory}'", file=sys.stderr)
    return None


class UE4SSDetector:
    @staticmethod
    def detect(game_root: str | Path) -> UE4SSResult:
        """
        Scan from game_root to find a UE4SS installation.
        Returns a UE4SSResult describing what was found and what is missing.
        """
        root = Path(game_root)
        result = UE4SSResult(game_root=root)

        # --- Find ue4ss/ directory containing UE4SS.dll ---
        ue4ss_dir = UE4SSDetector._find_ue4ss_dir(root)
        if ue4ss_dir is None:
            # UE4SS absent — still locate Binaries/<arch>/ so fresh installs know where to extract
            platform_dir = UE4SSDetector._find_platform_dir(root)
            if platform_dir:
                result.platform_dir = platform_dir
                parent_of_platform = platform_dir.parent
                if parent_of_platform.name.lower() == "binaries":
                    result.binaries_dir = parent_of_platform
            result.missing.append("UE4SS not installed")
            return result
        result.ue4ss_dir = ue4ss_dir

        # platform_dir = the arch directory (e.g. Win64/) containing ue4ss/
        result.platform_dir = ue4ss_dir.parent

        # binaries_dir = the actual Binaries/ folder (parent of platform_dir),
        # only set if the name confirms it (handles non-standard layouts gracefully)
        parent_of_platform = ue4ss_dir.parent.parent
        if parent_of_platform.name.lower() == "binaries":
            result.binaries_dir = parent_of_platform

        # --- Mods directory ---
        mods_dir = _find_dir_ci(ue4ss_dir, "Mods")
        if mods_dir is None:
            result.missing.append("Mods directory")
        else:
            result.mods_dir = mods_dir
            mods_txt = _find_file_ci(mods_dir, "mods.txt")
            if mods_txt is None:
                result.missing.append("mods.txt")
            else:
                result.mods_txt = mods_txt

        # --- Content/Paks ---
        content_paks = UE4SSDetector._find_content_paks(root)
        if content_paks:
            result.content_paks_dir = content_paks
            logicmods = _find_dir_ci(content_paks, "LogicMods")
            if logicmods:
                result.logicmods_dir = logicmods

        result.valid = len(result.missing) == 0
        return result

    @staticmethod
    def _find_ue4ss_dir(root: Path) -> Path | None:
        """
        Recursively scan from root (up to MAX_SCAN_DEPTH) for a ue4ss/ directory
        containing UE4SS.dll — the universal presence marker for all UE4SS versions.
        """
        def scan(directory: Path, depth: int) -> Path | None:
            print(f"[APFManager] Scanning '{directory}' for UE4SS... (depth='{depth}')", file=sys.stderr)
            if depth > MAX_SCAN_DEPTH:
                return None
            candidate = _find_dir_ci(directory, "ue4ss")
            if candidate and _find_file_ci(candidate, "UE4SS.dll"):
                return candidate
            try:
                for entry in directory.iterdir():
                    if entry.is_dir():
                        found = scan(entry, depth + 1)
                        if found:
                            return found
            except (PermissionError, OSError):
                print(f"[APFManager] Failed to detect UE4SS directory from '{directory}' (root='{root}', depth='{depth}')", file=sys.stderr)
            return None

        return scan(root, 0)

    @staticmethod
    def _find_platform_dir(root: Path) -> Path | None:
        """Find Binaries/<arch>/ even when ue4ss/ is absent (fresh install)."""
        def scan(directory: Path, depth: int) -> Path | None:
            print(f"[APFManager] Scanning '{directory}' for UE binaries/platform path... (depth='{depth}')", file=sys.stderr)
            if depth > MAX_SCAN_DEPTH:
                return None
            binaries = _find_dir_ci(directory, "Binaries")
            if binaries:
                for arch in ("Win64", "WinGDK", "Win32"):
                    arch_dir = _find_dir_ci(binaries, arch)
                    if arch_dir:
                        return arch_dir
                try:
                    for entry in binaries.iterdir():
                        if entry.is_dir():
                            return entry
                except (PermissionError, OSError):
                    print(f"[APFManager] Failed to detect UE platform path from '{directory}' (root='{root}', binaries='{binaries}', depth='{depth}')", file=sys.stderr)
            try:
                for entry in directory.iterdir():
                    if entry.is_dir() and entry.name.lower() != "binaries":
                        found = scan(entry, depth + 1)
                        if found:
                            return found
            except (PermissionError, OSError):
                print(f"[APFManager] Failed to detect UE binaries path from '{directory}' (root='{root}', depth='{depth}')", file=sys.stderr)
            return None

        return scan(root, 0)

    @staticmethod
    def _find_content_paks(root: Path) -> Path | None:
        """Find the Content/Paks directory (UE4/UE5 packaging marker)."""
        def scan(directory: Path, depth: int) -> Path | None:
            print(f"[APFManager] Scanning '{directory}' for Content/Paks path... (depth='{depth}')", file=sys.stderr)
            if depth > MAX_SCAN_DEPTH:
                return None
            content = _find_dir_ci(directory, "Content")
            if content:
                paks = _find_dir_ci(content, "Paks")
                if paks:
                    return paks
            try:
                for entry in directory.iterdir():
                    if entry.is_dir() and entry.name.lower() != "content":
                        found = scan(entry, depth + 1)
                        if found:
                            return found
            except (PermissionError, OSError):
                print(f"[APFManager] Failed to detect Content/Paks path from '{directory}' (root='{root}', depth='{depth}')", file=sys.stderr)
            return None

        return scan(root, 0)
