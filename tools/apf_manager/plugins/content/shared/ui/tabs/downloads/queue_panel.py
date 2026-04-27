"""queue_panel.py — QueuePanelMixin: active download queue row + download logic."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel
from kivymd.uix.progressindicator import MDLinearProgressIndicator

from .....shared.ui.constants import COL_DIM

if TYPE_CHECKING:
    from .downloads_tab import _QueueItem


_CACHE_DIR = Path.home() / ".apf_manager" / "cache"
_BG_ITEM   = (0.13, 0.13, 0.13, 1)


class QueuePanelMixin:
    """Active download queue row builder and download logic for DownloadsTab."""

    def _queue_row(self, item: "_QueueItem") -> MDBoxLayout:
        from .....shared.ui.content_row import ContentRowWidget
        row = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=_BG_ITEM,
        )
        row.add_widget(ContentRowWidget(content=item.mod, row_index=0))

        status_colors = {
            "queued":      (0.5, 0.5, 0.5, 1),
            "downloading": (0.3, 0.7, 1.0, 1),
            "unpacking":   (0.7, 0.5, 1.0, 1),
            "done":        (0.3, 0.8, 0.4, 1),
            "error":       (1.0, 0.3, 0.3, 1),
        }
        status_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(24),
            padding=[dp(8), 0], spacing=dp(8),
        )
        status_row.add_widget(MDLabel(
            text=item.status.capitalize(),
            font_style="Label", role="small",
            size_hint=(1, 1), halign="left", valign="middle",
            theme_text_color="Custom",
            text_color=status_colors.get(item.status, COL_DIM),
        ))
        if item.status in ("queued", "downloading"):
            status_row.add_widget(MDButton(
                MDButtonText(text="Cancel"),
                style="text", size_hint=(None, None), size=(dp(72), dp(24)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, qi=item: self._cancel(qi),
            ))
        row.add_widget(status_row)

        if item.status == "downloading":
            bar = MDLinearProgressIndicator(size_hint=(1, None), height=dp(4))
            bar.value = item.progress
            row.add_widget(bar)

        if item.status == "error" and item.error_msg:
            row.add_widget(MDLabel(
                text=item.error_msg,
                font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
                padding=[dp(8), 0],
                theme_text_color="Custom", text_color=(1.0, 0.4, 0.4, 1),
            ))

        return row

    def _start_next_download(self) -> None:
        with self._queue_lock:
            pending = [q for q in self._queue if q.status == "queued"]
            active  = [q for q in self._queue if q.status == "downloading"]
        if active or not pending:
            return
        item = pending[0]
        with self._queue_lock:
            item.status = "downloading"
        threading.Thread(target=self._download_item_bg, args=(item,), daemon=True).start()
        Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)

    def _download_item_bg(self, item: "_QueueItem") -> None:
        try:
            from .....shared.data.content_types import (
                GithubReleaseBinary as _GRB,
                ExternalUrlBinary as _EUB,
                ManualBinary as _MB,
                TemplateDescriptor as _TPL,
                ModDescriptor as _MOD,
            )
            _mod = item.mod

            # Determine source repo info
            if isinstance(_mod, (_GRB, _TPL, _MOD)):
                _src = getattr(_mod, "source", None)
                owner = _src.repo.owner if _src else ""
                repo  = _src.repo.repo if _src else ""
            else:
                owner = repo = ""

            # Determine cache destination
            if isinstance(_mod, _GRB):
                tag  = _mod.source.tag if _mod.source else "unknown"
                dest = _CACHE_DIR / "_other" / f"{owner}+{repo}" / tag
            elif isinstance(_mod, (_EUB, _MB)):
                raise RuntimeError("Manual/external install — no automatic download available")
            elif isinstance(_mod, _TPL):
                dest = _CACHE_DIR / f"{owner}+{repo}" / _mod.template_path
            else:
                folder_name = (getattr(_mod, "folder_name", "") or
                               (_src.folder.split("/")[-1] if _src and _src.folder else "") or
                               getattr(_mod, "mod_id", ""))
                dest = _CACHE_DIR / f"{owner}+{repo}" / folder_name

            dest.mkdir(parents=True, exist_ok=True)
            _save_descriptor_cache(item, dest, self._game_id)

            from .......core.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH

            if isinstance(_mod, _GRB):
                import zipfile as _zipfile
                _opt_owner = _mod.source.repo.owner if _mod.source else ""
                _opt_repo  = _mod.source.repo.repo if _mod.source else ""
                _opt_tag   = _mod.source.tag if _mod.source else ""
                self._host.log(
                    f"[downloads] other-download: owner={_opt_owner!r} repo={_opt_repo!r} "
                    f"tag={_opt_tag!r} name={_mod.name!r}"
                )
                api = GitHubAPI(
                    repo_owner=_opt_owner, repo_name=_opt_repo,
                    token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
                    on_status=lambda lvl, msg: None,
                )
                selected_assets = [a for a in (_mod.assets or []) if getattr(a, "selected", False)]
                self._host.log(f"[downloads] selected_assets count={len(selected_assets)}")
                if not selected_assets:
                    raise RuntimeError("No assets selected for download")
                n = len(selected_assets)
                for idx, asset in enumerate(selected_assets):
                    asset_url  = getattr(asset, "url", "")
                    asset_name = getattr(asset, "name", asset_url.split("/")[-1])
                    dest_file  = dest / asset_name
                    self._host.log(f"[downloads] downloading asset {idx+1}/{n}: {asset_name!r}")
                    self._set_progress(item, idx / n * 0.1)
                    dl_ok = api.download_asset(
                        asset_url, dest_file,
                        progress_cb=lambda p, i=idx: self._set_progress(
                            item, (i + 0.1 + p * 0.9) / n
                        ),
                    )
                    self._host.log(
                        f"[downloads] download_asset returned {dl_ok!r} "
                        f"exists={dest_file.exists()} "
                        f"size={dest_file.stat().st_size if dest_file.exists() else 'N/A'}"
                    )
                    if dest_file.suffix.lower() == ".zip":
                        if not dest_file.exists() or dest_file.stat().st_size == 0:
                            raise ValueError(f"Downloaded file is empty or missing: {dest_file}")
                        try:
                            with _zipfile.ZipFile(dest_file) as zf:
                                bad = zf.testzip()
                                self._host.log(f"[downloads] zipfile.testzip() {asset_name!r} → {bad!r}")
                        except _zipfile.BadZipFile as zexc:
                            self._host.log(f"[downloads] BadZipFile {asset_name!r}: {zexc}")
                            dest_file.unlink(missing_ok=True)
                            raise ValueError(f"Downloaded file is not a valid zip: {asset_name}")
            elif isinstance(_mod, _TPL):
                _download_github_folder(owner, repo, _mod.template_path, dest,
                                        progress_cb=lambda p: self._set_progress(item, p))
            else:
                folder_path = (_src.folder if _src and _src.folder else folder_name)
                _download_github_folder(owner, repo, folder_path, dest,
                                        progress_cb=lambda p: self._set_progress(item, p))

            with self._queue_lock:
                item.status = "done"
                item.cache_path = dest
        except Exception as exc:
            with self._queue_lock:
                item.status = "error"
                item.error_msg = str(exc)

        Clock.schedule_once(lambda dt: self._on_item_done(item), 0)

    def _set_progress(self, item: "_QueueItem", progress: float) -> None:
        with self._queue_lock:
            item.progress = progress
        Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)

    def _on_item_done(self, item: "_QueueItem") -> None:
        self._scan_cache_and_rebuild()
        self._start_next_download()

    def _cancel(self, item: "_QueueItem") -> None:
        with self._queue_lock:
            if item.status == "queued":
                self._queue.remove(item)
        self._rebuild_ui()


# ---------------------------------------------------------------------------
# Module-level helpers (used by _download_item_bg and _save_descriptor_cache)
# ---------------------------------------------------------------------------

def _save_descriptor_cache(item, dest: Path, current_game_id: str) -> None:
    """Write the typed ContentDescriptor from the queue item to .apf_cache."""
    from .....shared.data.pipeline_state import ContentSerializer
    try:
        ContentSerializer().save_cache(dest, item.mod)
    except Exception:
        pass


# Registry metadata files that must never be downloaded into the mod cache.
_REGISTRY_META = frozenset({"ue4ss.json"})

# File extensions that must be written as raw bytes (not decoded as UTF-8 text).
_BINARY_EXTS = frozenset({".dll", ".pak", ".zip", ".exe", ".pdb", ".db", ".so", ".dylib"})


def _download_github_folder(
    owner: str, repo: str, path: str, dest: Path,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> None:
    """Recursively download a GitHub repo folder into dest.

    Uses GitHubAPI.list_contents() for directory traversal (auth, 1-hr cache,
    rate-limit tracking). Text files are written via GitHubAPI.fetch_text()
    (24-hr TTL caching, stale fallback). Binary files are downloaded directly
    via httpx since fetch_text only handles text.
    """
    from .......core.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH
    api = GitHubAPI(
        repo_owner=owner, repo_name=repo,
        token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
    )

    file_list: list[tuple[str, Path]] = []
    _collect_files(api, path, dest, file_list)

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


def _collect_files(api: "object", api_path: str, local_base: Path, out: list) -> None:
    """Recursively collect (download_url, dest_path) pairs for a GitHub repo subtree.

    Uses GitHubAPI.list_contents() so directory traversal goes through the
    shared auth/cache/rate-limit layer.

    K-8 Fix A: files named in _REGISTRY_META (e.g. 'ue4ss.json') are skipped.
    K-9 fix: subdirectory recursion passes the computed subdir path as local_base,
    preserving the full directory structure instead of flattening everything to root.
    """
    items = api.list_contents(api_path)  # type: ignore[attr-defined]
    for item in items:
        # K-8 Fix A: skip registry metadata files
        if item["type"] == "file" and item.get("name", "") in _REGISTRY_META:
            continue
        rel = (
            Path(item["path"]).relative_to(api_path)
            if api_path else Path(item["path"])
        )
        local_path = local_base / rel
        if item["type"] == "dir":
            local_path.mkdir(parents=True, exist_ok=True)
            # K-9: pass local_path (the subdir's computed destination) so that
            # nested files land under their correct parent directory, not at root.
            _collect_files(api, item["path"], local_path, out)
        elif item["type"] == "file":
            dl_url = item.get("download_url", "")
            if dl_url:
                out.append((dl_url, local_path))
