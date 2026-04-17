"""
GitHubAPI — general-purpose GitHub REST client.

Used for: docs fetching, release checks, and any future GitHub feature
(update checker, CI/CD Actions plugin, mod registry, mod sets, plugin registry, etc.).

Auth token resolution (priority order):
  1. User override  → ~/.apf_manager/github_token.json  {"token": "ghp_..."}
  2. Bundled token  → token_file_path (e.g. data/.github_token via _BUNDLED_TOKEN_PATH)
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

# Bundled PAT — centralized location for all plugins that need GitHub auth
_BUNDLED_TOKEN_PATH = Path(__file__).parent.parent.parent / "data" / ".github_token"

# Module-level cache so any plugin can read the most recent rate limit state
# without holding a reference to a specific GitHubAPI instance.
# Keyed by auth_source ('user_override', 'bundled', 'unauthenticated', 'devtools').
# Value: (remaining, limit, reset_ts)
_rate_limit_global: dict = {}

# Persistent cache path — survives app restarts so the proactive gate works
# even if the app was closed while rate-limited.
_RATE_LIMIT_CACHE_PATH = Path.home() / ".apf_manager" / "github" / "rate_limit.json"


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
        direct_token: Optional[str] = None,
    ) -> None:
        self._owner = repo_owner
        self._repo = repo_name
        self._cache = cache or GitHubCache(repo_owner, repo_name)
        self._on_status = on_status or (lambda level, msg: None)
        self._bundled_token_path = token_file_path
        self._token, self._auth_source = self._resolve_token(token_file_path, direct_token)
        self._client: GitHub = self._make_client()
        # Lazy — avoids circular import at module load time
        self._release_manager: Optional["GitHubReleaseManager"] = None
        self._rate_limit_remaining: Optional[int] = None
        self._rate_limit_limit: Optional[int] = None
        self._rate_limit_reset: Optional[int] = None

    # -----------------------------------------------------------------------
    # Release manager property
    # -----------------------------------------------------------------------

    @property
    def releases(self) -> "GitHubReleaseManager":
        """
        The GitHubReleaseManager for this repo.
        Constructed lazily on first access to avoid import-time circularity.
        """
        if self._release_manager is None:
            from .github_release_manager import GitHubReleaseManager
            self._release_manager = GitHubReleaseManager(self)
        return self._release_manager

    # ── Typed convenience methods ────────────────────────────────────────────

    def get_latest_release_typed(
        self, force_refresh: bool = False
    ) -> "Optional[RepoRelease]":
        """Return latest stable release as a typed RepoRelease, or None."""
        return self.releases.fetch_latest(force_refresh=force_refresh)

    def get_latest_prerelease_typed(
        self, force_refresh: bool = False
    ) -> "Optional[RepoRelease]":
        """Return latest pre-release as a typed RepoRelease, or None."""
        return self.releases.fetch_latest_prerelease(force_refresh=force_refresh)

    def fetch_updates(
        self, *,
        since_date=None,
        since_tag: Optional[str] = None,
        include_prereleases: bool = True,
        force_refresh: bool = False,
    ) -> "list[RepoRelease]":
        """Return all releases newer than the given reference point."""
        return self.releases.fetch_updates(
            since_date=since_date,
            since_tag=since_tag,
            include_prereleases=include_prereleases,
            force_refresh=force_refresh,
        )

    # -----------------------------------------------------------------------
    # Contents API
    # -----------------------------------------------------------------------

    def list_contents(self, path: str, force_refresh: bool = False) -> list[dict]:
        """
        List directory contents at the given repo path.
        Returns a list of dicts with keys: name, path, type, download_url, size.
        Falls back to stale cache on network/auth failure.
        """
        if self._check_rate_limit():
            return []

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
                    "submodule_git_url": getattr(item, "submodule_git_url", None),
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
        Return the latest stable release as a legacy dict, or None on failure.
        Delegates to GitHubReleaseManager which handles caching and error handling.

        Legacy dict schema: {tag_name, published_at, body, assets[{name, browser_download_url, size}]}
        """
        return self.releases.get_latest_release_dict(force_refresh=force_refresh)

    def list_releases(
        self,
        tag_prefix: str = "",
        per_page: int = 30,
        force_refresh: bool = False,
    ) -> list[dict]:
        """
        Return release metadata dicts, optionally filtered by tag prefix.
        Delegates to GitHubReleaseManager.
        """
        return self.releases.list_releases_dict(
            tag_prefix=tag_prefix,
            per_page=per_page,
            force_refresh=force_refresh,
        )

    # -----------------------------------------------------------------------
    # User / collaborator API (used by github_auth)
    # -----------------------------------------------------------------------

    def get_authenticated_user(self) -> Optional[str]:
        """Return the login name of the authenticated user, or None on failure."""
        if self._check_rate_limit():
            return None
        try:
            resp = self._client.rest.users.get_authenticated()
            self._update_rate_limit(resp.headers)
            return resp.parsed_data.login
        except Exception:
            return None

    def get_collaborator_permission(
        self, owner: str, repo: str, username: str
    ) -> Optional[str]:
        """Return the collaborator permission level for username, or None on failure."""
        if self._check_rate_limit():
            return None
        try:
            resp = self._client.rest.repos.get_collaborator_permission_level(
                owner, repo, username
            )
            self._update_rate_limit(resp.headers)
            return resp.parsed_data.permission
        except Exception:
            return None

    def search_repos(self, query: str, per_page: int = 30) -> list[dict]:
        """
        Search GitHub repositories by query string.

        Example: search_repos('topic:apf-ue4ss-registry-palworld')
        Maps to GET /search/repositories?q={query} — NOT /search/topics.
        Returns list of {owner, repo, stars, description, html_url, last_push_days}.

        Uses a separate rate limit key ('auth_source_search') so the search
        limit (30 req/min) never pollutes the REST limit display (5000 req/hr).
        Both limits are persisted to disk and show the warning dialog on exhaustion.
        """
        search_key = self._auth_source + "_search"
        search_info = _rate_limit_global.get(search_key)
        if search_info:
            remaining, _limit, reset_ts = search_info
            if remaining == 0 and reset_ts and time.time() < reset_ts:
                self._on_status("rate_limit_exceeded_search", _format_reset_time(reset_ts))
                return []

        cache_key = f"search/{_safe_key(query)}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except Exception:
                pass

        try:
            resp = self._client.rest.search.repos(q=query, per_page=per_page)
            self._update_rate_limit(resp.headers, rate_limit_key=search_key)
            from datetime import timezone, datetime as _dt
            now_utc = _dt.now(timezone.utc)

            # Try pydantic first; if the model is out of sync with GitHub's API
            # (e.g. a required field was removed from responses), fall back to
            # resp.json() — githubkit's own raw-JSON method, no additional network call.
            try:
                raw_items = [
                    {"owner": item.owner.login if item.owner else "",
                     "name":  item.name,
                     "stars": item.stargazers_count,
                     "desc":  item.description or "",
                     "url":   item.html_url or "",
                     "pushed": item.pushed_at}
                    for item in resp.parsed_data.items
                ]
            except Exception:
                raw_items = [
                    {"owner": r.get("owner", {}).get("login", ""),
                     "name":  r.get("name", ""),
                     "stars": r.get("stargazers_count", 0),
                     "desc":  r.get("description") or "",
                     "url":   r.get("html_url") or "",
                     "pushed": r.get("pushed_at")}
                    for r in resp.json().get("items", [])
                ]

            result = []
            for item in raw_items:
                try:
                    pushed = item["pushed"]
                    if isinstance(pushed, str):
                        pushed = _dt.fromisoformat(pushed.replace("Z", "+00:00"))
                    if pushed and hasattr(pushed, "tzinfo") and pushed.tzinfo is None:
                        pushed = pushed.replace(tzinfo=timezone.utc)
                    days = (now_utc - pushed).days if pushed else 999
                except Exception:
                    days = 999
                result.append({
                    "owner":          item["owner"],
                    "repo":           item["name"],
                    "stars":          item["stars"],
                    "description":    item["desc"],
                    "html_url":       item["url"],
                    "last_push_days": days,
                })
            self._cache.set(cache_key, json.dumps(result), 3600)
            return result

        except RateLimitExceeded as exc:
            return self._handle_rate_limit(exc, cache_key, fallback=[])
        except RequestFailed as exc:
            return self._handle_request_failed(exc, cache_key, fallback=[])
        except (_httpx.ConnectError, _httpx.TimeoutException) as exc:
            stale = self._load_stale_json(cache_key)
            if stale is not None:
                self._on_status("warn", f"GitHub search unreachable — using cached results ({exc})")
                return stale
            self._on_status("error", f"GitHub search unreachable and no cached results ({exc})")
            return []
        except Exception as exc:
            self._on_status("warn", f"GitHub search error: {exc}")
            return self._load_stale_json(cache_key) or []

    # -----------------------------------------------------------------------
    # Raw client escape hatch (used by ci_manager for DevTools-specific calls)
    # -----------------------------------------------------------------------

    @property
    def client(self) -> GitHub:
        """
        Expose the underlying githubkit client for calls not wrapped by this class.

        Callers must call self.update_rate_limit(resp.headers) after each response
        so that rate limit state is tracked globally.
        """
        return self._client

    def update_rate_limit(self, headers) -> None:
        """Update rate limit state from a response's headers.

        Use when calling self.client directly for operations not wrapped by this
        class (e.g. ci_manager workflow/branch/release management calls).
        """
        self._update_rate_limit(headers)

    def _check_rate_limit(self) -> bool:
        """
        Return True if this auth source is currently rate-limited (remaining == 0
        and the reset window has not yet passed).

        Fires on_status("rate_limit_exceeded", reset_str) so listeners can show a
        dialog. Callers MUST return their fallback value immediately when True is
        returned — no GitHub request should be made.
        """
        info = _rate_limit_global.get(self._auth_source)
        if info is None:
            return False
        remaining, _limit, reset_ts = info
        if remaining == 0 and reset_ts and time.time() < reset_ts:
            self._on_status("rate_limit_exceeded", _format_reset_time(reset_ts))
            return True
        return False

    def download_asset(
        self,
        asset_url: str,
        dest: Path,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """Download a release asset to dest. Delegates to GitHubReleaseManager."""
        return self.releases.download_asset(asset_url, dest, progress_cb)

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
        self._release_manager = None   # invalidate so next access gets a fresh manager

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
    def rate_limit_limit(self) -> Optional[int]:
        return self._rate_limit_limit

    @property
    def rate_limit_reset(self) -> Optional[int]:
        return self._rate_limit_reset

    @staticmethod
    def get_global_rate_limit_info() -> Optional[tuple]:
        """Return (remaining, limit, reset_ts) for REST API (lowest remaining), or None.
        Excludes search keys so the 30/min search limit never pollutes the 5000/hr display."""
        rest = {k: v for k, v in _rate_limit_global.items() if not k.endswith("_search")}
        if not rest:
            return None
        return min(rest.values(), key=lambda v: v[0])

    @staticmethod
    def get_global_search_rate_limit_info() -> Optional[tuple]:
        """Return (remaining, limit, reset_ts) for the search API (30 req/min), or None."""
        search = {k: v for k, v in _rate_limit_global.items() if k.endswith("_search")}
        if not search:
            return None
        return min(search.values(), key=lambda v: v[0])

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

    def _resolve_token(
        self,
        bundled_path: Optional[Path],
        direct_token: Optional[str] = None,
    ) -> tuple[Optional[str], str]:
        # 0. Direct token (highest priority — used by DevTools auth/CI flows)
        if direct_token:
            return direct_token.strip(), "devtools"
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

    def _update_rate_limit(self, headers, rate_limit_key: Optional[str] = None) -> None:
        try:
            remaining = headers.get("X-RateLimit-Remaining")
            limit = headers.get("X-RateLimit-Limit")
            reset = headers.get("X-RateLimit-Reset")

            rem_int = int(remaining) if remaining is not None else None
            lim_int = int(limit)     if limit     is not None else None
            rst_int = int(reset)     if reset     is not None else None

            if rem_int is None:
                return

            key = rate_limit_key or self._auth_source

            # Only clobber instance vars for primary (non-keyed) calls — prevents
            # search's 30/min limit from overwriting the REST 5000/hr display values.
            if rate_limit_key is None:
                self._rate_limit_remaining = rem_int
                if lim_int is not None:
                    self._rate_limit_limit = lim_int
                if rst_int is not None:
                    self._rate_limit_reset = rst_int

            _rate_limit_global[key] = (rem_int, lim_int or 5000, rst_int or 0)
            _save_rate_limit_cache()

            self._on_status(
                "debug",
                f"GitHub API: {rem_int}{'/' + str(lim_int) if lim_int else ''} requests remaining",
            )

            if rem_int == 0 and rst_int:
                # Fire immediately on the last successful call so the dialog appears
                # before the next request. Use a separate event for search limits so
                # the dialog can show context-appropriate messaging.
                event = "rate_limit_exceeded_search" if key.endswith("_search") else "rate_limit_exceeded"
                self._on_status(event, _format_reset_time(rst_int))
            elif rem_int < 10 and rate_limit_key is None:
                self._on_status(
                    "warn",
                    f"GitHub rate limit low: {rem_int} requests remaining",
                )
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Internals — error handlers
    # -----------------------------------------------------------------------

    def _handle_rate_limit(self, exc: RateLimitExceeded, cache_key: str, fallback):
        retry_secs = int(exc.retry_after.total_seconds()) if exc.retry_after else 0
        reset_ts = int(time.time()) + retry_secs if retry_secs else 0
        reset_str = _format_reset_time(reset_ts) if reset_ts else "soon"
        stale = self._load_stale_json(cache_key)
        if stale is not None:
            self._on_status("warn", f"GitHub rate limit hit (resets ~{reset_str}) — using cached content")
        else:
            self._on_status("error", f"GitHub rate limit hit (resets ~{reset_str}) — no cached content available")
        # Signal callers that can show a dialog (level "rate_limit_exceeded", msg = reset time string)
        self._on_status("rate_limit_exceeded", reset_str)
        return stale if stale is not None else fallback

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
    """Format a Unix timestamp as '~N minutes (H:MM AM/PM TZ)' relative + absolute local time."""
    import datetime
    import time as _time
    try:
        dt = datetime.datetime.fromtimestamp(unix_ts)
        minutes = max(0, int((unix_ts - _time.time()) / 60))
        hour_12 = str(int(dt.strftime("%I")))   # "%I" zero-pads; int() strips it
        am_pm   = dt.strftime("%p")             # "AM" or "PM"
        minute  = dt.strftime("%M")
        tz      = _time.strftime("%Z")          # local timezone abbreviation e.g. "PST", "EST"
        time_str = f"{hour_12}:{minute} {am_pm} {tz}"
        if minutes <= 0:
            return f"now ({time_str})"
        if minutes == 1:
            return f"~1 minute ({time_str})"
        return f"~{minutes} minutes ({time_str})"
    except Exception:
        return str(unix_ts)


def _load_rate_limit_cache() -> None:
    """
    Load persisted rate limit state into _rate_limit_global on app startup.

    Only entries whose reset window has not yet passed are applied — stale
    entries (reset_ts <= now) are ignored so expired limits don't block calls.
    """
    try:
        if not _RATE_LIMIT_CACHE_PATH.exists():
            return
        data = json.loads(_RATE_LIMIT_CACHE_PATH.read_text(encoding="utf-8"))
        now = time.time()
        for source, info in data.items():
            reset_ts = info.get("reset_ts", 0)
            if now < reset_ts:  # window still active — restore to in-memory state
                _rate_limit_global[source] = (
                    info["remaining"], info["limit"], reset_ts
                )
    except Exception:
        pass


def _save_rate_limit_cache() -> None:
    """Persist current _rate_limit_global to disk after every rate limit header update."""
    try:
        _RATE_LIMIT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            src: {"remaining": r, "limit": l, "reset_ts": ts}
            for src, (r, l, ts) in _rate_limit_global.items()
        }
        _RATE_LIMIT_CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


# Load persisted state on module import so the proactive gate is active from the
# first API call even if the app was restarted while rate-limited.
_load_rate_limit_cache()
