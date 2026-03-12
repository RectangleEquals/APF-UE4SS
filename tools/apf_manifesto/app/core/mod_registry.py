"""
core/mod_registry.py

Scans the Mods/ directory, loads all manifest.json files, and provides a
unified view of all capabilities (regions, items, options) across mods.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .manifest_io import load_manifest
from .manifest_model import ManifestModel, OptionDef, RegionDef, ItemDef


_DEP_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


@dataclass
class RegistryEntry:
    mod_id: str
    folder_name: str
    model: ManifestModel


@dataclass
class RegistryItem:
    name: str
    owner_mod_id: str
    definition: ItemDef


@dataclass
class RegistryRegion:
    name: str
    owner_mod_id: str


@dataclass
class RegistryOption:
    key: str
    owner_mod_id: str
    definition: OptionDef


class ModRegistry:
    """
    Aggregated view of all mods in a Mods/ directory.
    Call scan() to populate; call scan() again to refresh.
    """

    def __init__(self, mods_dir: str):
        self.mods_dir = Path(mods_dir)
        self._mods: list[RegistryEntry] = []

    # ------------------------------------------------------------------

    def scan(self) -> None:
        """(Re-)scan the Mods/ directory and reload all manifests."""
        self._mods.clear()
        if not self.mods_dir.is_dir():
            return
        for entry in sorted(self.mods_dir.iterdir()):
            manifest_path = entry / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                model = load_manifest(str(manifest_path))
                if model.mod_id:
                    self._mods.append(
                        RegistryEntry(
                            mod_id=model.mod_id,
                            folder_name=entry.name,
                            model=model,
                        )
                    )
            except Exception:
                pass  # Silently skip malformed manifests during scan

    def mods(self) -> list[RegistryEntry]:
        return list(self._mods)

    def get_mod(self, mod_id: str) -> RegistryEntry | None:
        for e in self._mods:
            if e.mod_id == mod_id:
                return e
        return None

    # ------------------------------------------------------------------
    # Aggregated capability views

    def all_regions(self) -> list[RegistryRegion]:
        out = []
        for entry in self._mods:
            for r in entry.model.capabilities.regions:
                out.append(RegistryRegion(name=r.name, owner_mod_id=entry.mod_id))
        return out

    def all_items(self) -> list[RegistryItem]:
        out = []
        for entry in self._mods:
            for it in entry.model.capabilities.items:
                out.append(RegistryItem(
                    name=it.name,
                    owner_mod_id=entry.mod_id,
                    definition=it,
                ))
        return out

    def all_options(self) -> list[RegistryOption]:
        out = []
        for entry in self._mods:
            for key, opt in entry.model.options.items():
                out.append(RegistryOption(
                    key=key,
                    owner_mod_id=entry.mod_id,
                    definition=opt,
                ))
        return out

    def known_region_names(self) -> set[str]:
        return {r.name for r in self.all_regions()}

    def known_item_names(self) -> set[str]:
        return {i.name for i in self.all_items()}

    def known_option_keys(self) -> set[str]:
        return {o.key for o in self.all_options()}

    # ------------------------------------------------------------------
    # Dependency helpers

    def resolve_dep_mod_id(self, dep_string: str) -> str:
        m = _DEP_RE.match(dep_string.strip())
        return m.group(1) if m else dep_string.strip()

    def check_dependencies(self, model: ManifestModel) -> list[str]:
        """Return list of unresolved dependency mod_ids."""
        known = {e.mod_id for e in self._mods}
        missing = []
        for dep in model.depends:
            dep_id = self.resolve_dep_mod_id(dep)
            if dep_id not in known:
                missing.append(dep_id)
        return missing

    def check_conflicts(self, model: ManifestModel) -> list[str]:
        """Return list of active mod_ids that conflict with model."""
        known = {e.mod_id for e in self._mods}
        conflicts = []
        for inc in model.incompatible:
            inc_id = self.resolve_dep_mod_id(inc)
            if inc_id in known and inc_id != model.mod_id:
                conflicts.append(inc_id)
        return conflicts
