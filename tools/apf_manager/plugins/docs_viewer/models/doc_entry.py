from __future__ import annotations

import re
from dataclasses import dataclass


_NAME_OVERRIDES: dict[str, str] = {
    "README.md": "Overview",
}


@dataclass
class DocEntry:
    display_name: str    # Human-readable label in the sidebar
    path: str            # Full path from repo root (e.g. "docs/public/README.md")
    download_url: str    # Raw content URL
    section: str         # "general" or "dev"
    commit: str = ""     # Short git hash of last commit (dev mode only)
    commit_url: str = "" # Full GitHub commit URL (dev mode only)


def prettify(filename: str) -> str:
    """Turn a filename into a readable display name."""
    if filename in _NAME_OVERRIDES:
        return _NAME_OVERRIDES[filename]
    name = re.sub(r"\.(md|txt)$", "", filename, flags=re.IGNORECASE)
    name = re.sub(r"[_\-]+", " ", name)
    return name.title()
