"""
SteamLibrary — parse Steam's VDF files to discover installed games.

No Steam API key required. All data comes from local files:
    libraryfolders.vdf  — lists all Steam library paths
    appmanifest_*.acf   — per-game install metadata (AppID, name, installdir)

UEFilter — heuristic to detect UE4/UE5 games from the install directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# VDF parser (minimal, handles libraryfolders.vdf and appmanifest_*.acf)
# ---------------------------------------------------------------------------

def _parse_vdf(text: str) -> dict:
    """
    Minimal Valve Data Format (VDF) parser.
    Handles flat key-value and one level of nested blocks.
    Returns a nested dict.
    """
    root: dict = {}
    stack: list[dict] = [root]
    key: Optional[str] = None
    i = 0
    lines = text.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        if stripped == "{":
            if key is not None:
                new_dict: dict = {}
                stack[-1][key] = new_dict
                stack.append(new_dict)
                key = None
            continue

        if stripped == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
            continue

        # Match quoted key or key-value pair
        # Pattern: "key" or "key" "value"
        m = re.match(r'"([^"]*)"(?:\s+"([^"]*)")?', stripped)
        if m:
            k = m.group(1)
            v = m.group(2)
            if v is None:
                key = k
            else:
                stack[-1][k] = v
                key = None

    return root


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SteamGame:
    app_id: int
    name: str
    install_dir: Path          # Absolute path to game's install directory
    is_ue: bool = False        # Heuristic: True if UE4 or UE5 game
    extra: dict = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# SteamLibrary
# ---------------------------------------------------------------------------

class SteamLibrary:
    """
    Discovers installed Steam games from the local file system.

    Usage:
        lib = SteamLibrary(override_vdf_path=None)
        games = lib.scan()  # list[SteamGame]
    """

    def __init__(self, override_vdf_path: Optional[str] = None) -> None:
        self._override = Path(override_vdf_path) if override_vdf_path else None

    # -----------------------------------------------------------------------
    # Public
    # -----------------------------------------------------------------------

    def scan(self) -> list[SteamGame]:
        """Return all installed Steam games. Returns [] if Steam not found."""
        vdf_path = self._find_libraryfolders_vdf()
        if not vdf_path:
            return []
        library_dirs = self._parse_library_dirs(vdf_path)
        games: list[SteamGame] = []
        seen: set[int] = set()
        for lib_dir in library_dirs:
            for game in self._scan_library(lib_dir):
                if game.app_id not in seen:
                    seen.add(game.app_id)
                    games.append(game)
        return sorted(games, key=lambda g: g.name.lower())

    # -----------------------------------------------------------------------
    # VDF path resolution
    # -----------------------------------------------------------------------

    def _find_libraryfolders_vdf(self) -> Optional[Path]:
        if self._override and self._override.exists():
            return self._override

        # Default Steam locations (Windows / Linux / macOS)
        candidates = [
            Path(r"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf"),
            Path(r"C:\Program Files\Steam\steamapps\libraryfolders.vdf"),
            Path.home() / ".steam" / "steam" / "steamapps" / "libraryfolders.vdf",
            Path.home() / ".local" / "share" / "Steam" / "steamapps" / "libraryfolders.vdf",
            Path("/Applications/Steam.app/Contents/MacOS/Steam") / "steamapps" / "libraryfolders.vdf",
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    # -----------------------------------------------------------------------
    # Parse library dirs
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_library_dirs(vdf_path: Path) -> list[Path]:
        """Extract all Steam library paths from libraryfolders.vdf."""
        try:
            text = vdf_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        data = _parse_vdf(text)
        dirs: list[Path] = []

        # The root key is "libraryfolders" which contains numbered entries
        # Each entry has a "path" key.
        root = data.get("libraryfolders", data)
        for key, val in root.items():
            if isinstance(val, dict):
                path_str = val.get("path", "")
                if path_str:
                    p = Path(path_str) / "steamapps"
                    if p.is_dir():
                        dirs.append(p)
            elif key == "path":
                # Older VDF format: direct path values
                p = Path(val) / "steamapps"
                if p.is_dir():
                    dirs.append(p)

        # Always include the default steamapps dir alongside the vdf
        default_steamapps = vdf_path.parent
        if default_steamapps not in dirs and default_steamapps.is_dir():
            dirs.insert(0, default_steamapps)

        return dirs

    # -----------------------------------------------------------------------
    # Scan a single library dir
    # -----------------------------------------------------------------------

    @staticmethod
    def _scan_library(steamapps_dir: Path) -> list[SteamGame]:
        games: list[SteamGame] = []
        for acf_file in steamapps_dir.glob("appmanifest_*.acf"):
            game = SteamLibrary._parse_acf(acf_file, steamapps_dir)
            if game:
                games.append(game)
        return games

    @staticmethod
    def _parse_acf(acf_path: Path, steamapps_dir: Path) -> Optional[SteamGame]:
        try:
            text = acf_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        data = _parse_vdf(text)
        state = data.get("AppState", {})

        try:
            app_id = int(state.get("appid", "0"))
        except ValueError:
            return None

        if app_id == 0:
            return None

        name = state.get("name", f"App {app_id}")
        install_dir_name = state.get("installdir", "")
        install_dir = steamapps_dir / "common" / install_dir_name

        if not install_dir.is_dir():
            return None

        is_ue = UEFilter.is_ue_game(install_dir)

        return SteamGame(
            app_id=app_id,
            name=name,
            install_dir=install_dir,
            is_ue=is_ue,
        )


# ---------------------------------------------------------------------------
# UEFilter
# ---------------------------------------------------------------------------

class UEFilter:
    """
    Heuristic detection of UE4/UE5 game installations.

    Checks for ≥2 of:
      - Content/Paks/ directory containing .pak files
      - Engine/ directory
      - Binaries/ directory (at root or nested in a platform folder)
    """

    _MARKERS = [
        ("Content/Paks", lambda p: any(p.glob("*.pak"))),  # must have .pak files
        ("Engine", lambda p: p.is_dir()),
        ("Binaries", lambda p: p.is_dir()),
    ]

    @classmethod
    def is_ue_game(cls, install_dir: Path) -> bool:
        hits = 0
        for rel, check in cls._MARKERS:
            candidate = install_dir / rel
            if candidate.exists() and check(candidate):
                hits += 1
            else:
                # Also check one level deep (e.g. GameName/Content/Paks/)
                for child in install_dir.iterdir():
                    if child.is_dir():
                        nested = child / rel
                        if nested.exists() and check(nested):
                            hits += 1
                            break
            if hits >= 2:
                return True
        return hits >= 2