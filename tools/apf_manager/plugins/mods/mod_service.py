"""
ModService — scans a Mods directory and exposes ModInfo objects.

Registered as the "mods" service by the mods plugin.
Re-scans automatically when the active game changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.plugin_host import PluginHost
    from ...core.config import GameProfile


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
class ManualStep:
    type: str       # "text" | "file"
    when: str       # "button" | "before_install" | "after_install" | "before_deploy" | "after_package"
    caption: str = ""
    title: str = ""
    content: str = ""


@dataclass
class InstallStep:
    step_type: str
    params: dict = field(default_factory=dict)


@dataclass
class ValidationCheck:
    check_type: str
    params: dict = field(default_factory=dict)


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

    # install.json
    prefers_after: list = field(default_factory=list)
    requires_external: list = field(default_factory=list)
    manual_steps: list = field(default_factory=list)   # list[ManualStep]
    install_steps: list = field(default_factory=list)  # list[InstallStep]
    uninstall_steps: list = field(default_factory=list)
    validate_checks: list = field(default_factory=list)# list[ValidationCheck]

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

    # Called by PluginHost when game context changes
    def on_game_changed(self, profile: Optional["GameProfile"]) -> None:
        if profile is None:
            self._mods = []
            self._mods_dir = None
            return
        detection = self._host.get_detection()
        if detection and detection.mods_dir:
            self._mods_dir = detection.mods_dir
            self._mods = self._scan(detection.mods_dir)

    # -----------------------------------------------------------------------
    # Public API (the "mods" service interface)
    # -----------------------------------------------------------------------

    def scan(self) -> list[ModInfo]:
        """Return cached mod list. Call rescan() to refresh."""
        return list(self._mods)

    def rescan(self) -> list[ModInfo]:
        """Re-read the Mods directory and return the updated list."""
        if self._mods_dir:
            self._mods = self._scan(self._mods_dir)
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
        game: str = "APFramework",
        strict: bool = False,
    ) -> dict:
        """
        Build aggregated capabilities from AP mods.
        Uses templates_dirs auto-resolved from the game's root directory.
        """
        from .capabilities_builder import CapabilitiesBuilder
        if mods is None:
            mods = self.get_ap_mods()
        templates_dirs = self._resolve_templates_dirs()
        return CapabilitiesBuilder().from_mod_infos(mods, game=game, templates_dirs=templates_dirs, strict=strict)

    def _resolve_templates_dirs(self) -> list[Path]:
        """
        Locate Templates/<game>/ directories relative to the active game root.
        Searches common UE4 directory layouts.
        """
        dirs: list[Path] = []
        if not self._mods_dir:
            return dirs
        # Typical layout: game_root/Pal/Binaries/Win64/Mods/ → game_root/
        # Walk up looking for a Templates/ directory (up to 6 levels)
        candidate = self._mods_dir
        for _ in range(6):
            templates = candidate / "Templates"
            if templates.is_dir():
                dirs.append(templates)
                break
            parent = candidate.parent
            if parent == candidate:
                break
            candidate = parent
        return dirs

    # -----------------------------------------------------------------------
    # Internal scanning
    # -----------------------------------------------------------------------

    @staticmethod
    def _scan(mods_dir: Path) -> list[ModInfo]:
        results: list[ModInfo] = []
        if not mods_dir.is_dir():
            return results
        for entry in sorted(mods_dir.iterdir()):
            if not entry.is_dir():
                continue
            info = ModService._load_mod(entry)
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
            except Exception:
                pass

        # --- install.json ---
        install_path = folder / "install.json"
        if install_path.exists():
            try:
                raw = json.loads(install_path.read_text(encoding="utf-8"))
                info.prefers_after = raw.get("prefers_after", [])
                info.requires_external = raw.get("requires_external", [])
                info.manual_steps = [
                    ManualStep(
                        type=s.get("type", "text"),
                        when=s.get("when", "button"),
                        caption=s.get("caption", ""),
                        title=s.get("title", ""),
                        content=s.get("content", ""),
                    )
                    for s in raw.get("manual_steps", [])
                ]
                info.install_steps = [
                    InstallStep(step_type=s.get("type", ""), params={k: v for k, v in s.items() if k != "type"})
                    for s in raw.get("install", [])
                ]
                info.uninstall_steps = [
                    InstallStep(step_type=s.get("type", ""), params={k: v for k, v in s.items() if k != "type"})
                    for s in raw.get("uninstall", [])
                ]
                info.validate_checks = [
                    ValidationCheck(check_type=s.get("type", ""), params={k: v for k, v in s.items() if k != "type"})
                    for s in raw.get("validate", [])
                ]
            except Exception:
                pass

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
