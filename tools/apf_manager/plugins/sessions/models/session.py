"""SessionBackup — dataclass representing a single session backup file."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
