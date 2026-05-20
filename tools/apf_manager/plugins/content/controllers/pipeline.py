"""PipelineController — service queries for ContentPipelinePanel (no Kivy)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ....core.models.config import GameProfile


class PipelineController:
    """
    Non-Kivy controller for ContentPipelinePanel.

    Owns all service queries so the view never imports services directly.
    """

    def __init__(self, host) -> None:
        self._host = host

    def on_activate(self, game_profile) -> None:
        """Notify registry service of game change so it clears stale cache."""
        if self._host.has_service("registry"):
            self._host.get_service("registry").on_game_changed(game_profile)

    def get_framework_state(self) -> dict:
        """
        Query detection + mods service.

        Returns dict keys:
          ue4ss_ok           bool
          fw_conflict        list[Path]
          fw_dir             Optional[Path]
          fw_conflict_names  str   (comma-separated folder names)
          detection          DetectionResult | None
        """
        detection = self._host.get_detection()
        ue4ss_ok = bool(detection and detection.valid)
        fw_conflict: list = []
        fw_dir: Optional[Path] = None

        if ue4ss_ok and self._host.has_service("mods"):
            mods_svc = self._host.get_service("mods")
            fw_conflict = mods_svc.get_framework_mod_conflict()
            fw_dir = mods_svc.get_framework_mod_dir()

        fw_conflict_names = ", ".join(
            p.name if hasattr(p, "name") else str(p) for p in fw_conflict
        )
        return {
            "ue4ss_ok": ue4ss_ok,
            "fw_conflict": fw_conflict,
            "fw_dir": fw_dir,
            "fw_conflict_names": fw_conflict_names,
            "detection": detection,
        }

    def count_content_updates(self) -> int:
        """Return pending UE4SS + framework binary update count (secondary badge)."""
        if not self._host.has_service("updates"):
            return 0
        updates_svc = self._host.get_service("updates")
        count = 0
        ue4ss = updates_svc.get_update_info("ue4ss")
        if ue4ss and ue4ss.is_update_available:
            count += 1
        framework = updates_svc.get_update_info("framework")
        if framework and framework.is_update_available:
            count += 1
        return count

    def get_game_id(self, profile) -> str:
        """Derive game_id from registry service or fall back to profile."""
        if self._host.has_service("registry"):
            svc = self._host.get_service("registry")
            gid = svc._get_game_id() if hasattr(svc, "_get_game_id") else ""
            if gid:
                return gid
        if profile:
            name = profile.display_name
            return name.lower().replace(" ", "_") if name else ""
        return ""
