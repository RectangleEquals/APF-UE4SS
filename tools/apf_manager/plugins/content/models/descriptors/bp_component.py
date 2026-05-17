"""
bp_component.py — Typed blueprint logic mod model.

BpLogicMod is the abstract base; PakLogicMod and UcasLogicMod are the two concrete forms:
  - PakLogicMod     : a single .pak file
  - UcasLogicMod    : a paired .ucas + .utoc file (both required for the mod to load)

parse_bp_mods() converts a flat list of filenames (from disk scan or registry resolver)
into typed instances by pairing .ucas/.utoc by stem.

INSTALL PATH INVARIANT: BP logic mods are ALWAYS deployed to and removed from
  <GameRoot>/<GameShortName>/Content/Paks/LogicMods/
They are NEVER placed anywhere inside ue4ss/Mods/.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)

_BP_EXTENSIONS = frozenset({".pak", ".ucas", ".utoc"})


class BpLogicMod(ABC):
    """Abstract base for a blueprint logic mod (one or two files in LogicMods/)."""

    @property
    @abstractmethod
    def files(self) -> list[str]:
        """All filenames belonging to this mod unit."""
        ...

    @property
    @abstractmethod
    def display_type(self) -> str:
        """Short human-readable type label: "PAK" or "UCAS/UTOC"."""
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


def parse_bp_mods(file_list: Sequence[str]) -> list[BpLogicMod]:
    """
    Convert a flat list of BP filenames into typed BpLogicMod instances.

    Pairing rules:
      - .ucas and .utoc with the same stem → UcasLogicMod
      - .pak → PakLogicMod
      - Unpaired .ucas or .utoc → PakLogicMod (with a warning; mod will likely not load)
      - Unrecognised extensions → ignored
    """
    ucas: dict[str, str] = {}  # stem -> filename
    utoc: dict[str, str] = {}  # stem -> filename
    paks: list[str] = []

    for fname in (file_list or []):
        ext = os.path.splitext(fname)[1].lower()
        stem = os.path.splitext(fname)[0]
        if ext == ".ucas":
            ucas[stem] = fname
        elif ext == ".utoc":
            utoc[stem] = fname
        elif ext == ".pak":
            paks.append(fname)
        # else: skip — not a recognised BP extension

    result: list[BpLogicMod] = []

    matched_stems: set[str] = set()
    for stem, ucas_fname in ucas.items():
        if stem in utoc:
            result.append(UcasLogicMod(ucas_file=ucas_fname, utoc_file=utoc[stem]))
            matched_stems.add(stem)
        else:
            logger.warning(
                "Unpaired .ucas file '%s' has no matching .utoc — treating as standalone PAK",
                ucas_fname,
            )
            result.append(PakLogicMod(pak_file=ucas_fname))

    for stem, utoc_fname in utoc.items():
        if stem not in matched_stems:
            logger.warning(
                "Unpaired .utoc file '%s' has no matching .ucas — treating as standalone PAK",
                utoc_fname,
            )
            result.append(PakLogicMod(pak_file=utoc_fname))

    for pak in paks:
        result.append(PakLogicMod(pak_file=pak))

    return result
