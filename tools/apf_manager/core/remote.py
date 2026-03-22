"""
RemoteManager — GitHub release checking/downloading + Steam CDN thumbnail fetching.

No hardcoded URLs. All GitHub operations use a caller-supplied API URL.
Steam thumbnails use the public CDN (no API key required).
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import zipfile
from pathlib import Path
from typing import Callable, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


# Cache directory for Steam thumbnails
def _cache_dir() -> Path:
    return Path.home() / ".apf_manager" / "cache" / "steam"


# ---------------------------------------------------------------------------
# GitHub release manager
# ---------------------------------------------------------------------------

class GitHubReleaseManager:
    TIMEOUT = 10  # seconds for info requests

    def __init__(self, api_url: str) -> None:
        """
        api_url: GitHub API URL, e.g.
          https://api.github.com/repos/owner/repo
        """
        self._api_url = api_url.rstrip("/")

    def get_latest_release(self) -> Optional[dict]:
        """Return the latest release metadata dict, or None on failure."""
        url = f"{self._api_url}/releases/latest"
        try:
            req = Request(url, headers={"Accept": "application/vnd.github+json",
                                        "User-Agent": "APFManager"})
            with urlopen(req, timeout=self.TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return None

    def download_asset(self, asset_url: str, dest_path: Path,
                       progress_cb: Optional[Callable[[int, int], None]] = None) -> bool:
        """
        Download a release asset to dest_path.
        progress_cb(bytes_downloaded, total_bytes) is called periodically.
        Returns True on success.
        """
        try:
            req = Request(asset_url, headers={"Accept": "application/octet-stream",
                                              "User-Agent": "APFManager"})
            with urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                downloaded = 0
                with open(dest_path, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            progress_cb(downloaded, total)
            return True
        except Exception:
            return False

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


# ---------------------------------------------------------------------------
# Steam CDN thumbnail fetcher
# ---------------------------------------------------------------------------

class SteamThumbnailFetcher:
    CDN_URL = "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"
    TIMEOUT = 10

    @staticmethod
    def get_cached_path(app_id: int) -> Path:
        return _cache_dir() / f"{app_id}.jpg"

    @staticmethod
    def is_cached(app_id: int) -> bool:
        return SteamThumbnailFetcher.get_cached_path(app_id).exists()

    @staticmethod
    def fetch_async(app_id: int, on_done: Callable[[int, Optional[Path]], None]) -> None:
        """
        Fetch thumbnail for app_id in a background thread.
        Calls on_done(app_id, path) on the calling thread context when complete
        (path is None on failure).
        NOTE: on_done is called from the worker thread; callers must schedule
        any UI update to the main thread via Clock.schedule_once() or similar.
        """
        def worker():
            path = SteamThumbnailFetcher._fetch(app_id)
            on_done(app_id, path)

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _fetch(app_id: int) -> Optional[Path]:
        dest = SteamThumbnailFetcher.get_cached_path(app_id)
        if dest.exists():
            return dest
        url = SteamThumbnailFetcher.CDN_URL.format(appid=app_id)
        try:
            req = Request(url, headers={"User-Agent": "APFManager"})
            with urlopen(req, timeout=SteamThumbnailFetcher.TIMEOUT) as resp:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as f:
                    shutil.copyfileobj(resp, f)
            return dest
        except Exception:
            return None
