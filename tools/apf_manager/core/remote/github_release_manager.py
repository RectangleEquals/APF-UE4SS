"""
GitHubReleaseManager — typed release data layer.

Provides ReleaseAuthor, ReleaseFile, and RepoRelease dataclasses (ported from
the standalone GitHubReleasesTool/github_release_fetcher.py) plus a
GitHubReleaseManager class that fetches, caches, and filters release data for
a single GitHub repo.

All network calls use self._api.client (auth already resolved by GitHubAPI)
and track rate-limit state via self._api._update_rate_limit() so that auth,
rate-limiting, and caching remain centralised in GitHubAPI.
"""

from __future__ import annotations

import json
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

from githubkit.exception import RequestFailed, RateLimitExceeded, RequestTimeout
import httpx as _httpx

from .github_cache import TTL_RELEASES

if TYPE_CHECKING:
    from .github_api import GitHubAPI


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReleaseAuthor:
    """Minimal author / actor information attached to a release."""
    login: str
    id: int
    avatar_url: str
    html_url: str
    type: str   # "User", "Bot", etc.

    @classmethod
    def from_model(cls, author) -> "ReleaseAuthor":
        return cls(
            login=author.login,
            id=author.id,
            avatar_url=str(author.avatar_url),
            html_url=str(author.html_url),
            type=author.type,
        )


@dataclass
class ReleaseFile:
    """A single downloadable asset attached to a release."""
    id: int
    name: str
    label: Optional[str]
    content_type: str
    size_bytes: int
    download_count: int
    browser_download_url: str
    state: str   # "uploaded" | "open"
    created_at: datetime
    updated_at: datetime
    uploader_login: Optional[str]

    @classmethod
    def from_asset(cls, asset) -> "ReleaseFile":
        return cls(
            id=asset.id,
            name=asset.name,
            label=asset.label if asset.label else None,
            content_type=asset.content_type,
            size_bytes=asset.size,
            download_count=asset.download_count,
            browser_download_url=str(asset.browser_download_url),
            state=asset.state,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
            uploader_login=asset.uploader.login if asset.uploader else None,
        )

    @property
    def size_human(self) -> str:
        """Human-readable file size (B / KB / MB / GB)."""
        n = self.size_bytes
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"


@dataclass
class RepoRelease:
    """All metadata for a single GitHub release."""

    # ── Identity ──────────────────────────────────────────────────────────────
    id: int
    node_id: str
    tag_name: str
    target_commitish: str
    name: Optional[str]

    # ── Flags ─────────────────────────────────────────────────────────────────
    draft: bool
    prerelease: bool

    # ── Content ───────────────────────────────────────────────────────────────
    body: Optional[str]

    # ── URLs ──────────────────────────────────────────────────────────────────
    html_url: str
    url: str
    assets_url: str
    upload_url: str
    tarball_url: Optional[str]
    zipball_url: Optional[str]

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: datetime
    published_at: Optional[datetime]

    # ── Author ────────────────────────────────────────────────────────────────
    author: ReleaseAuthor

    # ── Assets ────────────────────────────────────────────────────────────────
    assets: list[ReleaseFile] = field(default_factory=list)

    # ── Reactions (summary counts; present on newer API responses) ────────────
    reactions: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_release(cls, release) -> "RepoRelease":
        assets = [ReleaseFile.from_asset(a) for a in (release.assets or [])]

        reactions: dict[str, int] = {}
        if release.reactions:
            r = release.reactions
            reactions = {
                "+1":       r.plus_one,
                "-1":       r.minus_one,
                "laugh":    r.laugh,
                "hooray":   r.hooray,
                "confused": r.confused,
                "heart":    r.heart,
                "rocket":   r.rocket,
                "eyes":     r.eyes,
                "total":    r.total_count,
            }

        return cls(
            id=release.id,
            node_id=release.node_id,
            tag_name=release.tag_name,
            target_commitish=release.target_commitish,
            name=release.name if release.name else None,
            draft=release.draft,
            prerelease=release.prerelease,
            body=release.body if release.body else None,
            html_url=str(release.html_url),
            url=str(release.url),
            assets_url=str(release.assets_url),
            upload_url=release.upload_url,
            tarball_url=str(release.tarball_url) if release.tarball_url else None,
            zipball_url=str(release.zipball_url) if release.zipball_url else None,
            created_at=release.created_at,
            published_at=release.published_at,
            author=ReleaseAuthor.from_model(release.author),
            assets=assets,
            reactions=reactions,
        )

    @property
    def total_download_count(self) -> int:
        """Sum of download counts across all assets."""
        return sum(a.download_count for a in self.assets)

    @property
    def total_size_bytes(self) -> int:
        """Combined size of all assets in bytes."""
        return sum(a.size_bytes for a in self.assets)

    @property
    def changelog_preview(self) -> str:
        """First 300 characters of the release body, or empty string."""
        chars = 300
        if not self.body:
            return ""
        return self.body[:chars] + ("…" if len(self.body) > chars else "")

    def __repr__(self) -> str:
        kind = "pre-release" if self.prerelease else ("draft" if self.draft else "release")
        return (
            f"<RepoRelease tag={self.tag_name!r} "
            f"kind={kind} "
            f"assets={len(self.assets)} "
            f"published={self.published_at}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Manager
# ─────────────────────────────────────────────────────────────────────────────

class GitHubReleaseManager:
    """
    Fetch, cache, and filter GitHub release data for a single repo.

    Never constructs its own GitHub() client. Uses api.client (auth already
    resolved by GitHubAPI) and api._update_rate_limit() for tracking so that
    rate-limit state, auth, and caching remain centralised in GitHubAPI.
    """

    # In-memory TTL matching disk cache TTL_RELEASES (15 min)
    _TYPED_TTL = TTL_RELEASES

    def __init__(self, api: "GitHubAPI") -> None:
        self._api = api
        # In-memory cache for typed objects (avoids JSON serialisation round-trip)
        self._all_releases: Optional[list[RepoRelease]] = None
        self._all_releases_time: float = 0.0

    # ── Sync fetch ────────────────────────────────────────────────────────────

    def fetch_all(self, *, per_page: int = 100,
                  force_refresh: bool = False) -> list[RepoRelease]:
        """
        Return every release for the repo, newest-first (up to per_page).

        Results are cached in memory for TTL_RELEASES seconds.
        Falls back to the last successful result on network/auth failure.
        """
        now = time.time()
        if (
            not force_refresh
            and self._all_releases is not None
            and (now - self._all_releases_time) < self._TYPED_TTL
        ):
            return list(self._all_releases)

        if self._api._check_rate_limit():
            return list(self._all_releases) if self._all_releases is not None else []

        try:
            resp = self._api.client.rest.repos.list_releases(
                self._api._owner, self._api._repo, per_page=min(per_page, 100)
            )
            self._api._update_rate_limit(resp.headers)
            releases = [RepoRelease.from_release(r) for r in (resp.parsed_data or [])]
            self._all_releases = releases
            self._all_releases_time = time.time()
            return list(releases)

        except RateLimitExceeded as exc:
            self._api._handle_rate_limit(exc, "releases/list/all", None)
            return list(self._all_releases) if self._all_releases is not None else []

        except RequestFailed as exc:
            self._api._handle_request_failed(exc, "releases/list/all", None)
            return list(self._all_releases) if self._all_releases is not None else []

        except (RequestTimeout, _httpx.ConnectError, _httpx.TimeoutException):
            return list(self._all_releases) if self._all_releases is not None else []

        except Exception as exc:
            self._api._on_status("warn", f"GitHub error fetching releases: {exc}")
            return list(self._all_releases) if self._all_releases is not None else []

    def fetch_latest(self, force_refresh: bool = False) -> Optional[RepoRelease]:
        """Return the latest stable release (no draft, no pre-release), or None."""
        if self._api._check_rate_limit():
            # Try to get from in-memory list
            if self._all_releases:
                return next((r for r in self._all_releases
                             if not r.draft and not r.prerelease), None)
            return None

        try:
            resp = self._api.client.rest.repos.get_latest_release(
                self._api._owner, self._api._repo
            )
            self._api._update_rate_limit(resp.headers)
            return RepoRelease.from_release(resp.parsed_data)

        except RateLimitExceeded as exc:
            self._api._handle_rate_limit(exc, "releases/latest", None)
            if self._all_releases:
                return next((r for r in self._all_releases
                             if not r.draft and not r.prerelease), None)
            return None

        except RequestFailed as exc:
            self._api._handle_request_failed(exc, "releases/latest", None)
            if self._all_releases:
                return next((r for r in self._all_releases
                             if not r.draft and not r.prerelease), None)
            return None

        except (RequestTimeout, _httpx.ConnectError, _httpx.TimeoutException):
            if self._all_releases:
                return next((r for r in self._all_releases
                             if not r.draft and not r.prerelease), None)
            return None

        except Exception as exc:
            self._api._on_status("warn", f"GitHub error fetching latest release: {exc}")
            return None

    def fetch_latest_prerelease(self,
                                force_refresh: bool = False) -> Optional[RepoRelease]:
        """Return the latest pre-release (draft=False, prerelease=True), or None."""
        all_releases = self.fetch_all(force_refresh=force_refresh)
        return next((r for r in all_releases if r.prerelease and not r.draft), None)

    def fetch_by_tag(self, tag: str,
                     force_refresh: bool = False) -> Optional[RepoRelease]:
        """Return the release with the given tag, or None if not found."""
        all_releases = self.fetch_all(force_refresh=force_refresh)
        return next((r for r in all_releases if r.tag_name == tag), None)

    def fetch_updates(
        self, *,
        since_date: Optional[datetime] = None,
        since_tag: Optional[str] = None,
        include_prereleases: bool = True,
        force_refresh: bool = False,
    ) -> list[RepoRelease]:
        """
        Return all releases newer than the given reference point, newest-first.

        Exactly one of since_date or since_tag must be provided.
        """
        if since_date is None and since_tag is None:
            raise ValueError("Provide either since_date or since_tag.")
        if since_date is not None and since_tag is not None:
            raise ValueError("Provide either since_date or since_tag, not both.")

        all_releases = self.fetch_all(force_refresh=force_refresh)

        cutoff: Optional[datetime] = since_date

        if since_tag is not None:
            for r in all_releases:
                if r.tag_name == since_tag:
                    cutoff = r.published_at
                    break
            if cutoff is None:
                return []

        if cutoff is not None and cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)

        newer: list[RepoRelease] = []
        for release in all_releases:
            if not include_prereleases and release.prerelease:
                continue
            if release.draft:
                continue
            pub = release.published_at
            if pub is None:
                continue
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            if cutoff is None or pub > cutoff:
                newer.append(release)
        return newer

    # ── Dict-based shims (used by GitHubAPI delegate methods in Phase 2) ─────

    def get_latest_release_dict(self,
                                force_refresh: bool = False) -> Optional[dict]:
        """Return latest stable release as a legacy dict, or None on failure."""
        if self._api._check_rate_limit():
            return self._api._load_stale_json("releases/latest")

        cache_key = "releases/latest"
        if not force_refresh:
            cached = self._api._cache.get(cache_key)
            if cached is not None:
                try:
                    return json.loads(cached)
                except Exception:
                    pass

        try:
            resp = self._api.client.rest.repos.get_latest_release(
                self._api._owner, self._api._repo
            )
            self._api._update_rate_limit(resp.headers)
            release = resp.parsed_data
            data = self._raw_to_dict(release)
            self._api._cache.set(cache_key, json.dumps(data), TTL_RELEASES)
            return data

        except RateLimitExceeded as exc:
            return self._api._handle_rate_limit(exc, cache_key, fallback=None)

        except RequestFailed as exc:
            return self._api._handle_request_failed(exc, cache_key, fallback=None)

        except (RequestTimeout, _httpx.ConnectError, _httpx.TimeoutException) as exc:
            stale = self._api._cache.get_stale(cache_key)
            if stale is not None:
                self._api._on_status("warn", f"GitHub unreachable — using cached release info ({exc})")
                try:
                    return json.loads(stale)
                except Exception:
                    pass
            self._api._on_status("error", f"GitHub unreachable and no cached release info ({exc})")
            return None

        except Exception as exc:
            self._api._on_status("warn", f"Unexpected error fetching release info: {exc}")
            return self._api._load_stale_json(cache_key)

    def list_releases_dict(
        self,
        tag_prefix: str = "",
        per_page: int = 30,
        force_refresh: bool = False,
    ) -> list[dict]:
        """Return release metadata dicts, optionally filtered by tag prefix."""
        cache_key = f"releases/list/{tag_prefix or 'all'}"

        if self._api._check_rate_limit():
            stale = self._api._cache.get_stale(cache_key)
            try:
                return json.loads(stale) if stale else []
            except Exception:
                return []

        if not force_refresh:
            cached = self._api._cache.get(cache_key)
            if cached is not None:
                try:
                    return json.loads(cached)
                except Exception:
                    pass

        try:
            resp = self._api.client.rest.repos.list_releases(
                self._api._owner, self._api._repo, per_page=per_page
            )
            self._api._update_rate_limit(resp.headers)
            releases = resp.parsed_data or []
            results = []
            for release in releases:
                tag = release.tag_name or ""
                if tag_prefix and not tag.startswith(tag_prefix):
                    continue
                results.append(self._raw_to_dict(release))
            self._api._cache.set(cache_key, json.dumps(results), TTL_RELEASES)
            return results

        except RateLimitExceeded as exc:
            return self._api._handle_rate_limit(exc, cache_key, fallback=[])

        except RequestFailed as exc:
            return self._api._handle_request_failed(exc, cache_key, fallback=[]) or []

        except Exception as exc:
            self._api._on_status("warn", f"Unexpected error listing releases: {exc}")
            stale = self._api._cache.get_stale(cache_key)
            try:
                return json.loads(stale) if stale else []
            except Exception:
                return []

    # ── Downloads ─────────────────────────────────────────────────────────────

    def download_asset(
        self,
        asset_url: str,
        dest: Path,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """Download a release asset to dest. Returns True on success."""
        try:
            headers = self._api._cdn_headers()
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

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _raw_to_dict(release) -> dict:
        """Convert a raw githubkit Release model to the legacy dict format."""
        return {
            "tag_name":     release.tag_name,
            "published_at": str(release.published_at),
            "body":         release.body or "",
            "assets": [
                {
                    "name":                 a.name,
                    "browser_download_url": str(a.browser_download_url),
                    "size":                 a.size,
                }
                for a in (release.assets or [])
            ],
        }

    @staticmethod
    def _release_to_dict(release: RepoRelease) -> dict:
        """Convert a typed RepoRelease to the legacy dict format."""
        return {
            "tag_name":     release.tag_name,
            "published_at": str(release.published_at),
            "body":         release.body or "",
            "assets": [
                {
                    "name":                 a.name,
                    "browser_download_url": a.browser_download_url,
                    "size":                 a.size_bytes,
                }
                for a in release.assets
            ],
        }
