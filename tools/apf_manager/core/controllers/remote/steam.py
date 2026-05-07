"""
SteamThumbnailFetcher — fetch and cache Steam game header images.

Uses the public Steam CDN (no API key required).
Cache: ~/.apf_manager/cache/steam/
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Callable, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError


def _cache_dir() -> Path:
    return Path.home() / ".apf_manager" / "cache" / "steam"


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
    def fetch_async(
        app_id: int,
        on_done: Callable[[int, Optional[Path]], None],
    ) -> None:
        """
        Fetch thumbnail for app_id in a background thread.
        Calls on_done(app_id, path) from the worker thread — callers must
        schedule any UI update to the main thread via Clock.schedule_once().
        path is None on failure.
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
