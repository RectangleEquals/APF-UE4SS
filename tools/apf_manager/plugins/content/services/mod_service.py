"""
ModService — scans a Mods directory and exposes ModInfo objects.

Registered as the "mods" service by the mods plugin.
Re-scans automatically when the active game changes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ....core.plugin_host import PluginHost
    from ....core.config import GameProfile


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Framework mod id must match exactly: archipelago.<game_id>.framework
_FRAMEWORK_MOD_RE = re.compile(r"^archipelago\.[a-z0-9_]+\.framework$")

# Folder names inside mods_dir that are never AP mods — excluded from all scans.
# "shared" is the UE4SS built-in Lua library: no manifest.json, no main.lua.
_SCAN_EXCLUDE: frozenset[str] = frozenset({"shared"})


# ---------------------------------------------------------------------------
# ModInfo dataclass — full current manifest schema
# ---------------------------------------------------------------------------

@dataclass
class ItemDef:
    name: str
    type: str = "filler"       # "progression" | "useful" | "filler" | "trap"
    amount: object = 1         # int or "fill" or "{key}" expression
    amount_min: Optional[int] = None
    placement: list = field(default_factory=list)
    enabled_if: str = ""
    # Additional fields stored verbatim
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
    depends: list = field(default_factory=list)        # list of "mod_id (>=version)" strings
    incompatible: list = field(default_factory=list)   # list of "mod_id" strings

    # manifest.json — capabilities
    capabilities_includes: list = field(default_factory=list)  # capabilities.include paths
    vocab_validation: bool = False
    items: list = field(default_factory=list)          # list[ItemDef]
    locations: list = field(default_factory=list)      # list[LocationDef]
    goals: list = field(default_factory=list)          # list[GoalDef]
    options: list = field(default_factory=list)        # list[OptionDef]
    item_overrides: list = field(default_factory=list) # list[ItemOverrideDef]

    # Component detection (determined from filesystem structure)
    components: list = field(default_factory=lambda: ["lua"])
    bp_pak_files: list = field(default_factory=list)
    is_orphaned: bool = False

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

class ModService:
    def __init__(self, host: "PluginHost") -> None:
        self._host = host
        self._mods: list[ModInfo] = []
        self._mods_dir: Optional[Path] = None
        self._game_id: Optional[str] = None

    # Called by PluginHost when game context changes
    def on_game_changed(self, profile: Optional["GameProfile"]) -> None:
        if profile is None:
            self._mods = []
            self._mods_dir = None
            self._game_id = None
            return
        self._game_id = getattr(profile, "game_id", None)
        detection = self._host.get_detection()
        if detection and detection.mods_dir:
            self._mods_dir = detection.mods_dir
            self._mods = self._scan_with_state(detection.mods_dir, self._game_id)

    # -----------------------------------------------------------------------
    # Public API (the "mods" service interface)
    # -----------------------------------------------------------------------

    def scan(self) -> list[ModInfo]:
        """Return cached mod list. Call rescan() to refresh."""
        return list(self._mods)

    def rescan(self) -> list[ModInfo]:
        """Re-read the Mods directory and return the updated list."""
        if self._mods_dir:
            self._mods = self._scan_with_state(self._mods_dir, self._game_id)
        return list(self._mods)

    def get_mod(self, folder_name: str) -> Optional[ModInfo]:
        return next((m for m in self._mods if m.folder_name == folder_name), None)

    def get_ap_mods(self) -> list[ModInfo]:
        return [m for m in self._mods if m.is_ap_mod]

    def get_mod_by_id(self, mod_id: str) -> Optional[ModInfo]:
        return next((m for m in self._mods if m.mod_id == mod_id), None)

    def build_capabilities(
        self,
        mods: Optional[list[ModInfo]] = None,
        game: str = "",
        strict: bool = False,
    ) -> dict:
        """
        Build aggregated capabilities from AP mods.
        `game` should be the actual game name (e.g. "Palworld") used as the
        Templates/<game>/ subdirectory name. Falls back to profile game_id.
        """
        from ..utils.capabilities_builder import CapabilitiesBuilder
        if mods is None:
            mods = self.get_ap_mods()
        game_name = game or (self._game_id or "")
        templates_dirs = self._resolve_templates_dirs(game_name)
        return CapabilitiesBuilder().from_mod_infos(
            mods, game=game_name, templates_dirs=templates_dirs, strict=strict
        )

    # -----------------------------------------------------------------------
    # Framework mod — content-based detection (mirrors ap_path_util.cpp)
    # -----------------------------------------------------------------------

    def _find_framework_mod_dirs(self) -> list[Path]:
        """
        Scan mods_dir for all folders containing framework_config.json +
        manifest.json whose mod_id matches 'archipelago.<game_id>.framework'.

        Returns:
          []       — framework mod not installed
          [path]   — exactly one found (normal state)
          [p1, p2] — conflict: multiple framework mods present
        """
        results: list[Path] = []
        if not self._mods_dir or not self._mods_dir.is_dir():
            return results
        for entry in sorted(self._mods_dir.iterdir()):
            if not entry.is_dir():
                continue
            if not (entry / "framework_config.json").exists():
                continue
            manifest_path = entry / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                if _FRAMEWORK_MOD_RE.match(raw.get("mod_id", "")):
                    results.append(entry)
            except Exception as exc:
                self._host.log(f"[mods] WARN: failed to read manifest at {manifest_path}: {exc}")
        return results

    def get_framework_mod_dir(self) -> Optional[Path]:
        """Return the unique framework mod directory, or None if absent or conflicted."""
        found = self._find_framework_mod_dirs()
        return found[0] if len(found) == 1 else None

    def get_framework_mod_conflict(self) -> list[Path]:
        """Return multiple paths when more than one framework mod is deployed (conflict state)."""
        found = self._find_framework_mod_dirs()
        return found if len(found) > 1 else []

    def _resolve_templates_dirs(self, game_name: str = "") -> list[Path]:
        """
        Return [<framework_mod>/Templates/<game_name>/] if the framework mod is
        deployed and the game-level template dir exists.

        The returned path is the game-level dir — callers use it as:
          - vocab: td / "Items.json"
          - includes: td / "logic" / inc_path
        """
        if not game_name:
            return []
        fw_dir = self.get_framework_mod_dir()
        if not fw_dir:
            return []
        game_dir = fw_dir / "Templates" / game_name
        return [game_dir] if game_dir.is_dir() else []

    # -----------------------------------------------------------------------
    # Internal scanning
    # -----------------------------------------------------------------------

    @staticmethod
    def _scan_with_state(mods_dir: Path, game_id: Optional[str]) -> list[ModInfo]:
        results: list[ModInfo] = []
        if not mods_dir.is_dir():
            return results

        install_state = None
        if game_id:
            try:
                from ..shared.data.install_state import InstallStateManager
                install_state = InstallStateManager(game_id)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("[mods] WARN: failed to load install state for %s: %s", game_id, exc)

        for entry in sorted(mods_dir.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name in _SCAN_EXCLUDE:
                continue
            info = ModService._load_mod(entry)
            if info.is_ap_mod and install_state is not None:
                info.is_orphaned = not install_state.is_managed(info.folder_name)
            results.append(info)
        return results

    @staticmethod
    def _load_mod(folder: Path) -> ModInfo:
        info = ModInfo(folder_name=folder.name, folder_path=folder)

        # --- manifest.json ---
        manifest_path = folder / "manifest.json"
        if manifest_path.exists():
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                info.mod_id = raw.get("mod_id", "")
                info.name = raw.get("name", "")
                info.version = raw.get("version", "")
                info.description = raw.get("description", "")
                info.author = raw.get("author", "")
                info.depends = raw.get("depends", [])
                info.incompatible = raw.get("incompatible", [])

                caps = raw.get("capabilities", {})
                info.capabilities_includes = caps.get("include", [])
                info.vocab_validation = bool(caps.get("vocab_validation", False))
                info.items = [ModService._parse_item(i) for i in caps.get("items", [])]
                info.locations = [ModService._parse_location(l) for l in caps.get("locations", [])]
                info.goals = [ModService._parse_goal(g) for g in caps.get("goals", [])]
                info.options = [ModService._parse_option(o) for o in caps.get("options", [])]
                info.item_overrides = [
                    ModService._parse_item_override(x) for x in raw.get("item_overrides", [])
                ]
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("[mods] WARN: failed to parse manifest at %s: %s", manifest_path, exc)

        # --- Component detection (from filesystem structure) ---
        detected = []
        if (folder / "scripts" / "main.lua").exists():
            detected.append("lua")
        if (folder / "dlls" / "main.dll").exists():
            detected.append("cpp")
        logicmods_subdir = folder / "LogicMods"
        if logicmods_subdir.is_dir():
            pak_files = [
                f.name for f in logicmods_subdir.iterdir()
                if f.suffix.lower() in (".pak", ".ucas", ".utoc")
            ]
            if pak_files:
                detected.append("blueprint")
                info.bp_pak_files = pak_files
        info.components = detected or ["lua"]

        return info

    # -----------------------------------------------------------------------
    # Sub-parsers
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_item(raw: dict) -> ItemDef:
        return ItemDef(
            name=raw.get("name", ""),
            type=raw.get("type", "filler"),
            amount=raw.get("amount", 1),
            amount_min=raw.get("amount_min"),
            placement=raw.get("placement", []),
            enabled_if=raw.get("enabled_if", ""),
            extra={k: v for k, v in raw.items()
                   if k not in ("name", "type", "amount", "amount_min", "placement", "enabled_if")},
        )

    @staticmethod
    def _parse_location(raw: dict) -> LocationDef:
        return LocationDef(
            name=raw.get("name", ""),
            logic=raw.get("logic", ""),
            out_of_logic=raw.get("out_of_logic", False),
            tags=raw.get("tags", []),
            extra={k: v for k, v in raw.items()
                   if k not in ("name", "logic", "out_of_logic", "tags")},
        )

    @staticmethod
    def _parse_goal(raw: dict) -> GoalDef:
        return GoalDef(
            name=raw.get("name", ""),
            display_name=raw.get("display_name", ""),
            description=raw.get("description", ""),
            condition=raw.get("condition", ""),
            extra={k: v for k, v in raw.items()
                   if k not in ("name", "display_name", "description", "condition")},
        )

    @staticmethod
    def _parse_option(raw: dict) -> OptionDef:
        return OptionDef(
            name=raw.get("name", ""),
            type=raw.get("type", "toggle"),
            default=raw.get("default", 0),
            description=raw.get("description", ""),
            extra={k: v for k, v in raw.items()
                   if k not in ("name", "type", "default", "description")},
        )

    @staticmethod
    def _parse_item_override(raw: dict) -> ItemOverrideDef:
        return ItemOverrideDef(
            item_name=raw.get("item_name", ""),
            override_type=raw.get("type", ""),
            requires_option=raw.get("requires_option", ""),
            extra={k: v for k, v in raw.items()
                   if k not in ("item_name", "type", "requires_option")},
        )
