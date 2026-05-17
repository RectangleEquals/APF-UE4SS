from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class UE4SSInfo:
    """Detected state of a UE4SS installation under a platform directory."""
    ue4ss_dir: Optional[Path] = None
    has_dwmapi: bool = False
    mods_dir: Optional[Path] = None
    mods_txt: Optional[Path] = None
    logicmods_dir: Optional[Path] = None
    missing: list = field(default_factory=list)
    version: Optional[str] = None

    @property
    def valid(self) -> bool:
        """True when ue4ss.dll was found and no required components are missing."""
        return self.ue4ss_dir is not None and len(self.missing) == 0
