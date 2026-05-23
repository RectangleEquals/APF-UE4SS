from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple


class APConfigController:
    def __init__(self, host) -> None:
        self._host = host

    def _svc(self):
        return self._host.get_service("ap_config")

    def activate(self, profile) -> bool:
        svc = self._svc()
        if svc:
            return svc.load()
        return False

    def get_load_status(self) -> Tuple[bool, str, Optional[Path]]:
        svc = self._svc()
        if not svc:
            return (False, "", None)
        return (svc.load_ok, svc.load_error, svc.config_path)

    def get_config(self) -> dict:
        svc = self._svc()
        return svc.get_config() if svc else {}

    def get_config_deep(self) -> dict:
        svc = self._svc()
        return svc.get_raw_data() if svc else {}

    def save(self, data: dict) -> bool:
        svc = self._svc()
        if not svc:
            return False
        svc.update(data)
        return svc.save()

    def reload(self) -> bool:
        svc = self._svc()
        return svc.load() if svc else False

    def reload_status(self) -> Tuple[bool, str]:
        svc = self._svc()
        if not svc:
            return (False, "")
        ok = svc.load()
        return (ok, svc.load_error)

    @property
    def has_framework_mod(self) -> bool:
        svc = self._svc()
        return svc.has_framework_mod if svc else False

    @property
    def framework_mod_name(self) -> Optional[str]:
        svc = self._svc()
        return svc.framework_mod_name if svc else None

    @property
    def config_exists(self) -> bool:
        svc = self._svc()
        return svc.config_exists if svc else False

    def has_service(self) -> bool:
        return self._svc() is not None

    def get_dependency_state(self) -> dict:
        """Return {"ue4ss_ok": bool, "fw_installed": bool, "missing": list[str]}."""
        detection = self._host.get_detection()
        ue4ss_ok = bool(detection and detection.ue4ss)
        fw_installed = self.has_framework_mod
        missing = []
        if not ue4ss_ok:
            missing.append("UE4SS")
        if not fw_installed:
            missing.append("AP Framework Mod")
        return {"ue4ss_ok": ue4ss_ok, "fw_installed": fw_installed, "missing": missing}
