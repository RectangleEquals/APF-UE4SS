"""queue_panel.py — QueuePanelMixin: active download queue row + download logic."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.progressindicator import MDLinearProgressIndicator

from .....shared.ui.constants import COL_CPP, COL_BP, COL_DIM

if TYPE_CHECKING:
    from .downloads_tab import _QueueItem


_CACHE_DIR = Path.home() / ".apf_manager" / "cache"
_BG_ITEM   = (0.13, 0.13, 0.13, 1)


class QueuePanelMixin:
    """Active download queue row builder and download logic for DownloadsTab."""

    def _queue_row(self, item: "_QueueItem") -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=_BG_ITEM, padding=[dp(8), dp(6)], spacing=dp(4),
        )

        top = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8),
        )
        if "cpp" in item.components:
            top.add_widget(MDIcon(
                icon="code-braces", size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=COL_CPP,
            ))
        if "blueprint" in item.components:
            top.add_widget(MDIcon(
                icon="blueprint", size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=COL_BP,
            ))
        top.add_widget(MDLabel(
            text=item.display_name, font_style="Body",
            size_hint=(1, 1), halign="left", valign="middle",
        ))
        status_colors = {
            "queued":      (0.5, 0.5, 0.5, 1),
            "downloading": (0.3, 0.7, 1.0, 1),
            "unpacking":   (0.7, 0.5, 1.0, 1),
            "done":        (0.3, 0.8, 0.4, 1),
            "error":       (1.0, 0.3, 0.3, 1),
        }
        top.add_widget(MDLabel(
            text=item.status.capitalize(),
            font_style="Label", role="small",
            size_hint=(None, 1), width=dp(90),
            halign="right", valign="middle",
            theme_text_color="Custom",
            text_color=status_colors.get(item.status, COL_DIM),
        ))
        if item.status in ("queued", "downloading"):
            top.add_widget(MDButton(
                MDButtonText(text="Cancel"),
                style="text", size_hint=(None, None), size=(dp(72), dp(28)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, qi=item: self._cancel(qi),
            ))
        row.add_widget(top)

        if item.status == "downloading":
            bar = MDLinearProgressIndicator(
                size_hint=(1, None), height=dp(4),
            )
            bar.value = item.progress
            row.add_widget(bar)

        if item.status == "error" and item.error_msg:
            row.add_widget(MDLabel(
                text=item.error_msg,
                font_style="Label", role="small",
                size_hint_y=None, height=dp(16),
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
            from .....shared.data.content_types import GithubReleaseBinary as _GRB

            _mod = item.mod
            if isinstance(_mod, _GRB) and _mod.source:
                owner = _mod.source.repo.owner
                repo  = _mod.source.repo.repo
            else:
                owner = getattr(_mod, "owner", "")
                repo  = getattr(_mod, "repo",  "")
            folder = getattr(_mod, "folder", getattr(_mod, "mod_id", ""))

            if item.category == "template":
                path = getattr(_mod, "path", folder)
                dest = _CACHE_DIR / f"{owner}+{repo}" / path
            elif item.category == "other":
                if isinstance(_mod, _GRB) and _mod.source:
                    ue4ss_owner = _mod.source.repo.owner
                    ue4ss_repo  = _mod.source.repo.repo
                    tag         = _mod.source.tag or "unknown"
                else:
                    ue4ss_owner = getattr(_mod, "owner", "")
                    ue4ss_repo  = getattr(_mod, "repo", "")
                    tag         = getattr(_mod, "tag", "unknown")
                dest = _CACHE_DIR / "_other" / f"{ue4ss_owner}+{ue4ss_repo}" / tag
            else:
                dest = _CACHE_DIR / f"{owner}+{repo}" / folder

            dest.mkdir(parents=True, exist_ok=True)

            _save_descriptor_cache(item, dest, self._game_id)

            from .......core.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH
            token = _BUNDLED_TOKEN_PATH.read_text().strip() \
                if _BUNDLED_TOKEN_PATH.exists() else ""

            if item.category == "other":
                import zipfile as _zipfile
                opt = item.mod
                if isinstance(opt, _GRB):
                    opt_type     = "github_release"
                    _opt_owner   = opt.source.repo.owner if opt.source else ""
                    _opt_repo    = opt.source.repo.repo if opt.source else ""
                    _opt_tag     = opt.source.tag if opt.source else ""
                else:
                    opt_type   = getattr(opt, "type", "manual")
                    _opt_owner = getattr(opt, "owner", "")
                    _opt_repo  = getattr(opt, "repo", "")
                    _opt_tag   = getattr(opt, "tag", "")
                self._host.log(
                    f"[downloads] other-download: opt_type={opt_type!r} "
                    f"owner={_opt_owner!r} repo={_opt_repo!r} "
                    f"tag={_opt_tag!r} name={getattr(opt,'name','')!r}"
                )
                if opt_type == "github_release":
                    api = GitHubAPI(
                        repo_owner=_opt_owner,
                        repo_name=_opt_repo,
                        token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
                        on_status=lambda lvl, msg: None,
                    )
                    _raw_assets = opt.assets if isinstance(opt, _GRB) else (getattr(opt, "assets", []) or [])
                    selected_assets = [a for a in _raw_assets if getattr(a, "selected", False)]
                    if not selected_assets:
                        direct_url = "" if isinstance(opt, _GRB) else getattr(opt, "url", "")
                        if direct_url:
                            from .....shared.data.content_base import ContentAsset as _CA
                            _fname = direct_url.split("/")[-1].split("?")[0] or f"{_opt_tag or 'release'}.zip"
                            selected_assets = [_CA(name=_fname, url=direct_url)]
                    self._host.log(f"[downloads] selected_assets count={len(selected_assets)}")
                    if not selected_assets:
                        raise RuntimeError("No assets selected for download")
                    n = len(selected_assets)
                    for idx, asset in enumerate(selected_assets):
                        asset_url = getattr(asset, "url", "")
                        asset_name = getattr(asset, "name", asset_url.split("/")[-1])
                        dest_file = dest / asset_name
                        self._host.log(f"[downloads] downloading asset {idx+1}/{n}: {asset_name!r} url={asset_url!r}")
                        self._set_progress(item, idx / n * 0.1)
                        dl_ok = api.download_asset(
                            asset_url, dest_file,
                            progress_cb=lambda p, i=idx: self._set_progress(
                                item, (i + 0.1 + p * 0.9) / n
                            ),
                        )
                        self._host.log(
                            f"[downloads] download_asset returned {dl_ok!r} "
                            f"dest_file={dest_file} exists={dest_file.exists()} "
                            f"size={dest_file.stat().st_size if dest_file.exists() else 'N/A'}"
                        )
                        if dest_file.suffix.lower() == ".zip":
                            if not dest_file.exists() or dest_file.stat().st_size == 0:
                                raise ValueError(f"Downloaded file is empty or missing: {dest_file}")
                            try:
                                with _zipfile.ZipFile(dest_file) as zf:
                                    bad = zf.testzip()
                                    self._host.log(f"[downloads] zipfile.testzip() {asset_name!r} returned {bad!r} (None=OK)")
                            except _zipfile.BadZipFile as zexc:
                                self._host.log(f"[downloads] BadZipFile {asset_name!r}: {zexc}")
                                dest_file.unlink(missing_ok=True)
                                raise ValueError(f"Downloaded file is not a valid zip: {asset_name}")
                elif opt_type == "external_url":
                    raise RuntimeError("External URL options require manual download — open in browser")
                else:
                    raise RuntimeError("Manual install required — no automatic download available")
            elif item.category == "template":
                template_path = getattr(item.mod, "path", folder)
                _download_github_folder(owner, repo, template_path, dest, token,
                                        progress_cb=lambda p: self._set_progress(item, p))
            else:
                _download_github_folder(owner, repo, folder, dest, token,
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
    """Build a typed ContentDescriptor from a queue item and write .apf_cache."""
    from .....shared.data.pipeline_state import ContentSerializer
    from .....shared.data.content_base import GitHubRepo, RegistrySource, ReleaseSource, ModComponents, DocInfo
    from .....shared.data.content_types import (
        APModDescriptor, FrameworkModDescriptor, ThirdPartyModDescriptor,
        TemplateDescriptor, GithubReleaseBinary,
    )
    try:
        mod = item.mod
        if item.category == "other":
            if isinstance(mod, GithubReleaseBinary):
                ContentSerializer().save_cache(dest, mod)
                return
            _install_type = getattr(mod, "install_type", "ue4ss")
            _reg_owner = getattr(mod, "registry_owner", "")
            game_id = "" if (_install_type == "framework_binary" or not _reg_owner) else current_game_id
            source = ReleaseSource(
                repo=GitHubRepo(owner=getattr(mod, "owner", ""), repo=getattr(mod, "repo", "")),
                tag=getattr(mod, "tag", ""),
                published_at=getattr(mod, "published_at", ""),
                changelog=getattr(mod, "changelog", ""),
                is_prerelease=getattr(mod, "prerelease", False),
            )
            descriptor = GithubReleaseBinary(
                name=getattr(mod, "name", ""),
                version=getattr(mod, "tag", ""),
                game_id=game_id,
                install_type=_install_type,
                source=source,
            )
        elif item.category == "template":
            game_id = getattr(mod, "game_id", "") or current_game_id
            source = RegistrySource(
                repo=GitHubRepo(owner=getattr(mod, "owner", ""), repo=getattr(mod, "repo", "")),
                folder=getattr(mod, "path", ""),
            )
            descriptor = TemplateDescriptor(
                name=(getattr(mod, "path", "") or "").split("/")[-1],
                game_id=game_id,
                template_path=getattr(mod, "path", ""),
                source=source,
            )
        else:
            _mod_id = getattr(mod, "mod_id", "")
            _id_parts = _mod_id.split(".")
            game_id = (
                _id_parts[1] if len(_id_parts) >= 2 and _id_parts[1]
                else getattr(mod, "game_id", "") or current_game_id
            )
            source = RegistrySource(
                repo=GitHubRepo(owner=getattr(mod, "owner", ""), repo=getattr(mod, "repo", "")),
                registry_url=getattr(getattr(mod, "registry", None), "url", ""),
                folder=getattr(mod, "folder", ""),
            )
            components = ModComponents.from_lists(
                getattr(mod, "components", ["lua"]),
                getattr(mod, "bp_pak_files", []),
            )
            docs = DocInfo(readme_url=getattr(mod, "readme_url", ""))
            if _mod_id:
                from .....utils.registry.resolver import _is_framework_mod_id
                cls = FrameworkModDescriptor if _is_framework_mod_id(_mod_id) else APModDescriptor
                descriptor = cls(
                    name=getattr(mod, "name", ""),
                    version=getattr(mod, "version", ""),
                    game_id=game_id,
                    folder_name=(getattr(mod, "folder", "") or "").split("/")[-1],
                    description=getattr(mod, "description", ""),
                    mod_id=_mod_id,
                    source=source, components=components, docs=docs,
                )
            else:
                descriptor = ThirdPartyModDescriptor(
                    name=getattr(mod, "name", ""),
                    version=getattr(mod, "version", ""),
                    game_id=game_id,
                    folder_name=(getattr(mod, "folder", "") or "").split("/")[-1],
                    description=getattr(mod, "description", ""),
                    source=source, components=components, docs=docs,
                )
        ContentSerializer().save_cache(dest, descriptor)
    except Exception:
        pass


def _download_github_folder(
    owner: str, repo: str, path: str, dest: Path,
    token: str = "",
    progress_cb: Optional[Callable[[float], None]] = None,
) -> None:
    """Recursively download a GitHub repo folder into dest using the Contents API."""
    import requests

    headers: dict = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    file_list: list[tuple[str, Path]] = []
    _collect_files(owner, repo, path, dest, headers, file_list)

    total = len(file_list)
    for idx, (url, dest_file) in enumerate(file_list):
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, headers=headers, timeout=60)
        r.raise_for_status()
        dest_file.write_bytes(r.content)
        if progress_cb and total:
            progress_cb((idx + 1) / total)


def _collect_files(
    owner: str, repo: str, api_path: str, local_base: Path,
    headers: dict, out: list,
) -> None:
    import requests

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{api_path}"
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    items = r.json()
    if isinstance(items, dict):
        items = [items]

    for item in items:
        rel = Path(item["path"]).relative_to(api_path) if api_path else Path(item["path"])
        local_path = local_base / rel
        if item["type"] == "dir":
            local_path.mkdir(parents=True, exist_ok=True)
            _collect_files(owner, repo, item["path"], local_base, headers, out)
        elif item["type"] == "file":
            dl_url = item.get("download_url", "")
            if dl_url:
                out.append((dl_url, local_path))
