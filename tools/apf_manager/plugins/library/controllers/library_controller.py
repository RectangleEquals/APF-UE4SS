"""
LibraryController — business logic for the Game Library screen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

from .steam_scanner import SteamLibrary
from .thumbnail_cache import ThumbnailCache
from ..models.steam import SteamGame
from ....core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)

if TYPE_CHECKING:
    from ....core.models.config import APFConfig, GameProfile
    from ....core.models.ue.result import DetectionResult


def _has_content_paks(path: Path) -> bool:
    try:
        return (path / "Content" / "Paks").is_dir()
    except (PermissionError, OSError):
        return False


def _dirs_at_depth(path: Path, depth: int) -> list[Path]:
    if depth == 0:
        return [path]
    result: list[Path] = []
    try:
        for child in path.iterdir():
            if child.is_dir():
                result.extend(_dirs_at_depth(child, depth - 1))
    except (PermissionError, OSError) as exc:
        logger.debug("[library] Permission error traversing %s: %s", path, exc)
    return result


class LibraryController:
    def __init__(self, host, config: "APFConfig") -> None:
        self._host = host
        self._config = config
        self._thumbnail_cache: Optional[ThumbnailCache] = None

    def scan_steam_games(self) -> list[SteamGame]:
        """Scan Steam libraries and return UE games."""
        try:
            override = self._config.steam_library_override
            lib = SteamLibrary(override_vdf_path=override)
            all_games = lib.scan()
            return [g for g in all_games if g.is_ue]
        except Exception:
            return []

    def resolve_ue_root(self, selected: Path) -> Optional[Path]:
        """
        Given any path the user selected, resolve to the UE game_root
        (parent of the <short_name> directory that contains Content/Paks).
        """
        for depth in range(4):
            for candidate in _dirs_at_depth(selected, depth):
                if _has_content_paks(candidate):
                    return candidate.parent

        for root_candidate in [selected, *selected.parents]:
            try:
                for child in root_candidate.iterdir():
                    if child.is_dir() and _has_content_paks(child):
                        return root_candidate
            except (PermissionError, OSError):
                continue
        return None

    def detect_game_name(self, game_root: Path) -> str:
        return game_root.name.replace("_", " ").replace("-", " ").title()

    def detect_game(self, game_root: str | Path) -> "DetectionResult":
        from ....core.controllers.ue import UEDetector
        return UEDetector.detect(game_root)

    def get_ue4ss_badge_status(self, profile: "GameProfile") -> str:
        """Returns 'ok' | 'warn' | 'error' | 'unknown' for UE4SS badge."""
        if not profile.game_root:
            return "unknown"
        root = Path(profile.game_root)
        if not root.is_dir():
            return "error"
        detection = self.detect_game(root)
        if detection.valid:
            return "ok"
        elif detection.is_ue_game:
            return "warn"
        else:
            return "error"

    def add_custom_game(
        self,
        game_root: Path,
        display_name: str,
        custom_thumbnail: Optional[str] = None,
    ) -> "GameProfile":
        from ....core.models.config import GameProfile
        profile = GameProfile.new(
            display_name=display_name,
            game_root=str(game_root),
            custom_thumbnail=custom_thumbnail,
        )
        self._config.add_game(profile)
        return profile

    def remove_game(self, profile: "GameProfile") -> None:
        self._config.remove_game(profile.game_id)

    def navigate_to_game(self, profile: "GameProfile") -> None:
        if profile.game_id not in self._config.games:
            self._config.add_game(profile)
        self._host.navigate_to_game(profile)

    def fetch_thumbnail(
        self,
        app_id: int,
        on_loaded: Callable[[Optional[Path]], None],
    ) -> Optional[Path]:
        cache = self._get_thumbnail_cache()
        if not cache:
            return None
        cached = cache.path(app_id)
        if cached:
            return cached
        cache.get(app_id, on_loaded=on_loaded)
        return None

    def check_updates_all(self, on_done: Callable) -> None:
        """Trigger update check for all components via the updates service."""
        if self._host.has_service("updates"):
            self._host.get_service("updates").check_all(on_done=on_done)

    def get_update_info(self, component: str):
        """Return UpdateInfo for the given component, or None."""
        if not self._host.has_service("updates"):
            return None
        return self._host.get_service("updates").get_update_info(component)

    def get_manager_update_info(self):
        """Return UpdateInfo for the manager component, or None."""
        return self.get_update_info("manager")

    def open_docs(self) -> None:
        """Open the docs viewer if the service is available."""
        try:
            svc = self._host.get_service("docs_viewer")
            if svc:
                svc.open()
        except Exception as exc:
            logger.warning("[library] Could not open docs: %s", exc)

    def _get_thumbnail_cache(self) -> Optional[ThumbnailCache]:
        if self._thumbnail_cache is None:
            try:
                self._thumbnail_cache = ThumbnailCache()
            except Exception as exc:
                logger.warning("[library] Failed to initialize ThumbnailCache: %s", exc)
        return self._thumbnail_cache
