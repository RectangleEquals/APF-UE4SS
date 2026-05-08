"""
APConfigService — read/write framework_config.json.

The config file lives at:
    <mods_dir>/APFrameworkMod/framework_config.json

Registered as the "ap_config" service.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..models.config import DEFAULT_CONFIG

if TYPE_CHECKING:
    from ....core.models.ue.result import DetectionResult


class APConfigService:
    def __init__(self) -> None:
        self._path: Optional[Path] = None
        self._data: dict = {}
        self._load_ok: bool = False
        self._load_error: str = ""

    def on_game_changed(self, profile, detection: Optional["DetectionResult"]) -> None:
        if detection and detection.ue4ss and detection.ue4ss.mods_dir:
            self._path = detection.ue4ss.mods_dir / "APFrameworkMod" / "framework_config.json"
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
            if not self._data:
                self._data = copy.deepcopy(DEFAULT_CONFIG)
            return False
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
            self._load_ok = True
            return True
        except Exception as exc:
            self._load_error = str(exc)
            if not self._data:
                self._data = copy.deepcopy(DEFAULT_CONFIG)
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

    def get_raw_data(self) -> dict:
        return copy.deepcopy(self._data)

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
