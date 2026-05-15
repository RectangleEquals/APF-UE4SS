"""DownloadService — background download logic for queued content items."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .....core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)

_CACHE_DIR = Path.home() / ".apf_manager" / "cache"

# Registry metadata files that must never be downloaded into the mod cache.
_REGISTRY_META = frozenset({"ue4ss.json"})

# File extensions written as raw bytes (not decoded as UTF-8 text).
_BINARY_EXTS = frozenset({".dll", ".pak", ".zip", ".exe", ".pdb", ".db", ".so", ".dylib"})


class DownloadService:
    """
    UI-free background download logic for queued content items.

    All methods are safe to call from a worker thread.

    Parameters
    ----------
    host : plugin host — must have a .log(msg) method
    """

    def __init__(self, host) -> None:
        self._host = host

    def download_item(
        self,
        item,
        game_id: str,
        on_progress: Optional[Callable[[float], None]] = None,
        on_done: Optional[Callable[[bool, str, Optional[Path]], None]] = None,
    ) -> None:
        """
        Download a single queue item synchronously (call from a worker thread).

        Calls on_progress(float 0..1) during download.
        Calls on_done(success, error_msg, cache_path) when finished.
        """
        cache_path: Optional[Path] = None
        try:
            from ...models.descriptors.types import (
                GithubReleaseBinary as _GRB,
                ExternalUrlBinary as _EUB,
                ManualBinary as _MB,
                TemplateDescriptor as _TPL,
                ModDescriptor as _MOD,
            )
            _mod = item.mod

            if isinstance(_mod, (_GRB, _TPL, _MOD)):
                _src = getattr(_mod, "source", None)
                owner = _src.repo.owner if _src else ""
                repo  = _src.repo.repo if _src else ""
            else:
                owner = repo = ""

            if isinstance(_mod, _GRB):
                tag  = _mod.source.tag if _mod.source else "unknown"
                dest = _CACHE_DIR / "_other" / f"{owner}+{repo}" / tag
            elif isinstance(_mod, (_EUB, _MB)):
                raise RuntimeError("Manual/external install — no automatic download available")
            elif isinstance(_mod, _TPL):
                dest = _CACHE_DIR / f"{owner}+{repo}" / _mod.template_path
            else:
                folder_name = (
                    getattr(_mod, "folder_name", "")
                    or (_src.folder.split("/")[-1] if _src and _src.folder else "")
                    or getattr(_mod, "mod_id", "")
                )
                dest = _CACHE_DIR / f"{owner}+{repo}" / folder_name

            dest.mkdir(parents=True, exist_ok=True)
            self.save_descriptor_cache(item, dest, game_id=game_id)

            from .....core.controllers.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH

            if isinstance(_mod, _GRB):
                import zipfile as _zipfile
                _opt_owner = _mod.source.repo.owner if _mod.source else ""
                _opt_repo  = _mod.source.repo.repo if _mod.source else ""
                _opt_tag   = _mod.source.tag if _mod.source else ""
                logger.info(
                    f"Downloading binary: owner={_opt_owner!r} repo={_opt_repo!r} "
                    f"tag={_opt_tag!r} name={_mod.name!r}"
                )
                api = GitHubAPI(
                    repo_owner=_opt_owner, repo_name=_opt_repo,
                    token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
                    on_status=lambda lvl, msg: None,
                )
                selected_assets = [a for a in (_mod.assets or []) if getattr(a, "selected", False)]
                logger.debug(f"Selected assets count: {len(selected_assets)}")
                if not selected_assets:
                    raise RuntimeError("No assets selected for download")
                n = len(selected_assets)
                for idx, asset in enumerate(selected_assets):
                    asset_url  = getattr(asset, "url", "")
                    asset_name = getattr(asset, "name", asset_url.split("/")[-1])
                    dest_file  = dest / asset_name
                    logger.info(f"Downloading asset {idx+1}/{n}: {asset_name!r}")
                    if on_progress:
                        on_progress(idx / n * 0.1)
                    dl_ok = api.download_asset(
                        asset_url, dest_file,
                        progress_cb=lambda p, i=idx: on_progress((i + 0.1 + p * 0.9) / n)
                        if on_progress else None,
                    )
                    logger.debug(
                        f"download_asset returned {dl_ok!r} "
                        f"exists={dest_file.exists()} "
                        f"size={dest_file.stat().st_size if dest_file.exists() else 'N/A'}"
                    )
                    if dest_file.suffix.lower() == ".zip":
                        if not dest_file.exists() or dest_file.stat().st_size == 0:
                            raise ValueError(f"Downloaded file is empty or missing: {dest_file}")
                        try:
                            with _zipfile.ZipFile(dest_file) as zf:
                                bad = zf.testzip()
                                logger.debug(f"zipfile.testzip() {asset_name!r} -> {bad!r}")
                        except _zipfile.BadZipFile as zexc:
                            logger.warning(f"BadZipFile {asset_name!r}: {zexc}")
                            dest_file.unlink(missing_ok=True)
                            raise ValueError(f"Downloaded file is not a valid zip: {asset_name}")

            elif isinstance(_mod, _TPL):
                download_github_folder(
                    owner, repo, _mod.template_path, dest,
                    progress_cb=on_progress,
                )
            else:
                folder_path = _src.folder if _src and _src.folder else folder_name
                download_github_folder(
                    owner, repo, folder_path, dest,
                    progress_cb=on_progress,
                )

            cache_path = dest
            if on_done:
                on_done(True, "", cache_path)

        except Exception as exc:
            if on_done:
                on_done(False, str(exc), None)

    def save_descriptor_cache(self, item, dest: Path, game_id: str = "") -> None:
        """Persist the typed ContentDescriptor from a queue item to .apf_cache."""
        from ...models.state.pipeline import ContentSerializer
        try:
            if game_id and not item.mod.game_id:
                item.mod.game_id = game_id
            ContentSerializer().save_cache(dest, item.mod)
        except Exception as exc:
            logger.warning(f"Failed to save descriptor cache at {dest}: {exc}")


# ---------------------------------------------------------------------------
# Module-level helpers (also importable for testing)
# ---------------------------------------------------------------------------

def download_github_folder(
    owner: str,
    repo: str,
    path: str,
    dest: Path,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> None:
    """
    Recursively download a GitHub repo folder into dest.

    Uses GitHubAPI.list_contents() for directory traversal (auth, 1-hr cache,
    rate-limit tracking). Text files written via GitHubAPI.fetch_text()
    (24-hr TTL caching, stale fallback). Binary files downloaded directly via
    requests since fetch_text only handles text.
    """
    from .....core.controllers.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH
    api = GitHubAPI(
        repo_owner=owner, repo_name=repo,
        token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
    )

    file_list: list[tuple[str, Path]] = []
    collect_files(api, path, dest, file_list)

    total = len(file_list)
    for idx, (url, dest_file) in enumerate(file_list):
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        if dest_file.suffix.lower() in _BINARY_EXTS:
            import requests
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            dest_file.write_bytes(r.content)
        else:
            content = api.fetch_text(url)
            dest_file.write_text(content, encoding="utf-8")
        if progress_cb and total:
            progress_cb((idx + 1) / total)


def collect_files(api, api_path: str, local_base: Path, out: list) -> None:
    """
    Recursively collect (download_url, dest_path) pairs for a GitHub repo subtree.

    Uses GitHubAPI.list_contents() so directory traversal goes through the
    shared auth/cache/rate-limit layer.

    K-8 Fix A: files named in _REGISTRY_META (e.g. 'ue4ss.json') are skipped.
    K-9 fix: subdirectory recursion passes the computed subdir path as local_base,
    preserving the full directory structure instead of flattening everything to root.
    """
    items = api.list_contents(api_path)
    for item in items:
        if item["type"] == "file" and item.get("name", "") in _REGISTRY_META:
            continue
        rel = (
            Path(item["path"]).relative_to(api_path)
            if api_path else Path(item["path"])
        )
        local_path = local_base / rel
        if item["type"] == "dir":
            local_path.mkdir(parents=True, exist_ok=True)
            collect_files(api, item["path"], local_path, out)
        elif item["type"] == "file":
            dl_url = item.get("download_url", "")
            if dl_url:
                out.append((dl_url, local_path))
