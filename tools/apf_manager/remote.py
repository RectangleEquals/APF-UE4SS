"""
APF Manager — GitHub releases integration.

No URLs are hardcoded in this module. The repo_api_url comes from APFConfig
and must be set by the user in the Setup tab.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Callable


class GitHubReleaseManager:
    """Check for and download releases from a configurable GitHub API endpoint."""

    def __init__(self, repo_api_url: str):
        self.repo_api_url = repo_api_url.rstrip("/")

    def _available(self) -> bool:
        return bool(self.repo_api_url)

    def check_latest(self) -> dict | None:
        """
        GET {repo_api_url}/releases/latest
        Returns the release info dict, or None on failure (network error, not configured, etc.).
        """
        if not self._available():
            return None
        try:
            import requests
            resp = requests.get(
                f"{self.repo_api_url}/releases/latest",
                timeout=10,
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def download_asset(self, asset_url: str, dest_dir: Path,
                       progress_cb: Callable[[int, int], None] | None = None) -> Path:
        """
        Download a release asset to dest_dir.
        progress_cb(bytes_downloaded, total_bytes) called periodically if provided.
        Returns the downloaded file Path.
        """
        import requests
        dest_dir.mkdir(parents=True, exist_ok=True)

        resp = requests.get(asset_url, stream=True, timeout=30,
                            headers={"Accept": "application/octet-stream"})
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0))
        filename = asset_url.rstrip("/").split("/")[-1]
        # Use Content-Disposition header if available
        cd = resp.headers.get("content-disposition", "")
        if "filename=" in cd:
            filename = cd.split("filename=")[-1].strip().strip('"')

        dest_file = dest_dir / filename
        downloaded = 0
        with open(dest_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)

        return dest_file

    def extract_release(self, zip_path: Path, dest_dir: Path) -> Path:
        """
        Extract a release zip to dest_dir.
        Returns the path to the extracted contents (dest_dir itself).
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_dir)
        return dest_dir

    @staticmethod
    def get_release_version(release_info: dict) -> str:
        """Extract version tag from GitHub release info dict."""
        return release_info.get("tag_name", "unknown")

    @staticmethod
    def get_asset_url(release_info: dict, name_contains: str) -> str | None:
        """Find the download URL for an asset whose name contains the given string."""
        for asset in release_info.get("assets", []):
            if name_contains.lower() in asset.get("name", "").lower():
                return asset.get("browser_download_url")
        return None
