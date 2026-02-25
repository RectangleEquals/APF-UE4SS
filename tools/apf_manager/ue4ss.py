"""
APF Manager — UE4SS installation detector.

Given a game root folder, recursively scans to locate all UE4SS-related paths:
  - binaries_dir    (contains dwmapi.dll proxy)
  - ue4ss_dir       (contains UE4SS.dll)
  - mods_dir        (target for AP mods)
  - mods_txt        (mods.txt load order file)
  - content_paks_dir (for LogicMods .pak files)
  - logicmods_dir   (may need to be created)

No game-specific paths are hardcoded — works for any UE4SS-modded game.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UE4SSDetectionResult:
    valid: bool = False
    game_root: Path = field(default_factory=Path)
    binaries_dir: Path = field(default_factory=Path)
    ue4ss_dir: Path = field(default_factory=Path)
    mods_dir: Path = field(default_factory=Path)
    mods_txt: Path = field(default_factory=Path)
    content_paks_dir: Path = field(default_factory=Path)
    logicmods_dir: Path = field(default_factory=Path)
    missing: list[str] = field(default_factory=list)


class UE4SSDetector:
    """Detects UE4SS installation by recursive scan from a game root folder."""

    MAX_SCAN_DEPTH = 6

    def detect(self, game_root: str) -> UE4SSDetectionResult:
        result = UE4SSDetectionResult()
        if not game_root:
            result.missing.append("Game root not configured")
            return result

        root = Path(game_root)
        if not root.is_dir():
            result.missing.append(f"Game root folder not found: {root}")
            return result

        result.game_root = root

        # --- Step 1: Find dwmapi.dll (UE4SS proxy) → binaries_dir ---
        dwmapi = self._find_file(root, "dwmapi.dll")
        if dwmapi is None:
            # Fallback: look for ue4ss.dll directly
            ue4ss_dll = self._find_file(root, "ue4ss.dll", case_insensitive=True)
            if ue4ss_dll is None:
                result.missing.append("dwmapi.dll (UE4SS proxy) not found — is UE4SS installed?")
                # Try to continue partial detection anyway
            else:
                # ue4ss_dll is inside <binaries_dir>/ue4ss/
                result.ue4ss_dir = ue4ss_dll.parent
                result.binaries_dir = ue4ss_dll.parent.parent
        else:
            result.binaries_dir = dwmapi.parent

            # --- Step 2: Check ue4ss/UE4SS.dll ---
            ue4ss_dll = result.binaries_dir / "ue4ss" / "UE4SS.dll"
            if not ue4ss_dll.exists():
                # Try case-insensitive search within binaries_dir/ue4ss/
                candidate = self._find_file(result.binaries_dir / "ue4ss", "ue4ss.dll",
                                            case_insensitive=True, max_depth=1)
                if candidate is None:
                    result.missing.append(
                        f"UE4SS.dll not found under {result.binaries_dir / 'ue4ss'}"
                    )
                else:
                    result.ue4ss_dir = candidate.parent
            else:
                result.ue4ss_dir = ue4ss_dll.parent

        # --- Step 3: Check ue4ss/Mods/ ---
        if result.ue4ss_dir.is_dir():
            mods_dir = result.ue4ss_dir / "Mods"
            if mods_dir.is_dir():
                result.mods_dir = mods_dir
            else:
                result.missing.append(f"Mods folder not found at {mods_dir}")
        else:
            result.missing.append("ue4ss directory not found")

        # --- Step 4: Check mods.txt ---
        if result.mods_dir.is_dir():
            mods_txt = result.mods_dir / "mods.txt"
            if mods_txt.exists():
                result.mods_txt = mods_txt
            else:
                result.missing.append(f"mods.txt not found at {mods_txt}")

        # --- Step 5: Find Content/Paks/ ---
        content_paks = self._find_directory(root, "Content/Paks")
        if content_paks is None:
            result.missing.append("Content/Paks directory not found")
        else:
            result.content_paks_dir = content_paks
            result.logicmods_dir = content_paks / "LogicMods"
            # LogicMods may not exist yet — that's fine, we'll create it on deploy

        # --- Determine overall validity ---
        # Valid = at minimum we have mods_dir (can deploy); everything else is best-effort
        critical_missing = [m for m in result.missing
                            if "mods.txt" not in m and "LogicMods" not in m
                            and "Content/Paks" not in m]
        result.valid = result.mods_dir.is_dir() and len(critical_missing) == 0

        return result

    def _find_file(self, root: Path, filename: str, *,
                   case_insensitive: bool = False, max_depth: int | None = None) -> Path | None:
        """Recursively search for a file by name within root up to MAX_SCAN_DEPTH levels."""
        target = filename.lower() if case_insensitive else filename
        return self._scan_for_file(root, target, case_insensitive, 0,
                                   max_depth if max_depth is not None else self.MAX_SCAN_DEPTH)

    def _scan_for_file(self, directory: Path, target: str, ci: bool,
                       depth: int, max_depth: int) -> Path | None:
        if depth > max_depth:
            return None
        try:
            for entry in directory.iterdir():
                name = entry.name.lower() if ci else entry.name
                if entry.is_file() and name == target:
                    return entry
                if entry.is_dir():
                    found = self._scan_for_file(entry, target, ci, depth + 1, max_depth)
                    if found is not None:
                        return found
        except PermissionError:
            pass
        return None

    def _find_directory(self, root: Path, rel_path: str) -> Path | None:
        """Find a directory matching rel_path (forward-slash separated) anywhere under root."""
        parts = rel_path.split("/")
        return self._scan_for_dir(root, parts, 0, self.MAX_SCAN_DEPTH)

    def _scan_for_dir(self, directory: Path, parts: list[str], depth: int, max_depth: int) -> Path | None:
        if depth > max_depth:
            return None
        try:
            for entry in directory.iterdir():
                if entry.is_dir():
                    # Check if this entry matches the start of the path chain
                    if entry.name.lower() == parts[0].lower():
                        if len(parts) == 1:
                            return entry
                        # Try to follow the rest of the chain
                        candidate = entry
                        matched = True
                        for part in parts[1:]:
                            candidate = candidate / part
                            if not candidate.is_dir():
                                # Check case-insensitively
                                parent = candidate.parent
                                found_child = next(
                                    (c for c in parent.iterdir()
                                     if c.is_dir() and c.name.lower() == part.lower()),
                                    None
                                )
                                if found_child is None:
                                    matched = False
                                    break
                                candidate = found_child
                        if matched:
                            return candidate
                    # Recurse into this directory
                    found = self._scan_for_dir(entry, parts, depth + 1, max_depth)
                    if found is not None:
                        return found
        except PermissionError:
            pass
        return None
