"""
RegistryCache — persistent disk cache for registry traversal data.

Cache root: ~/.apf_manager/github/registry/

Structure:
    meta.json                           # per-entry {stored_at} index
    search_{game_id}.json               # TTL 1h — GitHub topic search results
    {owner}+{repo}/
        traversal.json                  # TTL 1h — traversal result for that repo
        mods/{escaped_mod_id}/
            manifest.json               # TTL 24h
            readme.md                   # TTL 24h

blacklist.json is NEVER cached — always fetched live, held in memory only.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

_CACHE_ROOT = Path.home() / ".apf_manager" / "github" / "registry"
_log = logging.getLogger(__name__)

TTL_SEARCH     = 3600    # 1 hour
TTL_TRAVERSAL  = 3600    # 1 hour
TTL_MOD_DATA   = 86400   # 24 hours


class RegistryCache:
    def __init__(self) -> None:
        self._root = _CACHE_ROOT
        self._root.mkdir(parents=True, exist_ok=True)
        self._meta: dict = self._load_meta()

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def get(self, key: str, ttl: int) -> Optional[str]:
        """Return cached value for key if fresh, else None."""
        if self._is_stale(key, ttl):
            return None
        p = self._key_path(key)
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception as exc:
                _log.warning("[registry_cache] WARN: failed to read cache entry %s: %s", key, exc)
        return None

    def set(self, key: str, value: str) -> None:
        """Write value to cache and update meta."""
        p = self._key_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(value, encoding="utf-8")
        except Exception as exc:
            _log.warning("[registry_cache] WARN: failed to write cache entry %s: %s", key, exc)
            return
        self._meta[key] = {"stored_at": time.time()}
        self._save_meta()

    def invalidate(self, key: str) -> None:
        """Remove a specific cache entry."""
        self._meta.pop(key, None)
        self._save_meta()
        p = self._key_path(key)
        try:
            if p.exists():
                p.unlink()
        except Exception as exc:
            _log.warning("[registry_cache] WARN: failed to delete cache file %s: %s", p, exc)

    def invalidate_all(self) -> None:
        """Wipe all cached data."""
        import shutil
        try:
            shutil.rmtree(self._root, ignore_errors=True)
            self._root.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            _log.warning("[registry_cache] WARN: failed to wipe cache root: %s", exc)
        self._meta = {}

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _is_stale(self, key: str, ttl: int) -> bool:
        meta = self._meta.get(key)
        if not meta:
            return True
        stored_at = meta.get("stored_at", 0)
        return (time.time() - stored_at) > ttl

    def _key_path(self, key: str) -> Path:
        # key uses '/' as separator; first component maps to a subdirectory
        parts = key.split("/", 1)
        if len(parts) == 2:
            return self._root / parts[0] / parts[1]
        return self._root / key

    def _meta_path(self) -> Path:
        return self._root / "meta.json"

    def _load_meta(self) -> dict:
        p = self._meta_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                _log.warning("[registry_cache] WARN: failed to parse meta.json: %s", exc)
        return {}

    def _save_meta(self) -> None:
        try:
            self._meta_path().write_text(
                json.dumps(self._meta), encoding="utf-8"
            )
        except Exception as exc:
            _log.warning("[registry_cache] WARN: failed to save meta.json: %s", exc)
