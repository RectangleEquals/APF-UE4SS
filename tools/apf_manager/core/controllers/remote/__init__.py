"""
core.controllers.remote — GitHub API client, caching, release management, Steam thumbnails.

Re-exports for backward compatibility:
    from ...core.controllers.remote import GitHubReleaseManager, SteamThumbnailFetcher
"""

from .github_release import GitHubReleaseManager
from .steam import SteamThumbnailFetcher

__all__ = ["GitHubReleaseManager", "SteamThumbnailFetcher"]
