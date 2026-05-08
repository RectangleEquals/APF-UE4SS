from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .game import UEGameInfo
    from .platform import UEPlatformInfo
    from .ue4ss import UE4SSInfo
    from .framework import FrameworkBinariesInfo, FrameworkModInfo


@dataclass
class DetectionResult:
    """
    Aggregate detection result for a game installation.

    Build by chaining UEGameDetector → UEPlatformDetector →
    UE4SSInstallDetector → FrameworkDetector. Each sub-result is None
    when the corresponding layer was not found.
    """
    game: Optional["UEGameInfo"] = None
    platform: Optional["UEPlatformInfo"] = None
    ue4ss: Optional["UE4SSInfo"] = None
    framework_binaries: Optional["FrameworkBinariesInfo"] = None
    framework_mod: Optional["FrameworkModInfo"] = None

    @property
    def is_ue_game(self) -> bool:
        """True when the folder structure was recognised as a UE4/UE5 game."""
        return self.game is not None

    @property
    def valid(self) -> bool:
        """True when UE4SS is installed and fully functional."""
        return self.ue4ss is not None and self.ue4ss.valid
