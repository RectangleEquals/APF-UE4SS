"""
Release data classes — ReleaseAuthor, ReleaseFile, RepoRelease.

Pure model: no network I/O, no caching logic.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


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
