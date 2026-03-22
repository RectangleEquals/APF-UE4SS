"""
APConfigService — read/write framework_config.json.

The config file lives at:
    <mods_dir>/APFrameworkMod/framework_config.json

Registered as the "ap_config" service.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.ue4ss import UE4SSResult


_DEFAULT_CONFIG = {
    "server": {
        "host": "localhost",
        "port": 38281,
        "slot_name": "",
        "password": "",
    },
    "logging": {
        "level": "info",
        "file": True,
        "console": True,
        "append": False,
    },
    "timeouts": {
        "connect_timeout_ms": 5000,
        "recv_timeout_ms": 10000,
        "retry_delay_ms": 2000,
        "max_retries": 5,
    },
    "threading": {
        "poll_interval_ms": 100,
    },
}


class APConfigService:
    def __init__(self) -> None:
        self._path: Optional[Path] = None
        self._data: dict = {}

    # Called by PluginHost when game context changes
    def on_game_changed(self, profile, detection: Optional["UE4SSResult"]) -> None:
        if detection and detection.mods_dir:
            self._path = detection.mods_dir / "APFrameworkMod" / "framework_config.json"
            self.load()
        else:
            self._path = None
            self._data = {}

    def load(self) -> bool:
        if not self._path or not self._path.exists():
            self._data = {}
            return False
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
            return True
        except Exception:
            self._data = {}
            return False

    def save(self) -> bool:
        if not self._path:
            return False
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, indent=2), encoding="utf-8"
            )
            return True
        except Exception:
            return False

    def get_config(self) -> dict:
        return dict(self._data)

    def update(self, new_data: dict) -> None:
        self._data = new_data

    def get_host(self) -> str:
        return self._data.get("server", {}).get("host", "localhost")

    def get_port(self) -> int:
        return int(self._data.get("server", {}).get("port", 38281))

    def get_slot_name(self) -> str:
        return self._data.get("server", {}).get("slot_name", "")

    @property
    def config_path(self) -> Optional[Path]:
        return self._path

    @property
    def has_config(self) -> bool:
        return bool(self._data)
