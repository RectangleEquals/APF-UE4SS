"""
SessionManager — backup and restore AP session state.

Session state file: <mods_dir>/APFrameworkMod/output/session_state.json
Backups stored at:  ~/.apf_manager/sessions/<game_id>/<timestamp>_<name>.json

Registered as the "sessions" service.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..models.session import SessionBackup

if TYPE_CHECKING:
    from ....core.models.config import GameProfile
    from ....core.models.ue.result import DetectionResult


_SESSIONS_ROOT = Path.home() / ".apf_manager" / "sessions"
_SESSION_STATE_FILENAME = "session_state.json"
_FALLBACK_MOD_NAME = "APFrameworkMod"


class SessionManager:
    def __init__(self) -> None:
        self._game_id: Optional[str] = None
        self._state_path: Optional[Path] = None

    def on_game_changed(
        self,
        profile: Optional["GameProfile"],
        detection: Optional["DetectionResult"],
    ) -> None:
        if profile and detection and detection.ue4ss and detection.ue4ss.mods_dir:
            self._game_id = profile.game_id
            if detection.framework_mod:
                mod_dir = detection.framework_mod.mod_dir
            else:
                mod_dir = detection.ue4ss.mods_dir / _FALLBACK_MOD_NAME
            self._state_path = mod_dir / "output" / _SESSION_STATE_FILENAME
        else:
            self._game_id = None
            self._state_path = None

    @property
    def deployed_path(self) -> Optional[Path]:
        return self._state_path

    def get_deployed_info(self) -> Optional[dict]:
        if not self._state_path or not self._state_path.exists():
            return None
        stat = self._state_path.stat()
        return {
            "path": str(self._state_path),
            "mtime": stat.st_mtime,
            "size": stat.st_size,
        }

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
                backups.append(SessionBackup(
                    game_id=gid,
                    name=name,
                    timestamp=ts,
                    path=f,
                    display_ts=_format_ts(ts),
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

    def clear_sessions(self, game_id: Optional[str] = None) -> None:
        gid = game_id or self._game_id
        if not gid:
            return
        folder = _SESSIONS_ROOT / gid
        if folder.is_dir():
            shutil.rmtree(folder)

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


def _parse_filename(stem: str) -> Optional[tuple[str, str]]:
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
