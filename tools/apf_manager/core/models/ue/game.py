from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class UEGameInfo:
    """Detected Unreal Engine game structure at a given game root."""
    game_root: Path
    game_shortname: str
    shortname_dir: Path
    engine_dir: Optional[Path]
    stub_exe: Optional[Path]
    content_dir: Path
    content_paks_dir: Path
    binaries_dir: Path
