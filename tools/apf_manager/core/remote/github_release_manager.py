"""
GitHubReleaseManager — check for app/component updates and download release assets.

Refactored to use GitHubAPI (cache-aware, auth-aware, status callbacks).
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .github_api import GitHubAPI


class GitHubReleaseManager:
    """
    Checks for the latest release and downloads assets from a GitHub repo.

    Requires a GitHubAPI instance (injected). The API handles caching,
    auth, and rate-limit fallback.
    """

    def __init__(self, api: "GitHubAPI") -> None:
        self._api = api

    def get_latest_release(self) -> Optional[dict]:
        """Return the latest release metadata dict, or None on failure."""
        return self._api.get_latest_release()

    def download_asset(
        self,
        asset_url: str,
        dest_path: Path,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """
        Download a release asset to dest_path.
        progress_cb(bytes_downloaded, total_bytes) is called periodically.
        Returns True on success.
        """
        return self._api.download_asset(asset_url, dest_path, progress_cb)

    @staticmethod
    def extract_zip(zip_path: Path, dest_dir: Path) -> bool:
        """Extract a zip archive to dest_dir. Returns True on success."""
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(dest_dir)
            return True
        except Exception:
            return False
