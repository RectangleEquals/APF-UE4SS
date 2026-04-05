"""
APFConfig — global settings and per-game profiles.

Saved to ~/.apf_manager/config.json (user home, survives app updates).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


def _config_path() -> Path:
    return Path.home() / ".apf_manager" / "config.json"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GameProfile:
    game_id: str
    display_name: str
    game_root: str
    steam_app_id: Optional[int] = None     # None for custom (non-Steam) games
    custom_thumbnail: Optional[str] = None  # Absolute path to user-supplied image
    repo_api_url: str = ""                  # GitHub API URL for player-mode update checks
    # Dev-only fields:
    # source_project: root of the APF source repo — deploy plugin uses this to
    #   resolve manual_steps file content and packager uses it for source files.
    source_project: str = ""
    # build_dir: path to compiled DLL output (e.g. build/Release/bin) —
    #   deploy plugin copies APFrameworkCore.dll + APClientLib.dll from here.
    build_dir: str = ""

    @staticmethod
    def new(display_name: str, game_root: str, **kwargs) -> "GameProfile":
        return GameProfile(
            game_id=str(uuid.uuid4()),
            display_name=display_name,
            game_root=game_root,
            **kwargs,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "GameProfile":
        return GameProfile(
            game_id=d.get("game_id", str(uuid.uuid4())),
            display_name=d.get("display_name", "Unknown Game"),
            game_root=d.get("game_root", ""),
            steam_app_id=d.get("steam_app_id"),
            custom_thumbnail=d.get("custom_thumbnail"),
            repo_api_url=d.get("repo_api_url", ""),
            source_project=d.get("source_project", ""),
            build_dir=d.get("build_dir", ""),
        )


@dataclass
class GlobalSettings:
    mode: str = "player"                          # "player" | "dev"
    games: dict = field(default_factory=dict)     # game_id -> GameProfile (stored as dicts)
    last_game_id: Optional[str] = None
    steam_library_override: Optional[str] = None  # Override for Steam libraryfolders.vdf path
    disabled_plugins: list = field(default_factory=list)  # plugin IDs to skip loading
    user_registries: list = field(default_factory=list)   # [{"url": str, "added_at": ISO8601}]
    window_width: int = 1280
    window_height: int = 720
    window_x: Optional[int] = None
    window_y: Optional[int] = None
    window_maximized: bool = False


# ---------------------------------------------------------------------------
# APFConfig singleton-style manager
# ---------------------------------------------------------------------------

class APFConfig:
    def __init__(self) -> None:
        self._settings = GlobalSettings()
        self._path = _config_path()

    def load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            s = self._settings
            s.mode = data.get("mode", "player")
            s.last_game_id = data.get("last_game_id")
            s.steam_library_override = data.get("steam_library_override")
            s.disabled_plugins = data.get("disabled_plugins", [])
            s.user_registries = data.get("user_registries", [])
            s.window_width = data.get("window_width", 1280)
            s.window_height = data.get("window_height", 720)
            s.window_x = data.get("window_x")
            s.window_y = data.get("window_y")
            s.window_maximized = data.get("window_maximized", False)
            s.games = {
                gid: GameProfile.from_dict(gdata)
                for gid, gdata in data.get("games", {}).items()
            }
        except Exception:
            pass  # Corrupt config — use defaults

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        s = self._settings
        data = {
            "mode": s.mode,
            "last_game_id": s.last_game_id,
            "steam_library_override": s.steam_library_override,
            "disabled_plugins": s.disabled_plugins,
            "window_width": s.window_width,
            "window_height": s.window_height,
            "window_x": s.window_x,
            "window_y": s.window_y,
            "window_maximized": s.window_maximized,
            "games": {gid: g.to_dict() for gid, g in s.games.items()},
            "user_registries": s.user_registries,
        }
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # -----------------------------------------------------------------------
    # Accessors
    # -----------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._settings.mode

    @mode.setter
    def mode(self, value: str) -> None:
        self._settings.mode = value

    @property
    def is_dev(self) -> bool:
        return self._settings.mode == "dev"

    @property
    def games(self) -> dict[str, GameProfile]:
        return self._settings.games  # type: ignore[return-value]

    @property
    def last_game_id(self) -> Optional[str]:
        return self._settings.last_game_id

    @last_game_id.setter
    def last_game_id(self, value: Optional[str]) -> None:
        self._settings.last_game_id = value

    @property
    def steam_library_override(self) -> Optional[str]:
        return self._settings.steam_library_override

    @steam_library_override.setter
    def steam_library_override(self, value: Optional[str]) -> None:
        self._settings.steam_library_override = value

    @property
    def disabled_plugins(self) -> list[str]:
        return self._settings.disabled_plugins  # type: ignore[return-value]

    def add_game(self, profile: GameProfile) -> None:
        self._settings.games[profile.game_id] = profile
        self.save()

    def remove_game(self, game_id: str) -> None:
        self._settings.games.pop(game_id, None)
        if self._settings.last_game_id == game_id:
            self._settings.last_game_id = None
        self.save()

    def get_game(self, game_id: str) -> Optional[GameProfile]:
        return self._settings.games.get(game_id)

    @property
    def window_width(self) -> int:
        return self._settings.window_width

    @window_width.setter
    def window_width(self, value: int) -> None:
        self._settings.window_width = value

    @property
    def window_height(self) -> int:
        return self._settings.window_height

    @window_height.setter
    def window_height(self, value: int) -> None:
        self._settings.window_height = value

    @property
    def window_x(self) -> Optional[int]:
        return self._settings.window_x

    @window_x.setter
    def window_x(self, value: Optional[int]) -> None:
        self._settings.window_x = value

    @property
    def window_y(self) -> Optional[int]:
        return self._settings.window_y

    @window_y.setter
    def window_y(self, value: Optional[int]) -> None:
        self._settings.window_y = value

    @property
    def window_maximized(self) -> bool:
        return self._settings.window_maximized

    @window_maximized.setter
    def window_maximized(self, value: bool) -> None:
        self._settings.window_maximized = value

    def set_plugin_disabled(self, plugin_id: str, disabled: bool) -> None:
        if disabled and plugin_id not in self._settings.disabled_plugins:
            self._settings.disabled_plugins.append(plugin_id)
        elif not disabled and plugin_id in self._settings.disabled_plugins:
            self._settings.disabled_plugins.remove(plugin_id)
        self.save()

    # -----------------------------------------------------------------------
    # Registry management
    # -----------------------------------------------------------------------

    def get_user_registries(self, game_id: str = "") -> list[dict]:
        """Return user-added registry entries, optionally filtered by game_id.

        Entries without a stored game_id (added before this field existed) are
        always included so older data is not silently dropped.
        """
        entries = list(self._settings.user_registries)
        if not game_id:
            return entries
        return [r for r in entries if not r.get("game_id") or r["game_id"] == game_id]

    def add_user_registry(self, url: str, game_id: str = "") -> None:
        """Add a registry URL if not already present, then save."""
        from datetime import datetime, timezone
        existing_urls = {r["url"] for r in self._settings.user_registries}
        if url not in existing_urls:
            entry: dict = {
                "url": url,
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
            if game_id:
                entry["game_id"] = game_id
            self._settings.user_registries.append(entry)
            self.save()

    def remove_user_registry(self, url: str) -> None:
        """Remove a registry URL by URL string, then save."""
        self._settings.user_registries = [
            r for r in self._settings.user_registries if r["url"] != url
        ]
        self.save()
