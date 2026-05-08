"""
DocsService — fetches and caches the APF-UE4SS documentation tree from GitHub.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..models.doc_entry import DocEntry, prettify

if TYPE_CHECKING:
    from ....core.controllers.remote.github_api import GitHubAPI


_PUBLIC_PATH = "docs/public"
_DEV_PATH = "docs/public/dev"


class DocsService:
    """Fetches and caches the documentation tree from GitHub."""

    def __init__(self, api: "GitHubAPI", dev_mode: bool = False) -> None:
        self._api = api
        self._dev_mode = dev_mode
        self._tree: Optional[list[DocEntry]] = None

    def get_tree(self, force_refresh: bool = False) -> list[DocEntry]:
        """Return sorted list of available doc entries (general first, then dev)."""
        if self._tree is not None and not force_refresh:
            return self._tree

        entries: list[DocEntry] = []

        for item in self._api.list_contents(_PUBLIC_PATH, force_refresh=force_refresh):
            if item["type"] == "file" and item["name"].endswith(".md"):
                url = item.get("download_url")
                if url:
                    entries.append(DocEntry(
                        display_name=prettify(item["name"]),
                        path=item["path"],
                        download_url=url,
                        section="general",
                    ))

        if self._dev_mode:
            for item in self._api.list_contents(_DEV_PATH, force_refresh=force_refresh):
                if item["type"] == "file" and item["name"].endswith(".md"):
                    url = item.get("download_url")
                    if url:
                        entries.append(DocEntry(
                            display_name=prettify(item["name"]),
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

    def fetch_content(self, entry: DocEntry, force_refresh: bool = False) -> str:
        """Return raw markdown text for a DocEntry."""
        return self._api.fetch_text(entry.download_url, force_refresh=force_refresh)

    def invalidate(self) -> None:
        """Clear in-memory and disk cache."""
        self._tree = None
        self._api.invalidate_cache()
