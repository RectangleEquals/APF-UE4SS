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

from dataclasses import dataclass, field
from pathlib import Path

MAX_SCAN_DEPTH = 6


@dataclass
class UE4SSResult:
    valid: bool = False
    game_root: Path = field(default_factory=Path)
    binaries_dir: Path = field(default_factory=Path)   # Actual Binaries/ folder
    platform_dir: Path = field(default_factory=Path)   # Arch dir (e.g. Win64/) — parent of ue4ss/
    ue4ss_dir: Path = field(default_factory=Path)
    mods_dir: Path = field(default_factory=Path)
    mods_txt: Path = field(default_factory=Path)
    content_paks_dir: Path = field(default_factory=Path)
    logicmods_dir: Path = field(default_factory=Path)
    missing: list = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.valid


def _find_file_ci(directory: Path, name: str) -> Path | None:
    """Case-insensitive file search within a directory (non-recursive)."""
    name_lower = name.lower()
    try:
        for entry in directory.iterdir():
            if entry.name.lower() == name_lower:
                return entry
    except (PermissionError, OSError):
        pass
    return None


def _find_dir_ci(directory: Path, name: str) -> Path | None:
    """Case-insensitive directory search within a directory (non-recursive)."""
    name_lower = name.lower()
    try:
        for entry in directory.iterdir():
            if entry.is_dir() and entry.name.lower() == name_lower:
                return entry
    except (PermissionError, OSError):
        pass
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
                pass
            return None

        return scan(root, 0)

    @staticmethod
    def _find_content_paks(root: Path) -> Path | None:
        """Find the Content/Paks directory (UE4/UE5 packaging marker)."""
        def scan(directory: Path, depth: int) -> Path | None:
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
                pass
            return None

        return scan(root, 0)
