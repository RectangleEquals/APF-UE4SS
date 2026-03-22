"""
UE4SSDetector — detects an existing UE4SS installation under a given game root.

Works for any UE4/UE5 game that uses UE4SS. Does not depend on game-specific paths.
Detection is based on:
  - dwmapi.dll or winhttp.dll (UE4SS proxy DLL) in the binaries directory
  - UE4SS.dll in the UE4SS folder
  - Mods/ directory and mods.txt
  - Content/Paks/ (confirms UE4/UE5 packaging format)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MAX_SCAN_DEPTH = 6


@dataclass
class UE4SSResult:
    valid: bool = False
    game_root: Path = field(default_factory=Path)
    binaries_dir: Path = field(default_factory=Path)
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

        # --- Find binaries directory (contains dwmapi.dll or winhttp.dll) ---
        binaries_dir = UE4SSDetector._find_binaries(root)
        if binaries_dir is None:
            result.missing.append("Binaries directory (Win64)")
            return result
        result.binaries_dir = binaries_dir

        # --- Find UE4SS directory (ue4ss/ or UE4SS/) ---
        ue4ss_dir = _find_dir_ci(binaries_dir, "ue4ss")
        if ue4ss_dir is None:
            result.missing.append("UE4SS folder")
            return result
        result.ue4ss_dir = ue4ss_dir

        # --- UE4SS.dll ---
        if _find_file_ci(ue4ss_dir, "UE4SS.dll") is None:
            result.missing.append("UE4SS.dll")

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

            logicmods_dir = _find_dir_ci(mods_dir, "LogicMods")
            if logicmods_dir:
                result.logicmods_dir = logicmods_dir

        # --- Content/Paks ---
        content_paks = UE4SSDetector._find_content_paks(root)
        if content_paks:
            result.content_paks_dir = content_paks

        result.valid = len(result.missing) == 0
        return result

    @staticmethod
    def _find_binaries(root: Path) -> Path | None:
        """
        Recursively scan from root (up to MAX_SCAN_DEPTH) for a Win64 binaries directory
        that contains dwmapi.dll or winhttp.dll (UE4SS proxy DLL markers).
        """
        def scan(directory: Path, depth: int) -> Path | None:
            if depth > MAX_SCAN_DEPTH:
                return None
            try:
                for entry in directory.iterdir():
                    if not entry.is_dir():
                        continue
                    if entry.name.lower() == "win64":
                        if (
                            _find_file_ci(entry, "dwmapi.dll") is not None
                            or _find_file_ci(entry, "winhttp.dll") is not None
                        ):
                            return entry
                    result = scan(entry, depth + 1)
                    if result:
                        return result
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
                        result = scan(entry, depth + 1)
                        if result:
                            return result
            except (PermissionError, OSError):
                pass
            return None

        return scan(root, 0)
