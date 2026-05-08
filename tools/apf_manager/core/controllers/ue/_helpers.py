"""Shared filesystem helpers for UE detection controllers."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


def _find_file_ci(directory: Path, name: str) -> Optional[Path]:
    """Case-insensitive file search within a directory (non-recursive)."""
    name_lower = name.lower()
    try:
        for entry in directory.iterdir():
            if entry.is_file() and entry.name.lower() == name_lower:
                return entry
    except (PermissionError, OSError) as exc:
        print(f"[APFManager] Cannot scan '{directory}' for '{name}': {exc}", file=sys.stderr)
    return None


def _find_dir_ci(directory: Path, name: str) -> Optional[Path]:
    """Case-insensitive directory search within a directory (non-recursive)."""
    name_lower = name.lower()
    try:
        for entry in directory.iterdir():
            if entry.is_dir() and entry.name.lower() == name_lower:
                return entry
    except (PermissionError, OSError) as exc:
        print(f"[APFManager] Cannot scan '{directory}' for dir '{name}': {exc}", file=sys.stderr)
    return None
