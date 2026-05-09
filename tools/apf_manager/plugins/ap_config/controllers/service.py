"""
APConfigService — read/write framework_config.json.

The config file lives at the path reported by the detected framework mod
(DetectionResult.framework_mod.framework_config_path). If that mod is not
installed, the service has no active path and the panel shows a placeholder.

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
        self._framework_mod_dir: Optional[Path] = None
        self._data: dict = {}
        self._load_ok: bool = False
        self._load_error: str = ""

    def on_game_changed(self, profile, detection: Optional["DetectionResult"]) -> None:
        self._path = None
        self._framework_mod_dir = None
        self._data = {}
        self._load_ok = False
        self._load_error = ""

        if not (detection and detection.framework_mod):
            return

        mod = detection.framework_mod
        self._framework_mod_dir = mod.mod_dir
        # Use the detected path if available; otherwise derive where we would save it
        self._path = mod.framework_config_path or (mod.mod_dir / "framework_config.json")

        if self._path.exists():
            self.load()
        else:
            # Config doesn't exist yet — start from defaults so the panel has something to show
            self._data = copy.deepcopy(DEFAULT_CONFIG)

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

    @property
    def has_framework_mod(self) -> bool:
        return self._framework_mod_dir is not None

    @property
    def framework_mod_name(self) -> Optional[str]:
        return self._framework_mod_dir.name if self._framework_mod_dir else None

    @property
    def config_exists(self) -> bool:
        return self._path is not None and self._path.exists()

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
