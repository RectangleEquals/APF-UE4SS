"""
APF Manager — mod discovery.

Scans the source Mods/ directory (dev mode) or the deployed Mods/ directory (player mode)
for AP framework mods by reading their manifest.json and install.json files.

Dependency and ordering information comes from two sources:
  - manifest.json: 'depends' and 'incompatible' arrays (same schema the C++ framework uses)
  - install.json:  'prefers_after', 'requires_external', 'manual_steps' (deployment-only concerns)

AP mod detection: any mod whose manifest.json has a 'mod_id' field is treated as an AP mod.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import APFConfig

# Regex to extract the mod_id prefix from dependency strings like:
#   "archipelago.palworld.framework (>=1.0.0)"
#   "some.mod"
_DEP_MOD_ID_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


def _parse_dep_mod_id(dep_string: str) -> str:
    """Extract the mod_id from a dependency string (everything before the version constraint)."""
    m = _DEP_MOD_ID_RE.match(dep_string.strip())
    return m.group(1) if m else dep_string.strip()


@dataclass
class ModInfo:
    """All metadata for one discovered AP mod."""

    folder_name: str
    """Directory name under Mods/ — used as identifier in mods.txt and install steps."""

    display_name: str
    description: str
    is_core: bool = False
    """True for APFrameworkMod — cannot be unselected or moved."""
    is_stub: bool = False
    """True for placeholder/in-development mods."""

    # From manifest.json
    mod_id: str = ""
    version: str = "unknown"
    depends: list[str] = field(default_factory=list)
    """Hard deps: list of dep strings e.g. 'archipelago.palworld.framework (>=1.0.0)'."""
    incompatible: list[str] = field(default_factory=list)
    """Incompatibility strings (same format as depends)."""

    # From install.json
    has_install_json: bool = False
    install_descriptor: dict = field(default_factory=dict)
    prefers_after: list[str] = field(default_factory=list)
    """Soft load-order preference (folder names, not mod_ids)."""
    requires_external: list[str] = field(default_factory=list)
    """Non-AP mod dependencies to check for in mods.txt (e.g. 'PalSchema')."""
    manual_steps: list[dict] = field(default_factory=list)
    """Manual instruction descriptors for the GUI (type/when/caption/title/content)."""


class ModDiscovery:
    """
    Discovers AP mods by scanning a Mods/ directory.

    In dev mode: scans config.source_project/Mods/
    In player mode: scans detection.mods_dir (deployed Mods/) — caller provides this path.
    """

    def __init__(self, config: APFConfig):
        self.config = config
        self._mods: list[ModInfo] | None = None
        self._by_folder: dict[str, ModInfo] = {}
        self._by_mod_id: dict[str, ModInfo] = {}

    def discover(self, *, source_mods_dir: Path | None = None) -> list[ModInfo]:
        """
        Scan for AP mods. Pass source_mods_dir to override the default location.
        Results are cached until invalidate() is called.
        """
        if self._mods is not None:
            return self._mods

        mods_dir = source_mods_dir or self._default_mods_dir()
        if not mods_dir or not mods_dir.is_dir():
            self._mods = []
            return self._mods

        results: list[ModInfo] = []
        for entry in sorted(mods_dir.iterdir()):
            if not entry.is_dir():
                continue
            info = self._load_mod(entry)
            if info is not None:
                results.append(info)

        self._mods = results
        self._by_folder = {m.folder_name: m for m in results}
        self._by_mod_id = {m.mod_id: m for m in results if m.mod_id}
        return results

    def invalidate(self) -> None:
        """Force a re-scan on next call to discover()."""
        self._mods = None
        self._by_folder.clear()
        self._by_mod_id.clear()

    def get_by_folder(self, folder_name: str) -> ModInfo | None:
        self.discover()
        return self._by_folder.get(folder_name)

    def get_by_mod_id(self, mod_id: str) -> ModInfo | None:
        self.discover()
        return self._by_mod_id.get(mod_id)

    def known_ap_mod_names(self) -> set[str]:
        """Set of folder names for all known AP mods (for mods.txt cross-referencing)."""
        return {m.folder_name for m in self.discover()}

    def resolve_dep_to_folder(self, dep_string: str) -> str | None:
        """
        Given a dependency string like 'archipelago.palworld.framework (>=1.0.0)',
        return the folder_name of the matching AP mod, or None if not found.
        """
        mod_id = _parse_dep_mod_id(dep_string)
        info = self.get_by_mod_id(mod_id)
        return info.folder_name if info else None

    # -------------------------------------------------------------------------

    def _default_mods_dir(self) -> Path | None:
        src = self.config.source_project
        if src:
            p = Path(src) / "Mods"
            if p.is_dir():
                return p
        return None

    def _load_mod(self, entry: Path) -> ModInfo | None:
        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            return None

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return None

        # Any mod with a 'mod_id' field is an AP framework mod.
        mod_id = manifest.get("mod_id", "")
        if not mod_id:
            return None

        install_path = entry / "install.json"
        has_install = install_path.exists()
        descriptor: dict = {}
        if has_install:
            try:
                descriptor = json.loads(install_path.read_text(encoding="utf-8"))
            except Exception:
                has_install = False

        # Display name: install.json > manifest name > folder name
        display_name = (descriptor.get("display_name")
                        or manifest.get("name")
                        or entry.name)

        return ModInfo(
            folder_name=entry.name,
            display_name=display_name,
            description=descriptor.get("description") or manifest.get("description", ""),
            is_core=descriptor.get("is_core", False),
            is_stub=descriptor.get("is_stub", False),
            mod_id=mod_id,
            version=manifest.get("version", "unknown"),
            depends=manifest.get("depends", []),
            incompatible=manifest.get("incompatible", []),
            has_install_json=has_install,
            install_descriptor=descriptor,
            prefers_after=descriptor.get("prefers_after", []),
            requires_external=descriptor.get("requires_external", []),
            manual_steps=descriptor.get("manual_steps", []),
        )
