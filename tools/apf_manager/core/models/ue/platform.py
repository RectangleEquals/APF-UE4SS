from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class UEPlatformInfo:
    """The platform architecture directory (e.g. Win64/) under Binaries/."""
    platform_dir: Path
    arch: str   # "Win64", "WinGDK", "Win32", …
