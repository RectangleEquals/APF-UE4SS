"""
content_filter.py — Interprets selected_content lists for RegistryDescriptor entries.

selected_content semantics:
    None  → unset (show all content from this registry)
    []    → explicit empty (show nothing)
    [...]  → explicit list of content IDs
"""
from __future__ import annotations
from typing import Optional


class ContentFilter:

    @staticmethod
    def includes_ap_mod(selected_content: Optional[list], mod_id: str) -> bool:
        if selected_content is None:
            return True
        return f"mod:{mod_id}" in selected_content or f"framework_mod:{mod_id}" in selected_content

    @staticmethod
    def includes_non_ap_mod(selected_content: Optional[list], folder_name: str) -> bool:
        if selected_content is None:
            return True
        return f"mod:{folder_name}" in selected_content

    @staticmethod
    def includes_template(selected_content: Optional[list], template_path: str) -> bool:
        if selected_content is None:
            return True
        return f"template:{template_path}" in selected_content

    @staticmethod
    def includes_ue4ss(selected_content: Optional[list], repo_full_name: str, tag: str) -> bool:
        if selected_content is None:
            return True
        return f"ue4ss_option:{repo_full_name}:{tag}" in selected_content

    @staticmethod
    def to_viewer_set(selected_content: Optional[list]) -> Optional[set]:
        """Convert selected_content list to a set for the viewer SPA.
        Returns None if selected_content is None (show all), empty set if [].
        """
        if selected_content is None:
            return None
        return set(selected_content)

    @staticmethod
    def from_spa_ids(ids: list[str]) -> list:
        return list(ids)
