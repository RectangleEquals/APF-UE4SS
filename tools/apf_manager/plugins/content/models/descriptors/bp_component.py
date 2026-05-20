"""
bp_component.py — Typed blueprint logic mod model.

BpLogicMod is the abstract base; three concrete forms cover all file combinations:
  - PakLogicMod          : a single .pak file
  - UcasLogicMod         : a paired .ucas + .utoc file
  - PakUcasUtocLogicMod  : a .pak + .ucas + .utoc triple (all same stem)

Association metadata on each instance:
  - is_standalone  : True when the mod lives in root LogicMods/ with no non-BP parent
  - parent_folder  : folder_name of the parent non-BP mod (empty when is_standalone)

parse_bp_mods() operates on the file list for a SINGLE subfolder.  All files must share
one filename stem; mixed stems or unrecognised combinations return None (invalid subfolder).

INSTALL PATH INVARIANT: BP logic mods are ALWAYS deployed to and removed from
  <GameRoot>/<GameShortName>/Content/Paks/LogicMods/<subfolder_name>/
The subfolder name is preserved from the registry/repo structure.
BP mods are NEVER placed anywhere inside ue4ss/Mods/.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)

_BP_EXTENSIONS = frozenset({".pak", ".ucas", ".utoc"})


@dataclass(kw_only=True)
class BpLogicMod(ABC):
    """Abstract base for a blueprint logic mod (one or more files in a LogicMods/ subfolder)."""

    is_standalone: bool = False
    parent_folder: str = ""

    @property
    @abstractmethod
    def files(self) -> list[str]:
        """All filenames belonging to this mod unit."""
        ...

    @property
    @abstractmethod
    def display_type(self) -> str:
        """Short human-readable type label: 'PAK', 'UCAS/UTOC', or 'PAK+UCAS/UTOC'."""
        ...

    @property
    def primary_name(self) -> str:
        """Stem of the first file, used for display."""
        return os.path.splitext(self.files[0])[0] if self.files else ""


@dataclass
class PakLogicMod(BpLogicMod):
    """A standalone .pak blueprint mod file."""
    pak_file: str

    @property
    def files(self) -> list[str]:
        return [self.pak_file]

    @property
    def display_type(self) -> str:
        return "PAK"


@dataclass
class UcasLogicMod(BpLogicMod):
    """A paired .ucas + .utoc blueprint mod (both must be present for the mod to load)."""
    ucas_file: str
    utoc_file: str

    @property
    def files(self) -> list[str]:
        return [self.ucas_file, self.utoc_file]

    @property
    def display_type(self) -> str:
        return "UCAS/UTOC"


@dataclass
class PakUcasUtocLogicMod(BpLogicMod):
    """Three-file BP mod: .pak + .ucas + .utoc (all with the same stem)."""
    pak_file: str
    ucas_file: str
    utoc_file: str

    @property
    def files(self) -> list[str]:
        return [self.pak_file, self.ucas_file, self.utoc_file]

    @property
    def display_type(self) -> str:
        return "PAK+UCAS/UTOC"


def parse_bp_mods(
    file_list: Sequence[str],
    *,
    is_standalone: bool = False,
    parent_folder: str = "",
) -> list[BpLogicMod] | None:
    """
    Parse the BP files for a single subfolder into a typed BpLogicMod instance.

    All files must share the same filename stem.  Mixed stems, duplicate extensions,
    or unrecognised file combinations return None so the caller can flag the subfolder
    as invalid.  An empty or non-BP file list returns an empty list (not None).

    Recognised single-stem combinations:
      .pak only             → PakLogicMod
      .ucas + .utoc         → UcasLogicMod
      .pak + .ucas + .utoc  → PakUcasUtocLogicMod
    """
    bp_files = [
        f for f in (file_list or [])
        if os.path.splitext(f)[1].lower() in _BP_EXTENSIONS
    ]
    if not bp_files:
        return []

    stems = {os.path.splitext(f)[0] for f in bp_files}
    if len(stems) > 1:
        logger.warning(
            "BP subfolder contains files with mixed stems %s — invalid, skipping",
            sorted(stems),
        )
        return None

    exts: dict[str, str] = {}
    for f in bp_files:
        ext = os.path.splitext(f)[1].lower()
        if ext in exts:
            logger.warning(
                "BP subfolder has duplicate %r extension (%s and %s) — invalid, skipping",
                ext, exts[ext], f,
            )
            return None
        exts[ext] = f

    has_pak  = ".pak"  in exts
    has_ucas = ".ucas" in exts
    has_utoc = ".utoc" in exts

    if has_pak and has_ucas and has_utoc:
        return [PakUcasUtocLogicMod(
            pak_file=exts[".pak"],
            ucas_file=exts[".ucas"],
            utoc_file=exts[".utoc"],
            is_standalone=is_standalone,
            parent_folder=parent_folder,
        )]
    if has_ucas and has_utoc and not has_pak:
        return [UcasLogicMod(
            ucas_file=exts[".ucas"],
            utoc_file=exts[".utoc"],
            is_standalone=is_standalone,
            parent_folder=parent_folder,
        )]
    if has_pak and not has_ucas and not has_utoc:
        return [PakLogicMod(
            pak_file=exts[".pak"],
            is_standalone=is_standalone,
            parent_folder=parent_folder,
        )]

    logger.warning(
        "BP subfolder has unrecognised file extension combination %s — invalid, skipping",
        sorted(exts.keys()),
    )
    return None
