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
    from ......core.models.ue4ss import UE4SSResult
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
        self._detection: Optional["UE4SSResult"] = None
        self._profile: Optional["GameProfile"] = None
        self._lock = threading.Lock()
