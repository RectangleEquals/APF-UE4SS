"""UEDetector — main entry point for the full UE detection chain."""
from __future__ import annotations

from pathlib import Path

from ...models.ue.result import DetectionResult
from .game import UEGameDetector
from .platform import UEPlatformDetector
from .ue4ss import UE4SSInstallDetector
from .framework import FrameworkDetector


class UEDetector:
    """
    Chains all UE detection layers and returns a single DetectionResult.

    Detection order:
      1. UEGameDetector        — is this a UE4/UE5 game root?
      2. UEPlatformDetector    — find Binaries/<arch>/
      3. UE4SSInstallDetector  — is UE4SS installed?
      4. FrameworkDetector     — AP Framework DLLs + core mod
    """

    @staticmethod
    def detect(game_root: str | Path) -> DetectionResult:
        root = Path(game_root)
        result = DetectionResult()

        game_info = UEGameDetector.detect(root)
        if not game_info:
            return result
        result.game = game_info

        platform_info = UEPlatformDetector.detect(game_info)
        if not platform_info:
            return result
        result.platform = platform_info

        ue4ss_info = UE4SSInstallDetector.detect(platform_info, game_info)
        result.ue4ss = ue4ss_info

        result.framework_binaries = FrameworkDetector.detect_binaries(platform_info)
        if ue4ss_info.valid:
            result.framework_mod = FrameworkDetector.detect_mod(ue4ss_info)

        return result
