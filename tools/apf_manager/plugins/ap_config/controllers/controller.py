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

    def has_service(self) -> bool:
        return self._svc() is not None
