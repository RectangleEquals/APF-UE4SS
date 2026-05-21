"""cache_stats.py — pure data model for the Downloads-tab cache graph."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING


@dataclass
class CacheSegment:
    """One logical group of cached items (e.g. 'Palworld Mods', 'UE4SS binaries')."""

    label: str
    category: str           # "mod" | "template" | "other"
    game_id: str            # game this belongs to, or "" for cross-game items
    size_bytes: int
    item_count: int
    cache_paths: list = field(default_factory=list)  # list[Path] — for controller free ops

    @property
    def size_mb(self) -> float:
        return self.size_bytes / 1_048_576

    @property
    def size_fmt(self) -> str:
        b = self.size_bytes
        if b >= 1_073_741_824:
            return f"{b / 1_073_741_824:.1f} GB"
        if b >= 1_048_576:
            return f"{b / 1_048_576:.1f} MB"
        if b >= 1_024:
            return f"{b / 1_024:.1f} KB"
        return f"{b} B"


@dataclass
class CacheStats:
    """Aggregated cache statistics, computed by CacheController.compute_stats()."""

    segments: list = field(default_factory=list)   # list[CacheSegment]
    total_bytes: int = 0
    game_id: str = ""                               # Active game context

    @property
    def is_empty(self) -> bool:
        return self.total_bytes == 0

    @property
    def total_fmt(self) -> str:
        b = self.total_bytes
        if b >= 1_073_741_824:
            return f"{b / 1_073_741_824:.1f} GB"
        if b >= 1_048_576:
            return f"{b / 1_048_576:.1f} MB"
        if b >= 1_024:
            return f"{b / 1_024:.1f} KB"
        return f"{b} B"

    @property
    def top_segments(self) -> list:
        """Up to 4 largest segments, sorted descending by size."""
        return sorted(self.segments, key=lambda s: s.size_bytes, reverse=True)[:4]

