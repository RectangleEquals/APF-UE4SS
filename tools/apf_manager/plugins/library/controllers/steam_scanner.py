"""
SteamLibrary — parse Steam VDF files to discover installed games.
UEFilter — heuristic to detect UE4/UE5 games from the install directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..models.steam import SteamGame, parse_vdf


class SteamLibrary:
    """Discovers installed Steam games from the local file system."""

    def __init__(self, override_vdf_path: Optional[str] = None) -> None:
        self._override = Path(override_vdf_path) if override_vdf_path else None

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

    def _find_libraryfolders_vdf(self) -> Optional[Path]:
        if self._override and self._override.exists():
            return self._override
        candidates = [
            Path(r"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf"),
            Path(r"C:\Program Files\Steam\steamapps\libraryfolders.vdf"),
            Path.home() / ".steam" / "steam" / "steamapps" / "libraryfolders.vdf",
            Path.home() / ".local" / "share" / "Steam" / "steamapps" / "libraryfolders.vdf",
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    @staticmethod
    def _parse_library_dirs(vdf_path: Path) -> list[Path]:
        try:
            text = vdf_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        data = parse_vdf(text)
        dirs: list[Path] = []
        root = data.get("libraryfolders", data)
        for key, val in root.items():
            if isinstance(val, dict):
                path_str = val.get("path", "")
                if path_str:
                    p = Path(path_str) / "steamapps"
                    if p.is_dir():
                        dirs.append(p)
            elif key == "path":
                p = Path(val) / "steamapps"
                if p.is_dir():
                    dirs.append(p)
        default_steamapps = vdf_path.parent
        if default_steamapps not in dirs and default_steamapps.is_dir():
            dirs.insert(0, default_steamapps)
        return dirs

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
        data = parse_vdf(text)
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
        return SteamGame(
            app_id=app_id,
            name=name,
            install_dir=install_dir,
            is_ue=UEFilter.is_ue_game(install_dir),
        )


class UEFilter:
    """Heuristic detection of UE4/UE5 game installations."""

    _MARKERS = [
        ("Content/Paks", lambda p: any(p.glob("*.pak"))),
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
                for child in install_dir.iterdir():
                    if child.is_dir():
                        nested = child / rel
                        if nested.exists() and check(nested):
                            hits += 1
                            break
            if hits >= 2:
                return True
        return hits >= 2
