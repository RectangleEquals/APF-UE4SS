"""SessionsController — business logic bridge between SessionsPanel and SessionManager."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ....core.models.config import GameProfile
    from ..models.session import SessionBackup


class SessionsController:
    def __init__(self, host) -> None:
        self._host = host

    def _svc(self):
        return self._host.get_service("sessions")

    def activate(self, profile: "GameProfile") -> None:
        svc = self._svc()
        if svc:
            svc.on_game_changed(profile, self._host.get_detection())

    def get_deployed_info(self) -> Optional[dict]:
        svc = self._svc()
        return svc.get_deployed_info() if svc else None

    def get_deployed_path_str(self) -> str:
        svc = self._svc()
        if not svc:
            return "—"
        return str(svc.deployed_path) if svc.deployed_path else "—"

    def get_sessions(self, game_id: str) -> list["SessionBackup"]:
        svc = self._svc()
        return svc.list_sessions(game_id) if svc else []

    def backup(self, name: str, game_id: str) -> Optional["SessionBackup"]:
        svc = self._svc()
        return svc.backup(name, game_id) if svc else None

    def restore(self, backup: "SessionBackup") -> bool:
        svc = self._svc()
        return svc.restore(backup) if svc else False

    def delete(self, backup: "SessionBackup") -> None:
        svc = self._svc()
        if svc:
            svc.delete(backup)

    def rename(self, backup: "SessionBackup", new_name: str) -> Optional["SessionBackup"]:
        svc = self._svc()
        return svc.rename(backup, new_name) if svc else None

    def has_service(self) -> bool:
        return self._host.has_service("sessions")

    def get_dependency_state(self) -> dict:
        """Return {"ue4ss_ok": bool, "fw_installed": bool, "missing": list[str]}."""
        detection = self._host.get_detection()
        ue4ss_ok = bool(detection and detection.valid)
        fw_installed = bool(detection and detection.framework_mod)
        missing = []
        if not ue4ss_ok:
            missing.append("UE4SS")
        if not fw_installed:
            missing.append("AP Framework Mod")
        return {"ue4ss_ok": ue4ss_ok, "fw_installed": fw_installed, "missing": missing}
