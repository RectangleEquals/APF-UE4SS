"""
GitHubAPI — general-purpose GitHub REST client.

Used for: docs fetching, release checks, and any future GitHub feature
(update checker, CI/CD Actions plugin, mod registry, mod sets, plugin registry, etc.).

Auth token resolution (priority order):
  1. User override  → ~/.apf_manager/github_token.json  {"token": "ghp_..."}
  2. Bundled token  → token_file_path (e.g. plugins/docs_viewer/.github_token)
  3. Unauthenticated fallback (60 req/hr)

All methods are cache-aware and fall back to stale cache on network/auth failure.
The on_status callback surfaces warnings and errors to the caller (e.g. for Snackbar display).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Optional

from githubkit import GitHub, TokenAuthStrategy
from githubkit.exception import RequestFailed, RateLimitExceeded, RequestTimeout
import httpx as _httpx

from .github_cache import GitHubCache, TTL_CONTENTS, TTL_FILES, TTL_RELEASES

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
        self._bundled_token_path = token_file_path
        self._token, self._auth_source = self._resolve_token(token_file_path)
        self._client: GitHub = self._make_client()
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

        try:
            resp = self._client.rest.repos.get_content(self._owner, self._repo, path)
            self._update_rate_limit(resp.headers)
            data = resp.parsed_data
            if not isinstance(data, list):
                data = [data]
            result = [
                {
                    "name": item.name,
                    "path": item.path,
                    "type": item.type,
                    "download_url": getattr(item, "download_url", None),
                    "size": getattr(item, "size", 0),
                }
                for item in data
            ]
            self._cache.set(cache_key, json.dumps(result), TTL_CONTENTS)
            return result

        except RateLimitExceeded as exc:
            return self._handle_rate_limit(exc, cache_key, fallback=[])

        except RequestFailed as exc:
            return self._handle_request_failed(exc, cache_key, fallback=[])

        except (RequestTimeout, _httpx.ConnectError, _httpx.TimeoutException) as exc:
            return self._handle_network_error(exc, cache_key, fallback=[])

        except Exception as exc:
            self._on_status("warn", f"GitHub error listing {path}: {exc}")
            return self._load_stale_json(cache_key) or []

    def fetch_text(self, download_url: str, force_refresh: bool = False) -> str:
        """
        Fetch raw text from a download_url (e.g. raw.githubusercontent.com).
        Uses a separate cache keyed by URL hash. Falls back to stale on failure.
        """
        cache_key = f"files/{_url_key(download_url)}"

        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            resp = _httpx.get(
                download_url,
                headers=self._cdn_headers(),
                timeout=15,
                follow_redirects=True,
            )
            resp.raise_for_status()
            text = resp.text
            self._cache.set(cache_key, text, TTL_FILES)
            return text

        except (_httpx.HTTPStatusError, _httpx.ConnectError, _httpx.TimeoutException) as exc:
            stale = self._cache.get_stale(cache_key)
            if stale:
                self._on_status("warn", f"Failed to fetch file — showing cached version ({exc})")
                return stale
            self._on_status("error", f"Failed to fetch file and no cached version available ({exc})")
            return ""

        except Exception as exc:
            stale = self._cache.get_stale(cache_key)
            if stale:
                self._on_status("warn", f"Unexpected error fetching file — showing cached version ({exc})")
                return stale
            self._on_status("error", f"Unexpected error fetching file, no cache ({exc})")
            return ""

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

        try:
            resp = self._client.rest.repos.get_latest_release(self._owner, self._repo)
            self._update_rate_limit(resp.headers)
            release = resp.parsed_data
            data = {
                "tag_name": release.tag_name,
                "published_at": str(release.published_at),
                "body": release.body or "",
                "assets": [
                    {
                        "name": a.name,
                        "browser_download_url": a.browser_download_url,
                        "size": a.size,
                    }
                    for a in (release.assets or [])
                ],
            }
            self._cache.set(cache_key, json.dumps(data), TTL_RELEASES)
            return data

        except RateLimitExceeded as exc:
            return self._handle_rate_limit(exc, cache_key, fallback=None)

        except RequestFailed as exc:
            return self._handle_request_failed(exc, cache_key, fallback=None)

        except (RequestTimeout, _httpx.ConnectError, _httpx.TimeoutException) as exc:
            stale = self._cache.get_stale(cache_key)
            if stale is not None:
                self._on_status("warn", f"GitHub unreachable — using cached release info ({exc})")
                try:
                    return json.loads(stale)
                except Exception:
                    pass
            self._on_status("error", f"GitHub unreachable and no cached release info ({exc})")
            return None

        except Exception as exc:
            self._on_status("warn", f"Unexpected error fetching release info: {exc}")
            return self._load_stale_json(cache_key)

    def download_asset(
        self,
        asset_url: str,
        dest: Path,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """Download a release asset to dest. Returns True on success."""
        try:
            headers = self._cdn_headers()
            headers["Accept"] = "application/octet-stream"
            dest.parent.mkdir(parents=True, exist_ok=True)
            total = 0
            downloaded = 0
            with _httpx.stream(
                "GET", asset_url, headers=headers, timeout=60, follow_redirects=True
            ) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0))
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes(65536):
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
        """Re-resolve token from disk and rebuild the GitHub client."""
        path = token_file_path or self._bundled_token_path
        self._token, self._auth_source = self._resolve_token(path)
        self._client = self._make_client()

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
    # Internals — client construction
    # -----------------------------------------------------------------------

    def _make_client(self) -> GitHub:
        if self._token:
            return GitHub(auth=TokenAuthStrategy(self._token))
        return GitHub()

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

    def _cdn_headers(self) -> dict:
        """Headers for raw CDN / asset downloads (not the API endpoint)."""
        h = {"User-Agent": _USER_AGENT}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _update_rate_limit(self, headers) -> None:
        try:
            remaining = headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                self._rate_limit_remaining = int(remaining)
                if self._rate_limit_remaining < 10:
                    self._on_status(
                        "warn",
                        f"GitHub rate limit low: {self._rate_limit_remaining} requests remaining",
                    )
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Internals — error handlers
    # -----------------------------------------------------------------------

    def _handle_rate_limit(self, exc: RateLimitExceeded, cache_key: str, fallback):
        retry_secs = int(exc.retry_after.total_seconds()) if exc.retry_after else 0
        reset_str = _format_reset_time(int(time.time()) + retry_secs) if retry_secs else "soon"
        stale = self._load_stale_json(cache_key)
        if stale is not None:
            self._on_status("warn", f"GitHub rate limit hit (resets ~{reset_str}) — using cached content")
            return stale
        self._on_status("error", f"GitHub rate limit hit (resets ~{reset_str}) — no cached content available")
        return fallback

    def _handle_request_failed(self, exc: RequestFailed, cache_key: str, fallback):
        sc = exc.response.status_code
        url = str(exc.request.url)
        remaining = exc.response.headers.get("X-RateLimit-Remaining", "")
        if sc in (401, 403) and remaining != "0":
            # Auth failure — downgrade to unauthenticated and rebuild client
            self._on_status(
                "warn",
                f"GitHub token invalid or expired (HTTP {sc}) — switching to unauthenticated",
            )
            self._token = None
            self._auth_source = "unauthenticated"
            self._client = self._make_client()
        else:
            self._on_status("warn", f"GitHub API error (HTTP {sc}) for {url}")
        return self._load_stale_json(cache_key) or fallback

    def _handle_network_error(self, exc: Exception, cache_key: str, fallback):
        stale = self._load_stale_json(cache_key)
        if stale is not None:
            self._on_status("warn", f"GitHub unreachable — using cached content ({exc})")
            return stale
        self._on_status("error", f"GitHub unreachable and no cached content available ({exc})")
        return fallback

    def _load_stale_json(self, cache_key: str) -> Optional[dict | list]:
        stale = self._cache.get_stale(cache_key)
        if stale:
            try:
                return json.loads(stale)
            except Exception:
                pass
        return None


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _safe_key(s: str) -> str:
    return s.replace("/", "_").replace(" ", "_")


def _url_key(url: str) -> str:
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()


def _format_reset_time(unix_ts: int) -> str:
    """Format a Unix timestamp as a human-readable local time string."""
    import datetime
    try:
        return datetime.datetime.fromtimestamp(unix_ts).strftime("%H:%M:%S")
    except Exception:
        return str(unix_ts)
