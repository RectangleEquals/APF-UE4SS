"""
SessionManager — backup and restore AP session state.

Session state file: <mods_dir>/APFrameworkMod/session_state.json
Backups stored at:  ~/.apf_manager/sessions/<game_id>/<timestamp>_<name>.json

Registered as the "sessions" service.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.config import GameProfile
    from ...core.ue4ss import UE4SSResult


_SESSIONS_ROOT = Path.home() / ".apf_manager" / "sessions"
_SESSION_STATE_FILENAME = "session_state.json"


@dataclass
class SessionBackup:
    game_id: str
    name: str
    timestamp: str          # ISO-like: "20260321_143022"
    path: Path
    display_ts: str = ""    # Human readable: "2026-03-21 14:30:22"

    @property
    def display_name(self) -> str:
        return f"{self.display_ts}  —  {self.name}" if self.display_ts else self.name


class SessionManager:
    def __init__(self) -> None:
        self._game_id: Optional[str] = None
        self._state_path: Optional[Path] = None

    # Called by plugin when game context changes
    def on_game_changed(
        self,
        profile: Optional["GameProfile"],
        detection: Optional["UE4SSResult"],
    ) -> None:
        if profile and detection and detection.mods_dir:
            self._game_id = profile.game_id
            self._state_path = (
                detection.mods_dir / "APFrameworkMod" / _SESSION_STATE_FILENAME
            )
        else:
            self._game_id = None
            self._state_path = None

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def list_sessions(self, game_id: Optional[str] = None) -> list[SessionBackup]:
        gid = game_id or self._game_id
        if not gid:
            return []
        folder = _SESSIONS_ROOT / gid
        if not folder.is_dir():
            return []

        backups = []
        for f in sorted(folder.iterdir(), reverse=True):
            if f.suffix != ".json":
                continue
            parsed = _parse_filename(f.stem)
            if parsed:
                ts, name = parsed
                display = _format_ts(ts)
                backups.append(SessionBackup(
                    game_id=gid,
                    name=name,
                    timestamp=ts,
                    path=f,
                    display_ts=display,
                ))
        return backups

    def backup(self, name: str, game_id: Optional[str] = None) -> Optional[SessionBackup]:
        gid = game_id or self._game_id
        if not gid or not self._state_path or not self._state_path.exists():
            return None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "backup"
        out_folder = _SESSIONS_ROOT / gid
        out_folder.mkdir(parents=True, exist_ok=True)

        dest = out_folder / f"{ts}_{safe_name}.json"
        shutil.copy2(self._state_path, dest)

        return SessionBackup(
            game_id=gid,
            name=safe_name,
            timestamp=ts,
            path=dest,
            display_ts=_format_ts(ts),
        )

    def restore(self, backup: SessionBackup) -> bool:
        if not self._state_path:
            return False
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup.path, self._state_path)
            return True
        except Exception:
            return False

    def delete(self, backup: SessionBackup) -> None:
        if backup.path.exists():
            backup.path.unlink()

    def rename(self, backup: SessionBackup, new_name: str) -> Optional[SessionBackup]:
        safe = re.sub(r'[\\/:*?"<>|]', "_", new_name).strip() or "backup"
        new_path = backup.path.parent / f"{backup.timestamp}_{safe}.json"
        try:
            backup.path.rename(new_path)
            return SessionBackup(
                game_id=backup.game_id,
                name=safe,
                timestamp=backup.timestamp,
                path=new_path,
                display_ts=backup.display_ts,
            )
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_filename(stem: str) -> Optional[tuple[str, str]]:
    """Parse '<timestamp>_<name>' stem. Returns (ts, name) or None."""
    m = re.match(r"^(\d{8}_\d{6})_(.+)$", stem)
    if m:
        return m.group(1), m.group(2)
    return None


def _format_ts(ts: str) -> str:
    try:
        dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts
