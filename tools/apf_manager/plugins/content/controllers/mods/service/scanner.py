"""ModScannerMixin — filesystem scan and per-mod loading for ModService."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class ModScannerMixin:
    """Mixin for ModService: scan, rescan, get_mod, get_ap_mods, on_game_changed."""

    def on_game_changed(self, profile) -> None:
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

    def scan(self) -> list:
        """Return cached mod list. Call rescan() to refresh."""
        return list(self._mods)

    def rescan(self) -> list:
        """Re-read the Mods directory and return the updated list."""
        if self._mods_dir:
            self._mods = self._scan_with_state(self._mods_dir, self._game_id)
        return list(self._mods)

    def get_mod(self, folder_name: str):
        return next((m for m in self._mods if m.folder_name == folder_name), None)

    def get_ap_mods(self) -> list:
        return [m for m in self._mods if m.is_ap_mod]

    def get_mod_by_id(self, mod_id: str):
        return next((m for m in self._mods if m.mod_id == mod_id), None)

    @staticmethod
    def _scan_with_state(mods_dir: Path, game_id: Optional[str]) -> list:
        from . import ModInfo, _SCAN_EXCLUDE
        results = []
        if not mods_dir.is_dir():
            return results

        install_state = None
        if game_id:
            try:
                from ....models.state.install import InstallStateManager
                install_state = InstallStateManager(game_id)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "[mods] WARN: failed to load install state for %s: %s", game_id, exc
                )

        for entry in sorted(mods_dir.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name in _SCAN_EXCLUDE:
                continue
            info = ModScannerMixin._load_mod(entry)
            if info.is_ap_mod and install_state is not None:
                info.is_orphaned = not install_state.is_managed(info.folder_name)
            results.append(info)
        return results

    @staticmethod
    def _load_mod(folder: Path):
        from . import (
            ModInfo, ItemDef, LocationDef, GoalDef, OptionDef, ItemOverrideDef,
        )
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
                info.items = [ModScannerMixin._parse_item(i) for i in caps.get("items", [])]
                info.locations = [
                    ModScannerMixin._parse_location(l) for l in caps.get("locations", [])
                ]
                info.goals = [ModScannerMixin._parse_goal(g) for g in caps.get("goals", [])]
                info.options = [
                    ModScannerMixin._parse_option(o) for o in caps.get("options", [])
                ]
                info.item_overrides = [
                    ModScannerMixin._parse_item_override(x)
                    for x in raw.get("item_overrides", [])
                ]
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "[mods] WARN: failed to parse manifest at %s: %s", manifest_path, exc
                )

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
    def _parse_item(raw: dict):
        from . import ItemDef
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
    def _parse_location(raw: dict):
        from . import LocationDef
        return LocationDef(
            name=raw.get("name", ""),
            logic=raw.get("logic", ""),
            out_of_logic=raw.get("out_of_logic", False),
            tags=raw.get("tags", []),
            extra={k: v for k, v in raw.items()
                   if k not in ("name", "logic", "out_of_logic", "tags")},
        )

    @staticmethod
    def _parse_goal(raw: dict):
        from . import GoalDef
        return GoalDef(
            name=raw.get("name", ""),
            display_name=raw.get("display_name", ""),
            description=raw.get("description", ""),
            condition=raw.get("condition", ""),
            extra={k: v for k, v in raw.items()
                   if k not in ("name", "display_name", "description", "condition")},
        )

    @staticmethod
    def _parse_option(raw: dict):
        from . import OptionDef
        return OptionDef(
            name=raw.get("name", ""),
            type=raw.get("type", "toggle"),
            default=raw.get("default", 0),
            description=raw.get("description", ""),
            extra={k: v for k, v in raw.items()
                   if k not in ("name", "type", "default", "description")},
        )

    @staticmethod
    def _parse_item_override(raw: dict):
        from . import ItemOverrideDef
        return ItemOverrideDef(
            item_name=raw.get("item_name", ""),
            override_type=raw.get("type", ""),
            requires_option=raw.get("requires_option", ""),
            extra={k: v for k, v in raw.items()
                   if k not in ("item_name", "type", "requires_option")},
        )
