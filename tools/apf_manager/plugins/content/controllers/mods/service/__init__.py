"""
ModService — scans a Mods directory and exposes ModInfo objects.

Registered as the "mods" service by the mods plugin.
Re-scans automatically when the active game changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .scanner import ModScannerMixin
from .capabilities import ModCapabilitiesMixin

if TYPE_CHECKING:
    from ......core.controllers.plugin_host import PluginHost
    from ......core.models.config import GameProfile


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Framework mod id must match exactly: archipelago.<game_id>.framework
_FRAMEWORK_MOD_RE = re.compile(r"^archipelago\.[a-z0-9_]+\.framework$")

# Folder names inside mods_dir that are never AP mods — excluded from all scans.
_SCAN_EXCLUDE: frozenset[str] = frozenset({"shared"})


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ItemDef:
    name: str
    type: str = "filler"
    amount: object = 1
    amount_min: Optional[int] = None
    placement: list = field(default_factory=list)
    enabled_if: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class LocationDef:
    name: str
    logic: str = ""
    out_of_logic: bool = False
    tags: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class GoalDef:
    name: str
    display_name: str = ""
    description: str = ""
    condition: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class OptionDef:
    name: str
    type: str = "toggle"
    default: object = 0
    description: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class ItemOverrideDef:
    item_name: str
    override_type: str = ""
    requires_option: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class ModInfo:
    # Source location
    folder_name: str
    folder_path: Path

    # manifest.json — identity
    mod_id: str = ""
    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""

    # manifest.json — dependencies
    depends: list = field(default_factory=list)
    incompatible: list = field(default_factory=list)

    # manifest.json — capabilities
    capabilities_includes: list = field(default_factory=list)
    vocab_validation: bool = False
    items: list = field(default_factory=list)
    locations: list = field(default_factory=list)
    goals: list = field(default_factory=list)
    options: list = field(default_factory=list)
    item_overrides: list = field(default_factory=list)

    # Component detection (determined from filesystem structure)
    components: list = field(default_factory=lambda: ["lua"])
    bp_pak_files: list = field(default_factory=list)
    is_orphaned: bool = False

    @property
    def bp_mods(self) -> list:
        """Typed BpLogicMod instances derived from bp_pak_files (computed, not stored)."""
        from ....models.descriptors.bp_component import parse_bp_mods
        return parse_bp_mods(self.bp_pak_files)

    @property
    def is_managed(self) -> bool:
        return not self.is_orphaned and bool(self.mod_id)

    @property
    def is_ap_mod(self) -> bool:
        return bool(self.mod_id)

    @property
    def display_name(self) -> str:
        return self.name or self.folder_name


# ---------------------------------------------------------------------------
# ModService
# ---------------------------------------------------------------------------

class ModService(ModScannerMixin, ModCapabilitiesMixin):
    """
    Scans the Mods directory and exposes ModInfo objects.

    Registered as the "mods" service by plugins/mods/__init__.py.
    Inherits ModScannerMixin (filesystem scan) and ModCapabilitiesMixin (capabilities + framework dir).
    """

    def __init__(self, host: "PluginHost") -> None:
        self._host = host
        self._mods: list[ModInfo] = []
        self._mods_dir: Optional[Path] = None
        self._game_id: Optional[str] = None
