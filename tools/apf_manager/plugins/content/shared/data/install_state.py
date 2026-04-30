"""
InstallStateManager — tracks what APF Manager has deployed to each game's install target.

Used to distinguish "managed" content from "orphaned/manually installed" content.

Storage: ~/.apf_manager/install_state/<game_id>.json

Schema per game:
{
  "installed": [
    {
      "mod_id": "archipelago.palworld.my_mod",
      "folder_name": "MyMod",
      "source_repo": "owner/repo",
      "source_folder": "MyMod",
      "version": "1.0.0",
      "components": ["lua", "blueprint"],
      "deployed_at": "2026-04-12T10:00:00",
      "bp_pak_files_deployed": ["MyMod_P.pak", "MyMod_P.ucas", "MyMod_P.utoc"]
    }
  ]
}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .pipeline_state import InstallRecord


def _state_path(game_id: str) -> Path:
    return Path.home() / ".apf_manager" / "install_state" / f"{game_id}.json"


class InstallStateManager:
    def __init__(self, game_id: str) -> None:
        self._game_id = game_id
        self._path = _state_path(game_id)
        self._data: list[dict] = []
        self._load()

    # -----------------------------------------------------------------------
    # Load / save
    # -----------------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            self._data = []
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._data = raw.get("installed", [])
        except Exception as exc:
            _log.warning("[install_state] WARN: failed to load %s: %s", self._path, exc)
            self._data = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"installed": self._data}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # -----------------------------------------------------------------------
    # Query
    # -----------------------------------------------------------------------

    def get_all(self) -> list[dict]:
        return list(self._data)

    def find(self, folder_name: str) -> Optional[dict]:
        return next((e for e in self._data if e.get("folder_name") == folder_name), None)

    def find_by_pak(self, pak_filename: str) -> Optional[dict]:
        for entry in self._data:
            if pak_filename in entry.get("bp_pak_files_deployed", []):
                return entry
        return None

    def is_managed(self, folder_name: str) -> bool:
        return self.find(folder_name) is not None

    def is_pak_managed(self, pak_filename: str) -> bool:
        return self.find_by_pak(pak_filename) is not None

    # -----------------------------------------------------------------------
    # Mutate
    # -----------------------------------------------------------------------

    def add(self, entry: dict) -> None:
        if "deployed_at" not in entry:
            entry = dict(entry)
            entry["deployed_at"] = datetime.now(timezone.utc).isoformat()
        self._data = [e for e in self._data if e.get("folder_name") != entry.get("folder_name")]
        self._data.append(entry)
        self._save()

    def add_record(self, record: "InstallRecord") -> None:
        from .pipeline_state import InstallRecord
        self._data = [e for e in self._data if e.get("folder_name") != record.folder_name]
        self._data.append(record.to_dict())
        self._save()

    def find_record(self, folder_name: str) -> Optional["InstallRecord"]:
        from .pipeline_state import InstallRecord
        entry = self.find(folder_name)
        return InstallRecord.from_dict(entry) if entry else None

    def remove(self, folder_name: str) -> None:
        before = len(self._data)
        self._data = [e for e in self._data if e.get("folder_name") != folder_name]
        if len(self._data) != before:
            self._save()
