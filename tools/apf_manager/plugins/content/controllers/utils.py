"""Content plugin utility helpers — shared across controllers."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ....core.models.config import GameProfile


def slug_game_id(profile: "Optional[GameProfile]", registry_svc=None) -> str:
    """Return the human-readable game ID slug used for install state paths.

    Mirrors PipelineController.get_game_id() without circular imports.
    Priority: registry._get_game_id() → profile.display_name slug → "".
    """
    if registry_svc and hasattr(registry_svc, "_get_game_id"):
        try:
            gid = registry_svc._get_game_id()
            if gid:
                return gid
        except Exception:
            pass
    if profile and profile.display_name:
        return profile.display_name.lower().replace(" ", "_")
    return ""
