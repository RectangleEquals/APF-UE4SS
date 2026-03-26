"""
GitHubAPI — general-purpose GitHub REST client.

Used for: docs fetching, release checks, and any future GitHub feature.

Auth token resolution (priority order):
  1. User override  → ~/.apf_manager/github_token.json  {"token": "ghp_..."}
  2. Bundled token  → token_file_path (e.g. plugins/docs_viewer/.github_token)
  3. Unauthenticated fallback (60 req/hr)

All methods are cache-aware and fall back to stale cache on network/auth failure.
The on_status callback surfaces warnings and errors to the caller (e.g. for Snackbar display).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

import requests as _requests

from .github_cache import GitHubCache, TTL_CONTENTS, TTL_FILES, TTL_RELEASES

_API_BASE = "https://api.github.com"
_USER_AGENT = "APFManager/1.0"


class GitHubAPI:
    """
    General-purpose GitHub REST client with caching and graceful fallback.

    Not docs-specific — designed to be reused by any feature that touches GitHub
    (release checker, mod registry, plugin registry, etc.).
    """

    def __init__(
        self,
        repo_owner: str,
        repo_name: str,
        token_file_path: Optional[Path] = None,
        cache: Optional[GitHubCache] = None,
        on_status: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._owner = repo_owner
        self._repo = repo_name
        self._cache = cache or GitHubCache(repo_owner, repo_name)
        self._on_status = on_status or (lambda level, msg: None)
        self._token, self._auth_source = self._resolve_token(token_file_path)
        self._rate_limit_remaining: Optional[int] = None

    # -----------------------------------------------------------------------
    # Contents API
    # -----------------------------------------------------------------------

    def list_contents(self, path: str, force_refresh: bool = False) -> list[dict]:
        """
        List directory contents at the given repo path.
        Returns a list of dicts with keys: name, path, type, download_url, size.
        Falls back to stale cache on network/auth failure.
        """
        cache_key = f"contents/{_safe_key(path)}"

        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    return json.loads(cached)
                except Exception:
                    pass

        url = f"{_API_BASE}/repos/{self._owner}/{self._repo}/contents/{path}"
        try:
            resp = self._get(url)
            self._update_rate_limit(resp)
            data = resp.json()
            if not isinstance(data, list):
                data = [data]
            result = [
                {
                    "name": item.get("name", ""),
                    "path": item.get("path", ""),
                    "type": item.get("type", ""),
                    "download_url": item.get("download_url"),
                    "size": item.get("size", 0),
                }
                for item in data
                if isinstance(item, dict)
            ]
            self._cache.set(cache_key, json.dumps(result), TTL_CONTENTS)
            return result

        except _RateLimitError:
            self._on_status("warn", "GitHub rate limit reached — using cached content")
            return self._load_stale_json(cache_key) or []
        except (_NetworkError, Exception) as exc:
            self._on_status("warn", f"GitHub unreachable — using cached content ({exc})")
            return self._load_stale_json(cache_key) or []

    def fetch_text(self, download_url: str, force_refresh: bool = False) -> str:
        """
        Fetch raw text from a download_url (e.g. raw.githubusercontent.com).
        Uses a separate cache from the API cache. Falls back to stale on failure.
        """
        cache_key = f"files/{_url_key(download_url)}"

        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            # Raw GitHub CDN — auth token not required, but won't hurt
            resp = _requests.get(download_url, headers=self._raw_headers(), timeout=15)
            resp.raise_for_status()
            text = resp.text
            self._cache.set(cache_key, text, TTL_FILES)
            return text

        except _requests.HTTPError as exc:
            self._on_status("warn", f"Failed to fetch file ({exc}) — using cached version")
            return self._cache.get_stale(cache_key) or ""
        except Exception as exc:
            self._on_status("warn", f"Network error fetching file — using cached version")
            return self._cache.get_stale(cache_key) or ""

    # -----------------------------------------------------------------------
    # Releases API
    # -----------------------------------------------------------------------

    def get_latest_release(self, force_refresh: bool = False) -> Optional[dict]:
        """
        Return the latest release metadata dict, or None on failure.
        Short TTL cache (15 min).
        """
        cache_key = "releases/latest"

        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    return json.loads(cached)
                except Exception:
                    pass

        url = f"{_API_BASE}/repos/{self._owner}/{self._repo}/releases/latest"
        try:
            resp = self._get(url)
            self._update_rate_limit(resp)
            data = resp.json()
            self._cache.set(cache_key, json.dumps(data), TTL_RELEASES)
            return data

        except _RateLimitError:
            self._on_status("warn", "GitHub rate limit reached — using cached release info")
            return self._load_stale_json(cache_key)
        except Exception:
            return self._load_stale_json(cache_key)

    def download_asset(
        self,
        asset_url: str,
        dest: Path,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """Download a release asset to dest. Returns True on success."""
        try:
            headers = dict(self._api_headers())
            headers["Accept"] = "application/octet-stream"
            resp = _requests.get(asset_url, headers=headers, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            dest.parent.mkdir(parents=True, exist_ok=True)
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
            return True
        except Exception:
            return False

    # -----------------------------------------------------------------------
    # Auth management
    # -----------------------------------------------------------------------

    def set_user_token(self, token: str) -> None:
        """Persist a user-supplied PAT override to ~/.apf_manager/github_token.json."""
        override_path = Path.home() / ".apf_manager" / "github_token.json"
        override_path.parent.mkdir(parents=True, exist_ok=True)
        override_path.write_text(
            json.dumps({"token": token.strip()}, indent=2), encoding="utf-8"
        )
        self.refresh_auth()

    def clear_user_token(self) -> None:
        """Remove user PAT override; revert to bundled token or unauthenticated."""
        override_path = Path.home() / ".apf_manager" / "github_token.json"
        if override_path.exists():
            override_path.unlink()
        self.refresh_auth()

    def refresh_auth(self, token_file_path: Optional[Path] = None) -> None:
        """Re-resolve token from disk."""
        self._token, self._auth_source = self._resolve_token(token_file_path)

    def invalidate_cache(self) -> None:
        """Clear all cached data for this repo."""
        self._cache.invalidate()
        self._on_status("info", "Cache cleared.")

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        return self._auth_source != "unauthenticated"

    @property
    def rate_limit_remaining(self) -> Optional[int]:
        return self._rate_limit_remaining

    @property
    def auth_source(self) -> str:
        """Returns 'user_override', 'bundled', or 'unauthenticated'."""
        return self._auth_source

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _resolve_token(self, bundled_path: Optional[Path]) -> tuple[Optional[str], str]:
        # 1. User override
        user_override = Path.home() / ".apf_manager" / "github_token.json"
        if user_override.exists():
            try:
                data = json.loads(user_override.read_text(encoding="utf-8"))
                token = data.get("token", "").strip()
                if token:
                    return token, "user_override"
            except Exception:
                pass
        # 2. Bundled token file
        if bundled_path:
            p = Path(bundled_path)
            if p.exists():
                try:
                    token = p.read_text(encoding="utf-8").strip()
                    if token:
                        return token, "bundled"
                except Exception:
                    pass
        # 3. Unauthenticated
        return None, "unauthenticated"

    def _api_headers(self) -> dict:
        h = {
            "Accept": "application/vnd.github+json",
            "User-Agent": _USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _raw_headers(self) -> dict:
        h = {"User-Agent": _USER_AGENT}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _get(self, url: str) -> _requests.Response:
        try:
            resp = _requests.get(url, headers=self._api_headers(), timeout=10)
        except _requests.ConnectionError as exc:
            raise _NetworkError(str(exc)) from exc
        except _requests.Timeout as exc:
            raise _NetworkError(str(exc)) from exc

        if resp.status_code in (403, 429):
            raise _RateLimitError(f"HTTP {resp.status_code}")
        resp.raise_for_status()
        return resp

    def _update_rate_limit(self, resp: _requests.Response) -> None:
        try:
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                self._rate_limit_remaining = int(remaining)
                if self._rate_limit_remaining < 10:
                    self._on_status(
                        "warn",
                        f"GitHub rate limit low: {self._rate_limit_remaining} requests remaining",
                    )
        except Exception:
            pass

    def _load_stale_json(self, cache_key: str) -> Optional[dict | list]:
        stale = self._cache.get_stale(cache_key)
        if stale:
            try:
                return json.loads(stale)
            except Exception:
                pass
        return None


# ---------------------------------------------------------------------------
# Internal exception helpers
# ---------------------------------------------------------------------------

class _RateLimitError(Exception):
    pass

class _NetworkError(Exception):
    pass


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _safe_key(s: str) -> str:
    return s.replace("/", "_").replace(" ", "_")

def _url_key(url: str) -> str:
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()
