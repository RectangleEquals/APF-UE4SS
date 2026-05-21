"""CacheItem — lightweight wrapper around a cached ContentDescriptor on disk."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..descriptors.base import ContentDescriptor


class CacheItem:
    """A downloaded content item sitting in the local cache."""

    def __init__(self, cache_path: Path, content: "ContentDescriptor"):
        self.cache_path = cache_path
        self.content = content

    @property
    def category(self) -> str:
        ct = self.content.content_type
        if ct == "template":
            return "template"
        if ct in ("github_release_binary", "external_url_binary", "manual_binary"):
            return "other"
        return "mod"

    @property
    def display_name(self) -> str:
        return self.content.name or self.content.content_type or "Unknown"

    @property
    def version(self) -> str:
        return self.content.version or ""

    @property
    def game_name(self) -> str:
        return self.content.game_id or ""

    @property
    def install_type(self) -> str:
        return getattr(self.content, "install_type", "") or ""

    @property
    def folder_name(self) -> str:
        from ..descriptors.types import ModDescriptor as _MD
        if isinstance(self.content, _MD):
            return self.content.folder_name or ""
        _src = getattr(self.content, "source", None)
        if _src and _src.folder:
            return _src.folder.split("/")[-1]
        return self.content.name or ""

    @property
    def owner(self) -> str:
        _src = getattr(self.content, "source", None)
        if _src and _src.repo:
            return _src.repo.owner
        return ""

    @property
    def repo(self) -> str:
        _src = getattr(self.content, "source", None)
        if _src and _src.repo:
            return _src.repo.repo
        return ""

    @property
    def components(self) -> list:
        from ..descriptors.types import ModDescriptor as _MD
        if isinstance(self.content, _MD) and self.content.components:
            return self.content.components.types
        return []

    @property
    def bp_pak_files(self) -> list:
        from ..descriptors.types import ModDescriptor as _MD
        if isinstance(self.content, _MD) and self.content.components:
            return self.content.components.bp_pak_files
        return []
