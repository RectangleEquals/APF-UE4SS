"""
ThumbnailCache — async Steam CDN thumbnail fetcher.

Fetches:  https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg
Caches:   ~/.apf_manager/cache/steam/{app_id}.jpg
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional


_CACHE_DIR = Path.home() / ".apf_manager" / "cache" / "steam"
_CDN_URL = "https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"


class ThumbnailCache:
    def __init__(self) -> None:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._in_flight: set[int] = set()
        self._lock = threading.Lock()

    def get(
        self,
        app_id: int,
        on_loaded: Optional[Callable[[Optional[Path]], None]] = None,
    ) -> Optional[Path]:
        cached = self._cached_path(app_id)
        if cached.exists():
            return cached
        if on_loaded is None:
            return None
        with self._lock:
            if app_id in self._in_flight:
                return None
            self._in_flight.add(app_id)
        threading.Thread(target=self._fetch, args=(app_id, on_loaded), daemon=True).start()
        return None

    def is_cached(self, app_id: int) -> bool:
        return self._cached_path(app_id).exists()

    def path(self, app_id: int) -> Optional[Path]:
        p = self._cached_path(app_id)
        return p if p.exists() else None

    def invalidate(self, app_id: int) -> None:
        p = self._cached_path(app_id)
        if p.exists():
            p.unlink()

    @staticmethod
    def _cached_path(app_id: int) -> Path:
        return _CACHE_DIR / f"{app_id}.jpg"

    def _fetch(self, app_id: int, on_loaded: Callable[[Optional[Path]], None]) -> None:
        dest = self._cached_path(app_id)
        try:
            import requests
            url = _CDN_URL.format(app_id=app_id)
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                dest.write_bytes(resp.content)
                on_loaded(dest)
            else:
                on_loaded(None)
        except Exception:
            on_loaded(None)
        finally:
            with self._lock:
                self._in_flight.discard(app_id)
