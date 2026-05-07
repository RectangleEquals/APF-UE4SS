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
    from ...core.models.ue4ss import UE4SSResult


_DEFAULT_CONFIG = {
    "ap_server": {
        "host": "archipelago.gg",
        "port": 38281,
        "slot_name": "",
        "password": "",
        "auto_reconnect": True,
    },
    "logging": {
        "level": "info",
        "file": "ap_framework.log",
        "console": True,
        "append": False,
    },
    "timeouts": {
        "connection_ms": 30000,
        "priority_registration_ms": 30000,
        "registration_ms": 60000,
        "ipc_message_ms": 5000,
        "action_execution_ms": 5000,
        "retry": {
            "max_connection": 3,
            "max_ipc_message": 3,
            "initial_delay_ms": 1000,
            "backoff_multiplier": 2.0,
            "max_delay_ms": 10000,
        },
    },
    "threading": {
        "polling_interval_ms": 16,
        "queue_max_size": 1000,
        "shutdown_timeout_ms": 5000,
    },
}


class APConfigService:
    def __init__(self) -> None:
        self._path: Optional[Path] = None
        self._data: dict = {}
        self._load_ok: bool = False
        self._load_error: str = ""

    # Called by PluginHost when game context changes
    def on_game_changed(self, profile, detection: Optional["UE4SSResult"]) -> None:
        if detection and detection.mods_dir:
            self._path = detection.mods_dir / "APFrameworkMod" / "framework_config.json"
            self.load()
        else:
            self._path = None
            self._data = {}

    def load(self) -> bool:
        self._load_ok = False
        self._load_error = ""
        if not self._path:
            return False
        if not self._path.exists():
            # File absent — seed _data with defaults if empty so the form shows
            # something useful rather than empty hint-text fields.
            if not self._data:
                import copy
                self._data = copy.deepcopy(_DEFAULT_CONFIG)
            return False
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
            self._load_ok = True
            return True
        except Exception as exc:
            self._load_error = str(exc)
            if not self._data:
                import copy
                self._data = copy.deepcopy(_DEFAULT_CONFIG)
            return False

    @property
    def load_ok(self) -> bool:
        return self._load_ok

    @property
    def load_error(self) -> str:
        return self._load_error

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
        return self._data.get("ap_server", {}).get("host", "archipelago.gg")

    def get_port(self) -> int:
        return int(self._data.get("ap_server", {}).get("port", 38281))

    def get_slot_name(self) -> str:
        return self._data.get("ap_server", {}).get("slot_name", "")

    @property
    def config_path(self) -> Optional[Path]:
        return self._path

    @property
    def has_config(self) -> bool:
        return bool(self._data)
