"""
DeployService — service API for mod deployment operations.

Registered as the "deploy" service by the mods plugin.

Owns the shared ModsTextManager instance so all tabs share the same in-memory state.
"""

from __future__ import annotations

import threading
from typing import Optional, TYPE_CHECKING

from .content import DeployContentMixin
from .load_order import DeployLoadOrderMixin
from .impact import DeployImpactMixin

if TYPE_CHECKING:
    from ......core.models.config import GameProfile
    from ......core.models.ue.result import DetectionResult
    from ....models.mods.config import ModsTextManager


class DeployService(DeployContentMixin, DeployLoadOrderMixin, DeployImpactMixin):
    """
    Manages mod deployment, load order (mods.txt), and uninstall impact analysis.

    Registered as the "deploy" service by plugins/mods/__init__.py.
    Inherits modular mixin slices: DeployContentMixin, DeployLoadOrderMixin, DeployImpactMixin.
    """

    def __init__(self, host) -> None:
        self._host = host
        self._mods_txt: Optional["ModsTextManager"] = None
        self._detection: Optional["DetectionResult"] = None
        self._profile: Optional["GameProfile"] = None
        self._lock = threading.Lock()

    def get_installed_version_for_type(self, install_type: str, game_id: str) -> str:
        """Return the tracked installed version for a given install_type, or 'unknown'."""
        try:
            from ....models.state.install import InstallStateManager
            state = InstallStateManager(game_id)
            for entry in state.get_all():
                if entry.get("install_type") == install_type:
                    return entry.get("version", "unknown") or "unknown"
        except Exception:
            pass
        return "unknown"
