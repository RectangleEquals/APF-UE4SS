from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ....core.models.remote.release import RepoRelease


@dataclass
class UpdateInfo:
    """Typed update state for a single component."""
    component: str                           # "manager" | "framework" | "apworld" | "ue4ss"
    current: str                             # installed version string, or "unknown"
    latest_stable: Optional["RepoRelease"]   # None if not yet checked / unavailable
    latest_pre: Optional["RepoRelease"]      # None if no pre-release available
    asset_url: str = ""                      # primary download URL (stable)
    is_update_available: bool = False        # True when latest_stable > current
    is_pre_available: bool = False           # True when latest_pre exists
