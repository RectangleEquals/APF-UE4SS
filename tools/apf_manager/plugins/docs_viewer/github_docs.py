"""
GitHubDocsService — fetches and caches the APF-UE4SS documentation tree.

Doc layout in the repo:
    docs/public/README.md          ← general landing page
    docs/public/apf_manager.md     ← APF Manager user guide
    docs/public/dev/               ← developer docs (dev_mode only)
        README.md, framework.md, logic.md, manifest.md, ...

DocEntry represents a single document file in the tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.remote.github_api import GitHubAPI


_PUBLIC_PATH = "docs/public"
_DEV_PATH = "docs/public/dev"

# Special display name overrides
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


def _prettify(filename: str) -> str:
    """Turn a filename into a readable display name."""
    if filename in _NAME_OVERRIDES:
        return _NAME_OVERRIDES[filename]
    name = re.sub(r"\.(md|txt)$", "", filename, flags=re.IGNORECASE)
    name = re.sub(r"[_\-]+", " ", name)
    return name.title()


class GitHubDocsService:
    """
    Fetches and caches the documentation tree from GitHub.
    Provides content fetching with automatic fallback to stale cache.
    """

    def __init__(self, api: "GitHubAPI", dev_mode: bool = False) -> None:
        self._api = api
        self._dev_mode = dev_mode
        self._tree: Optional[list[DocEntry]] = None  # In-memory cache

    # -----------------------------------------------------------------------
    # Tree
    # -----------------------------------------------------------------------

    def get_tree(self, force_refresh: bool = False) -> list[DocEntry]:
        """
        Return the list of available doc entries.
        Entries are sorted: general docs first, then dev docs (dev_mode only).
        """
        if self._tree is not None and not force_refresh:
            return self._tree

        entries: list[DocEntry] = []

        # General docs
        for item in self._api.list_contents(_PUBLIC_PATH, force_refresh=force_refresh):
            if item["type"] == "file" and item["name"].endswith(".md"):
                url = item.get("download_url")
                if url:
                    entries.append(DocEntry(
                        display_name=_prettify(item["name"]),
                        path=item["path"],
                        download_url=url,
                        section="general",
                    ))

        # Dev docs (dev mode only)
        if self._dev_mode:
            for item in self._api.list_contents(_DEV_PATH, force_refresh=force_refresh):
                if item["type"] == "file" and item["name"].endswith(".md"):
                    url = item.get("download_url")
                    if url:
                        entries.append(DocEntry(
                            display_name=_prettify(item["name"]),
                            path=item["path"],
                            download_url=url,
                            section="dev",
                        ))

        self._tree = entries
        return entries

    def get_default_entry(self) -> Optional[DocEntry]:
        """Return the docs/public/README.md entry (the starting page)."""
        for entry in self.get_tree():
            if entry.path.endswith("README.md") and entry.section == "general":
                return entry
        tree = self.get_tree()
        return tree[0] if tree else None

    def get_entry_by_path(self, path: str) -> Optional[DocEntry]:
        """Find an entry by its full repo path."""
        for entry in self.get_tree():
            if entry.path == path:
                return entry
        return None

    # -----------------------------------------------------------------------
    # Content
    # -----------------------------------------------------------------------

    def fetch_content(self, entry: DocEntry, force_refresh: bool = False) -> str:
        """Return raw markdown text for a DocEntry."""
        return self._api.fetch_text(entry.download_url, force_refresh=force_refresh)

    def invalidate(self) -> None:
        """Clear in-memory and disk cache."""
        self._tree = None
        self._api.invalidate_cache()
