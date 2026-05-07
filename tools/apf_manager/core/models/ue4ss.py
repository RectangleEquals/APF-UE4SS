"""
UE4SSResult — detected state of a UE4SS installation.

All path fields are Optional[Path] = None. field(default_factory=Path) created
Path() == CWD which is truthy and .is_dir() always True — making it
indistinguishable from a real detection result. None is the correct sentinel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class UE4SSResult:
    valid: bool = False
    game_root: Optional[Path] = None
    binaries_dir: Optional[Path] = None    # Actual Binaries/ folder
    platform_dir: Optional[Path] = None   # Arch dir (e.g. Win64/) — parent of ue4ss/
    ue4ss_dir: Optional[Path] = None
    mods_dir: Optional[Path] = None
    mods_txt: Optional[Path] = None
    content_paks_dir: Optional[Path] = None
    logicmods_dir: Optional[Path] = None
    missing: list = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.valid
