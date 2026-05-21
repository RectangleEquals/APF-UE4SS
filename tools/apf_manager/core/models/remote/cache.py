"""
GitHubCache — persistent disk cache with per-entry TTL.

Cache root: ~/.apf_manager/cache/github/{owner}_{repo}/
Structure:
    contents/   ← Contents API directory listings (JSON)
    files/      ← Raw file text keyed by URL hash
    releases/   ← Release metadata
    meta.json   ← Per-entry {stored_at, ttl} index
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)


# Default TTLs (seconds)
TTL_CONTENTS = 3600       # 1 hour
TTL_FILES = 86400         # 24 hours
TTL_RELEASES = 900        # 15 minutes


class GitHubCache:
    def __init__(self, repo_owner: str, repo_name: str) -> None:
        self._root = (
            Path.home() / ".apf_manager" / "cache" / "github"
            / f"{repo_owner}_{repo_name}"
        )
        self._meta_path = self._root / "meta.json"
        self._root.mkdir(parents=True, exist_ok=True)
        self._meta: dict = self._load_meta()

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def get(self, key: str) -> Optional[str]:
        """Return cached value for key, or None if missing/stale."""
        if self.is_stale(key):
            return None
        path = self._key_path(key)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def get_stale(self, key: str) -> Optional[str]:
        """Return cached value regardless of staleness (fallback on errors)."""
        path = self._key_path(key)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store value with the given TTL."""
        path = self._key_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(value, encoding="utf-8")
        except Exception:
            return
        self._meta.setdefault("entries", {})[key] = {
            "stored_at": time.time(),
            "ttl": ttl_seconds,
        }
        self._save_meta()

    def is_stale(self, key: str) -> bool:
        """Return True if the entry is absent or expired."""
        entry = self._meta.get("entries", {}).get(key)
        if not entry:
            return True
        return (time.time() - entry["stored_at"]) > entry["ttl"]

    def invalidate(self, key: Optional[str] = None) -> None:
        """Invalidate a specific key, or the entire cache if key is None."""
        if key is None:
            shutil.rmtree(self._root, ignore_errors=True)
            self._root.mkdir(parents=True, exist_ok=True)
            self._meta = {"entries": {}}
            self._save_meta()
        else:
            self._meta.get("entries", {}).pop(key, None)
            self._save_meta()
            p = self._key_path(key)
            if p.exists():
                p.unlink(missing_ok=True)

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _key_path(self, key: str) -> Path:
        h = hashlib.md5(key.encode()).hexdigest()
        category = key.split("/")[0] if "/" in key else "misc"
        return self._root / category / h

    def _load_meta(self) -> dict:
        if self._meta_path.exists():
            try:
                return json.loads(self._meta_path.read_text(encoding="utf-8"))
            except Exception as exc:
                _log.warning("[cache] Corrupt cache meta at %s; resetting: %s", self._meta_path, exc)
        return {"entries": {}}

    def _save_meta(self) -> None:
        try:
            self._meta_path.write_text(
                json.dumps(self._meta, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            _log.warning("[cache] Failed to persist cache meta to %s: %s", self._meta_path, exc)
