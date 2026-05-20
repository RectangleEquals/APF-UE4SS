"""
Tab 3 — Downloads

Download queue and downloaded content cache.
Unit of download = one mod package (all components of one <ModName>/ subfolder).

Sections (top → bottom):
  - APF Updates  (teal, above queue — only shown when framework update available)
  - Queue        (active + queued items with per-item progress bars)
  - Cached       (downloaded packages ready to install)

Cache storage: ~/.apf_manager/cache/<owner>+<repo>/<folder>/
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

from ...models.descriptors.base import ContentDescriptor

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.progressindicator import MDLinearProgressIndicator

from .....core.controllers.logging.manager import APFLogManager
from .....core.views.widgets.tip_icon_button import TipIconButton

logger = APFLogManager.get_logger(__name__)
from ..chrome.constants import COL_DIM
from ..chrome.section_header import make_section_header
from ..panels.queue_panel import QueuePanelMixin
from ...controllers.download.service import _CACHE_DIR
from ..panels.cache_panel import CachePanelMixin

if TYPE_CHECKING:
    from .....core.models.ue.result import DetectionResult


_BG_SECTION   = (0.10, 0.12, 0.15, 1)
_BG_ITEM      = (0.13, 0.13, 0.13, 1)
_BG_UPDATES   = (0.08, 0.16, 0.18, 1)
_COL_TEAL     = (0.2, 0.8, 0.8, 1)
_COL_FW       = (0.2, 0.7, 0.9, 1)


# ---------------------------------------------------------------------------
# Queue item state
# ---------------------------------------------------------------------------

@dataclass
class _QueueItem:
    mod: ContentDescriptor
    status: str = "queued"       # queued | downloading | unpacking | done | error
    progress: float = 0.0        # 0.0 – 1.0
    error_msg: str = ""
    cache_path: Optional[Path] = None
    game_id: str = ""            # game this item was queued for; "" = any game
    _start_time: float = 0.0     # monotonic timestamp when download thread started

    @property
    def category(self) -> str:
        from ...models.descriptors.types import TemplateDescriptor as _TPL, BinaryDescriptor as _BD
        if isinstance(self.mod, _TPL):
            return "template"
        if isinstance(self.mod, _BD):
            return "other"
        return "mod"

    @property
    def key(self) -> str:
        from ...models.descriptors.types import GithubReleaseBinary as _GRB, TemplateDescriptor as _TPL
        mod = self.mod
        if isinstance(mod, _TPL):
            _src = mod.source
            owner = _src.repo.owner if _src else ""
            repo  = _src.repo.repo if _src else ""
            return f"tmpl:{owner}+{repo}/{mod.template_path}"
        if isinstance(mod, _GRB):
            _hash = mod.tags.content_hash if mod.tags else ""
            _src = mod.source
            return (f"other:{_hash}" if _hash else
                    f"other:{_src.repo.owner if _src else ''}+{_src.repo.repo if _src else ''}/{_src.tag if _src else mod.name}")
        _src = getattr(mod, "source", None)
        owner = _src.repo.owner if _src else ""
        repo  = _src.repo.repo if _src else ""
        folder = getattr(mod, "folder_name", "") or (
            _src.folder.split("/")[-1] if _src and _src.folder else getattr(mod, "mod_id", "")
        )
        return f"{owner}+{repo}/{folder}"

    @property
    def display_name(self) -> str:
        return self.mod.name or self.key

    @property
    def components(self) -> list:
        from ...models.descriptors.types import ModDescriptor as _MD
        if isinstance(self.mod, _MD) and self.mod.components:
            return self.mod.components.types
        return []


# ---------------------------------------------------------------------------
# Cached item (on-disk)
# ---------------------------------------------------------------------------

class _CacheItem:
    """A downloaded content item sitting in the local cache."""

    def __init__(self, cache_path: Path, content: ContentDescriptor):
        self.cache_path = cache_path
        self.content = content

    @property
    def category(self) -> str:
        ct = self.content.content_type
        if ct == "template":
            return "template"
        if ct in ("github_release_binary", "external_url_binary", "manual_binary"):
            return "other"
        return "mod"

    @property
    def display_name(self) -> str:
        return self.content.name or self.content.content_type or "Unknown"

    @property
    def version(self) -> str:
        return self.content.version or ""

    @property
    def game_name(self) -> str:
        return self.content.game_id or ""

    @property
    def install_type(self) -> str:
        return getattr(self.content, "install_type", "") or ""

    @property
    def folder_name(self) -> str:
        from ...models.descriptors.types import ModDescriptor as _MD
        if isinstance(self.content, _MD):
            return self.content.folder_name or ""
        _src = getattr(self.content, "source", None)
        if _src and _src.folder:
            return _src.folder.split("/")[-1]
        return self.content.name or ""

    @property
    def owner(self) -> str:
        _src = getattr(self.content, "source", None)
        if _src and _src.repo:
            return _src.repo.owner
        return ""

    @property
    def repo(self) -> str:
        _src = getattr(self.content, "source", None)
        if _src and _src.repo:
            return _src.repo.repo
        return ""

    @property
    def components(self) -> list:
        from ...models.descriptors.types import ModDescriptor as _MD
        if isinstance(self.content, _MD) and self.content.components:
            return self.content.components.types
        return []

    @property
    def bp_pak_files(self) -> list:
        from ...models.descriptors.types import ModDescriptor as _MD
        if isinstance(self.content, _MD) and self.content.components:
            return self.content.components.bp_pak_files
        return []

    @property
    def size_mb(self) -> float:
        try:
            total = sum(f.stat().st_size for f in self.cache_path.rglob("*") if f.is_file())
            return total / (1024 * 1024)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("[downloads_tab] WARN: failed to compute cache size for %s: %s", self.cache_path, exc)
            return 0.0


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class DownloadsTab(QueuePanelMixin, CachePanelMixin, MDBoxLayout):
    """Tab 3 — Downloads (queue + cache)."""

    def __init__(self, host, on_switch_to_installed: Optional[Callable] = None, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._on_switch_to_installed = on_switch_to_installed

        self._queue: list[_QueueItem] = []
        self._cached: list[_CacheItem] = []
        self._queue_lock = threading.Lock()
        self._game_id: str = ""
        self._detection = None
        self._ue4ss_detected: bool = False
        self._framework_detected: bool = False
        self._selected_cache: set[str] = set()
        self._collapsed_sections: set[str] = set()
        self._expanded_cache: set[str] = set()
        self._cache_dirty: bool = False
        self._title_label = None
        self._progress_bars: dict = {}
        self._progress_labels: dict = {}
        self._last_progress_time: dict = {}
        from ...controllers.tabs.downloads.cache import CacheController
        self._ctrl = CacheController(self._host, on_refresh=self._scan_cache_and_rebuild)
        self._build_ui()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        toolbar = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(48),
            md_bg_color=(0.12, 0.16, 0.20, 1), padding=(dp(8), 0), spacing=dp(4),
        )
        self._title_label = MDLabel(
            text="Downloads", font_style="Title", role="medium",
            size_hint_x=1, halign="left",
        )
        toolbar.add_widget(self._title_label)
        toolbar.add_widget(TipIconButton(
            icon="refresh",
            tooltip_text="Rescan cache",
            on_release=lambda *_: self._scan_cache_and_rebuild(),
        ))
        self.add_widget(toolbar)

        self.add_widget(MDLabel(
            text=(
                "Downloads from your registries. Mods and templates are installed to your game "
                "directory and require UE4SS and the framework mod. Other content (such as UE4SS "
                "and the framework mod itself) can be installed independently and is always available here."
            ),
            size_hint_y=None,
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
            role="small",
            padding=[dp(12), dp(4)],
        ))

        self._scroll = ScrollView(size_hint=(1, 1))
        self._content = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            spacing=dp(2), padding=[dp(8), dp(4)],
        )
        self._scroll.add_widget(self._content)
        self.add_widget(self._scroll)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def refresh(self, game_id: str, detection=None) -> None:
        self._game_id = game_id
        self._detection = detection
        self._ue4ss_detected = bool(detection and detection.valid)
        mods_svc = self._host.get_service("mods")
        self._framework_detected = bool(
            mods_svc and mods_svc.get_framework_mod_dir() is not None
        ) if self._ue4ss_detected else False
        self._cache_dirty = False
        self._scan_cache_and_rebuild()

    def mark_stale(self) -> None:
        self._cache_dirty = True

    def add_to_queue(self, items: list) -> None:
        """items: list of (mod_obj, category) tuples OR bare ContentDescriptor objects."""
        if not self._game_id:
            logger.error(
                "add_to_queue called with no active game_id — items discarded to prevent "
                "cross-game contamination: %s", [
                    getattr(i[0] if isinstance(i, tuple) else i, "name", "?")
                    for i in items
                ]
            )
            return
        with self._queue_lock:
            existing_keys = {qi.key for qi in self._queue}
            for item in items:
                mod_obj = item[0] if isinstance(item, tuple) and len(item) == 2 else item
                qi = _QueueItem(mod=mod_obj, game_id=self._game_id)
                if qi.key not in existing_keys:
                    self._queue.append(qi)
                    existing_keys.add(qi.key)
        self._rebuild_ui()
        self._start_next_download()

    # -----------------------------------------------------------------------
    # Cache scan
    # -----------------------------------------------------------------------

    def _scan_cache_and_rebuild(self) -> None:
        def _bg():
            items = self._scan_cache()
            Clock.schedule_once(lambda dt: self._set_cached(items), 0)
        threading.Thread(target=_bg, daemon=True).start()

    def _scan_cache(self) -> list[_CacheItem]:
        items = []
        if not _CACHE_DIR.is_dir():
            return items
        from ...models.state.pipeline import ContentSerializer

        def _add_item(cache_dir: Path) -> None:
            result = ContentSerializer().load_cache(cache_dir, log_fn=self._host.log)
            if not result:
                return
            content, _ = result
            if content.game_id != self._game_id:
                if not content.game_id:
                    logger.debug(
                        "Skipping untagged cache entry at %s -- no game_id (pre-AB3 cache); "
                        "re-download to associate with a game",
                        cache_dir,
                    )
                return
            items.append(_CacheItem(cache_path=cache_dir, content=content))

        _SKIP = {"github", "_framework"}

        for repo_dir in _CACHE_DIR.iterdir():
            if not repo_dir.is_dir() or repo_dir.name in _SKIP:
                continue
            if repo_dir.name == "_other":
                for ue4ss_repo_dir in repo_dir.iterdir():
                    if not ue4ss_repo_dir.is_dir():
                        continue
                    for tag_dir in ue4ss_repo_dir.iterdir():
                        if tag_dir.is_dir():
                            _add_item(tag_dir)
                continue
            for folder_dir in repo_dir.iterdir():
                if not folder_dir.is_dir():
                    continue
                if folder_dir.name == "Templates":
                    for game_dir in folder_dir.iterdir():
                        if game_dir.is_dir():
                            _add_item(game_dir)
                    continue
                _add_item(folder_dir)

        return items

    def _set_cached(self, items: list) -> None:
        self._cached = items
        self._rebuild_ui()

    # -----------------------------------------------------------------------
    # UI rebuild
    # -----------------------------------------------------------------------

    _CAT_ACCENT = {
        "template": (0.2, 0.7, 0.6, 1),
        "mod":      (0.3, 0.5, 0.9, 1),
        "other":    (0.8, 0.55, 0.1, 1),
    }
    _CAT_LABEL = {
        "template": ("Templates", "file-tree"),
        "mod":      ("Mods",      "layers-search"),
        "other":    ("Other",     "package-variant"),
    }

    def _update_title_size(self) -> None:
        if not self._title_label:
            return
        try:
            cache_root = Path.home() / ".apf_manager" / "cache"
            if not cache_root.exists():
                self._title_label.text = "Downloads"
                return

            total_bytes = 0
            game_bytes = 0
            for item in self._cached:
                try:
                    size = sum(f.stat().st_size for f in item.cache_path.rglob("*") if f.is_file())
                except Exception as exc:
                    self._host.log(f"[downloads] WARN: failed to stat cache files at {item.cache_path}: {exc}")
                    size = 0
                total_bytes += size
                if item.category != "other" and self._game_id and item.game_name == self._game_id:
                    game_bytes += size

            def _fmt(b: int) -> str:
                if b >= 1_073_741_824:
                    return f"{b / 1_073_741_824:.1f} GB"
                if b >= 1_048_576:
                    return f"{b / 1_048_576:.1f} MB"
                if b >= 1_024:
                    return f"{b / 1_024:.1f} KB"
                return f"{b} B"

            if total_bytes == 0:
                self._title_label.text = "Downloads"
            elif self._game_id and game_bytes > 0:
                self._title_label.text = (
                    f"Downloads — Total: {_fmt(total_bytes)} — This game: {_fmt(game_bytes)}"
                )
            else:
                self._title_label.text = f"Downloads — Total: {_fmt(total_bytes)}"
        except Exception as exc:
            self._host.log(f"[downloads] WARN: failed to compute cache size: {exc}")
            self._title_label.text = "Downloads"

    def _rebuild_ui(self) -> None:
        # Drop stale progress bar references before clearing the widget tree
        self._progress_bars.clear()
        self._content.clear_widgets()
        self._update_title_size()

        self._maybe_add_updates_section()

        with self._queue_lock:
            queue_snapshot = list(self._queue)
        queue_snapshot = [q for q in queue_snapshot if not q.game_id or q.game_id == self._game_id]
        active_items  = [q for q in queue_snapshot if q.status not in ("done", "error")]
        error_items   = [q for q in queue_snapshot if q.status == "error"]

        if queue_snapshot:
            queue_collapsed = "Queue" in self._collapsed_sections
            self._content.add_widget(self._section_header(
                "Queue", "tray-arrow-down",
                count=len(active_items),
                subtitle=f"{len(error_items)} error(s)" if error_items else "",
                accent_color=(0.3, 0.5, 0.9, 1),
                collapsed=queue_collapsed,
            ))
            if not queue_collapsed:
                self._add_items_by_category(queue_snapshot, self._queue_row, section="queue")

        if self._cached:
            cached_collapsed = "Cached" in self._collapsed_sections
            self._content.add_widget(self._section_header(
                "Cached", "package-variant",
                count=len(self._cached),
                accent_color=(0.3, 0.5, 0.9, 1),
                collapsed=cached_collapsed,
            ))
            if not cached_collapsed:
                self._content.add_widget(self._cached_toolbar())
                self._add_items_by_category(self._cached, self._cache_row, section="cached")
        elif not queue_snapshot:
            self._content.add_widget(MDLabel(
                text=(
                    "No downloads yet.\n"
                    "Select mods in the Content tab and click Queue for Download."
                ),
                halign="center", size_hint=(1, None), height=dp(80),
                theme_text_color="Secondary",
            ))

        # Reset scroll to top after rebuild so cleared/completed content doesn't leave
        # the view stranded at a stale scroll position showing empty space.
        Clock.schedule_once(lambda dt: setattr(self._scroll, 'scroll_y', 1.0), 0)

    def _add_items_by_category(self, items: list, row_builder, section: str = "") -> None:
        from collections import defaultdict
        by_cat: dict = defaultdict(list)
        for item in items:
            cat = getattr(item, "category", "mod")
            by_cat[cat].append(item)

        for cat in ("template", "mod", "other"):
            cat_items = by_cat.get(cat, [])
            if not cat_items:
                continue
            label, icon = self._CAT_LABEL.get(cat, (cat.capitalize(), "package"))
            accent = self._CAT_ACCENT.get(cat, (0.5, 0.5, 0.7, 1))
            sub_key = f"{section}:{cat}" if section else cat
            sub_collapsed = sub_key in self._collapsed_sections
            self._content.add_widget(
                self._cat_sub_header(label, icon, accent, len(cat_items),
                                     key=sub_key, collapsed=sub_collapsed)
            )
            if not sub_collapsed:
                for item in cat_items:
                    self._content.add_widget(row_builder(item))

    def _cat_sub_header(self, title: str, icon: str, accent: tuple, count: int,
                        key: str = "", collapsed: bool = False) -> MDBoxLayout:
        def _toggle(t, k=key):
            if k in self._collapsed_sections:
                self._collapsed_sections.discard(k)
            else:
                self._collapsed_sections.add(k)
            Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)

        return make_section_header(
            title=title, icon=icon, count=count,
            accent_color=accent, collapsed=collapsed,
            on_toggle=_toggle if key else None,
        )

    def _maybe_add_updates_section(self) -> None:
        updates_svc = self._host.get_service("updates")
        if not updates_svc:
            return
        fw_info = updates_svc.get_update_info("framework")
        if not (fw_info and fw_info.is_update_available and fw_info.latest_stable):
            return

        from ..banners.framework_status_banner import FrameworkStatusBanner

        latest_tag = fw_info.latest_stable.tag_name
        current    = fw_info.current if fw_info.current != "unknown" else "?"
        detail     = f"AP Framework update available: {current} → {latest_tag}"

        section = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=_BG_UPDATES, padding=[dp(8), dp(8)], spacing=dp(4),
        )
        section.add_widget(FrameworkStatusBanner(state="update_available", detail=detail))

        has_detection = bool(self._detection and self._detection.valid)
        dl_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(8),
        )
        dl_btn = MDButton(
            MDButtonText(text="Download"),
            style="filled", size_hint=(None, None), size=(dp(110), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._download_framework(fw_info),
        )
        dl_btn.disabled = not has_detection
        dl_row.add_widget(dl_btn)
        if not has_detection:
            from kivymd.uix.label import MDLabel as _ML
            dl_row.add_widget(_ML(
                text="Requires UE4SS installation",
                size_hint=(None, 1), width=dp(180),
                font_style="Label", role="small",
                theme_text_color="Custom", text_color=COL_DIM,
            ))
        section.add_widget(dl_row)
        self._content.add_widget(section)

    def _download_framework(self, update_info) -> None:
        updates_svc = self._host.get_service("updates")
        if not updates_svc:
            return
        latest_tag = (update_info.latest_stable.tag_name
                      if (update_info and update_info.latest_stable) else "unknown")
        dest = _CACHE_DIR / "_framework" / f"framework-{latest_tag}.zip"
        updates_svc.download_update(
            "framework", dest,
            on_done=lambda ok, msg: Clock.schedule_once(
                lambda dt: self._on_fw_download_done(ok, msg, dest), 0
            ),
        )

    def _on_fw_download_done(self, ok: bool, msg: str, dest: Path) -> None:
        if ok:
            self._install_framework_update(dest)
        else:
            self._host.log(f"[downloads] Framework download failed: {msg}")

    def _install_framework_update(self, zip_path: Path) -> None:
        if not (self._detection and self._detection.valid):
            return
        import zipfile, shutil
        platform_dir = (
            self._detection.platform.platform_dir
            if (self._detection and self._detection.platform) else None
        )
        if not platform_dir:
            return
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in zf.namelist():
                    if name.endswith(".dll"):
                        fname = Path(name).name
                        dest_file = platform_dir / fname
                        with zf.open(name) as src, open(dest_file, "wb") as dst:
                            dst.write(src.read())
            self._host.log("[downloads] Framework update installed.")
        except Exception as exc:
            self._host.log(f"[downloads] Framework install failed: {exc}")

    # -----------------------------------------------------------------------
    # Section header
    # -----------------------------------------------------------------------

    def _section_header(self, title: str, icon: str, count: int = 0,
                        subtitle: str = "",
                        accent_color: tuple = (0.3, 0.5, 0.9, 1),
                        collapsed: bool = False) -> MDBoxLayout:
        return make_section_header(
            title=title, icon=icon, count=count,
            accent_color=accent_color, subtitle=subtitle, collapsed=collapsed,
            on_toggle=self._toggle_section,
        )

    def _toggle_section(self, title: str) -> None:
        if title in self._collapsed_sections:
            self._collapsed_sections.discard(title)
        else:
            self._collapsed_sections.add(title)
        Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)

    def _cached_toolbar(self) -> MDBoxLayout:
        has_mods_or_templates = any(
            ci.category in ("mod", "template") for ci in self._cached
        )
        prereqs_missing = has_mods_or_templates and not (
            self._ue4ss_detected and self._framework_detected
        )
        toolbar = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44),
            padding=[dp(8), dp(4)], spacing=dp(4),
        )
        toolbar.add_widget(MDButton(
            MDButtonText(text="Select All"),
            style="outlined", size_hint=(None, None), size=(dp(104), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._select_all_cached(True),
        ))
        toolbar.add_widget(MDButton(
            MDButtonText(text="Select None"),
            style="outlined", size_hint=(None, None), size=(dp(104), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._select_all_cached(False),
        ))
        toolbar.add_widget(Widget(size_hint_x=1))
        install_btn = MDButton(
            MDButtonText(text="Install Selected"),
            style="filled", size_hint=(None, None), size=(dp(152), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._on_install_selected(),
        )
        if prereqs_missing:
            toolbar.add_widget(MDLabel(
                text="UE4SS + framework required for mods/templates" if not self._ue4ss_detected else "Framework mod required for mods/templates",
                size_hint=(None, 1), width=dp(240),
                font_style="Label", role="small",
                theme_text_color="Custom", text_color=(0.8, 0.55, 0.1, 1),
                halign="right", valign="middle",
            ))
        toolbar.add_widget(install_btn)
        toolbar.add_widget(MDButton(
            MDButtonText(text="Remove Selected"),
            style="text", size_hint=(None, None), size=(dp(152), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._on_remove_selected(),
        ))
        return toolbar

    # -----------------------------------------------------------------------
    # Badge count
    # -----------------------------------------------------------------------

    def get_download_count(self) -> int:
        with self._queue_lock:
            active = sum(
                1 for q in self._queue
                if q.status in ("queued", "downloading")
                and (not q.game_id or q.game_id == self._game_id)
            )
        if active:
            return active
        return len(self._cached)

    def get_active_download_count(self) -> int:
        with self._queue_lock:
            return sum(1 for q in self._queue if q.status in ("queued", "downloading"))


