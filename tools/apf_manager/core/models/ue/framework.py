from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FrameworkBinariesInfo:
    """AP Framework DLL presence in the platform directory."""
    has_core_dll: bool = False
    has_client_dll: bool = False

    @property
    def installed(self) -> bool:
        return self.has_core_dll and self.has_client_dll


@dataclass
class FrameworkModInfo:
    """Detected core framework mod (archipelago.<game_id>.framework)."""
    mod_dir: Path
    mod_id: str
    manifest_path: Path
    framework_config_path: Optional[Path] = None
    has_scripts: bool = False
    output_dir: Optional[Path] = None
    session_state_path: Optional[Path] = None
