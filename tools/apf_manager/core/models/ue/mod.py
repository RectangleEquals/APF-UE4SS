from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ModDetectionInfo:
    """A mod folder detected under ue4ss/Mods/ that contains Scripts/main.lua or dlls/main.dll."""
    folder_name: str
    mod_dir: Path
    mod_id: Optional[str] = None
    is_ap_mod: bool = False        # mod_id present (any AP mod)
    is_priority_ap: bool = False   # mod_id matches archipelago.<game_id>.<name>
    is_framework: bool = False     # mod_id matches archipelago.<game_id>.framework (subset of priority)
    has_lua: bool = False
    has_cpp: bool = False
