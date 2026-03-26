"""
core.remote — GitHub API client, caching, release management, Steam thumbnails.

Re-exports for backward compatibility:
    from ...core.remote import GitHubReleaseManager, SteamThumbnailFetcher
"""

from .github_release_manager import GitHubReleaseManager
from .steam_thumbnail import SteamThumbnailFetcher

__all__ = ["GitHubReleaseManager", "SteamThumbnailFetcher"]
