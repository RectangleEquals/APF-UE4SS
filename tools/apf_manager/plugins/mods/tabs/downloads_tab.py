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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.progressindicator import MDLinearProgressIndicator

from ....gui.widgets.tip_icon_button import TipIconButton

if TYPE_CHECKING:
    from ....core.ue4ss import UE4SSResult


_CACHE_DIR = Path.home() / ".apf_manager" / "cache"

_BG_SECTION   = (0.10, 0.12, 0.15, 1)
_BG_ITEM      = (0.13, 0.13, 0.13, 1)
_BG_UPDATES   = (0.08, 0.16, 0.18, 1)
_COL_DIM      = (0.5, 0.5, 0.5, 1)
_COL_CPP      = (0.4, 0.7, 1.0, 1)
_COL_BP       = (1.0, 0.6, 0.2, 1)
_COL_TEAL     = (0.2, 0.8, 0.8, 1)
_COL_FW       = (0.2, 0.7, 0.9, 1)


# ---------------------------------------------------------------------------
# Queue item state
# ---------------------------------------------------------------------------

@dataclass
class _QueueItem:
    mod: object                  # RegistryModEntry
    status: str = "queued"       # queued | downloading | unpacking | done | error
    progress: float = 0.0        # 0.0 – 1.0
    error_msg: str = ""
    cache_path: Optional[Path] = None
    category: str = "mod"        # "mod" | "template" | "other"

    @property
    def key(self) -> str:
        if self.category == "template":
            path  = getattr(self.mod, "path", str(id(self.mod)))
            owner = getattr(self.mod, "owner", "")
            repo  = getattr(self.mod, "repo", "")
            return f"tmpl:{owner}+{repo}/{path}"
        folder = getattr(self.mod, "folder", getattr(self.mod, "mod_id", ""))
        owner  = getattr(self.mod, "owner", "")
        repo   = getattr(self.mod, "repo",  "")
        return f"{owner}+{repo}/{folder}"

    @property
    def display_name(self) -> str:
        if self.category == "template":
            path = getattr(self.mod, "path", "")
            return path.rsplit("/", 1)[-1] if path else "Template"
        return getattr(self.mod, "name", self.key)

    @property
    def components(self) -> list:
        return getattr(self.mod, "components", ["lua"])


# ---------------------------------------------------------------------------
# Cached item (on-disk)
# ---------------------------------------------------------------------------

@dataclass
class _CacheItem:
    folder_name: str
    owner: str
    repo: str
    cache_path: Path
    components: list = field(default_factory=lambda: ["lua"])
    bp_pak_files: list = field(default_factory=list)
    mod_ref: Optional[object] = None   # RegistryModEntry if still known
    category: str = "mod"              # "mod" | "template" | "other"

    @property
    def display_name(self) -> str:
        return getattr(self.mod_ref, "name", self.folder_name) if self.mod_ref else self.folder_name

    @property
    def version(self) -> str:
        return getattr(self.mod_ref, "version", "") if self.mod_ref else ""

    @property
    def size_mb(self) -> float:
        try:
            total = sum(
                f.stat().st_size for f in self.cache_path.rglob("*") if f.is_file()
            )
            return total / (1024 * 1024)
        except Exception:
            return 0.0


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class DownloadsTab(MDBoxLayout):
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
        self._selected_cache: set[str] = set()   # set of cache_path str for checked rows
        self._build_ui()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        toolbar = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(48),
            md_bg_color=(0.12, 0.16, 0.20, 1), padding=(dp(8), 0), spacing=dp(4),
        )
        toolbar.add_widget(MDLabel(
            text="Downloads", font_style="Title", role="medium",
            size_hint_x=1, halign="left",
        ))
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
        self._ue4ss_detected = bool(detection and getattr(detection, "valid", False))
        mods_svc = self._host.get_service("mods")
        self._framework_detected = bool(
            mods_svc and mods_svc.get_framework_mod_dir() is not None
        ) if self._ue4ss_detected else False
        self._scan_cache_and_rebuild()

    def add_to_queue(self, items: list) -> None:
        """Called by ContentTab when the user queues items for download.

        items: list of (mod_obj, category) tuples OR bare mod objects (backwards compat).
        """
        with self._queue_lock:
            existing_keys = {qi.key for qi in self._queue}
            for item in items:
                if isinstance(item, tuple) and len(item) == 2:
                    mod_obj, category = item
                else:
                    mod_obj, category = item, "mod"
                qi = _QueueItem(mod=mod_obj, category=category)
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
        registry_svc = self._host.get_service("registry")
        mod_by_folder: dict[str, object] = {}
        if registry_svc and self._game_id:
            for m in (registry_svc.get_mods(self._game_id) or []):
                mod_by_folder[getattr(m, "folder", "")] = m

        for repo_dir in _CACHE_DIR.iterdir():
            if not repo_dir.is_dir():
                continue
            # Skip internal caches that are not user content
            if repo_dir.name in ("github", "_framework"):
                continue
            for folder_dir in repo_dir.iterdir():
                if not folder_dir.is_dir():
                    continue
                parts = repo_dir.name.split("+", 1)
                owner = parts[0] if len(parts) >= 1 else ""
                repo  = parts[1] if len(parts) == 2 else ""
                mod_ref = mod_by_folder.get(folder_dir.name)
                components = _detect_components(folder_dir)
                bp_files = _detect_bp_paks(folder_dir)
                items.append(_CacheItem(
                    folder_name=folder_dir.name,
                    owner=owner, repo=repo,
                    cache_path=folder_dir,
                    components=components,
                    bp_pak_files=bp_files,
                    mod_ref=mod_ref,
                ))
        return items

    def _set_cached(self, items: list) -> None:
        self._cached = items
        self._rebuild_ui()

    # -----------------------------------------------------------------------
    # UI rebuild
    # -----------------------------------------------------------------------

    # Accent colors per category (matches ContentTab)
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

    def _rebuild_ui(self) -> None:
        self._content.clear_widgets()

        # APF Updates section (framework update)
        self._maybe_add_updates_section()

        # Queue section
        with self._queue_lock:
            queue_snapshot = list(self._queue)
        active_items  = [q for q in queue_snapshot if q.status not in ("done", "error")]
        error_items   = [q for q in queue_snapshot if q.status == "error"]

        if queue_snapshot:
            self._content.add_widget(self._section_header(
                "Queue", "tray-arrow-down",
                count=len(active_items),
                subtitle=f"{len(error_items)} error(s)" if error_items else "",
                accent_color=(0.3, 0.5, 0.9, 1),
            ))
            # Group queue items by category
            self._add_items_by_category(queue_snapshot, self._queue_row)

        # Cached section
        if self._cached:
            self._content.add_widget(self._section_header(
                "Cached", "package-variant",
                count=len(self._cached),
                accent_color=(0.3, 0.5, 0.9, 1),
            ))
            self._content.add_widget(self._cached_toolbar())
            # Group cached items by category
            self._add_items_by_category(self._cached, self._cache_row)
        elif not queue_snapshot:
            self._content.add_widget(MDLabel(
                text=(
                    "No downloads yet.\n"
                    "Select mods in the Content tab and click Queue for Download."
                ),
                halign="center", size_hint=(1, None), height=dp(80),
                theme_text_color="Secondary",
            ))

    def _add_items_by_category(self, items: list, row_builder) -> None:
        """Render items grouped by category, with a sub-header per non-empty category."""
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
            # Sub-header (lighter indent)
            self._content.add_widget(self._cat_sub_header(label, icon, accent, len(cat_items)))
            for item in cat_items:
                self._content.add_widget(row_builder(item))

    def _cat_sub_header(self, title: str, icon: str, accent: tuple, count: int) -> MDBoxLayout:
        """Indented sub-section header for category grouping within Queue/Cached."""
        outer = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(28),
            md_bg_color=(0.09, 0.11, 0.14, 1),
        )
        outer.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(8)))  # indent
        outer.add_widget(MDBoxLayout(
            size_hint=(None, 1), width=dp(2), md_bg_color=accent,
        ))
        inner = MDBoxLayout(
            orientation="horizontal", size_hint=(1, 1),
            padding=[dp(6), 0], spacing=dp(6),
        )
        inner.add_widget(MDIcon(
            icon=icon, size_hint=(None, 1), width=dp(16),
            theme_icon_color="Custom", icon_color=(0.7, 0.72, 0.8, 1),
        ))
        inner.add_widget(MDLabel(
            text=f"{title}  ({count})", font_style="Label", role="medium",
            size_hint_x=1, halign="left",
            theme_text_color="Custom", text_color=(0.7, 0.72, 0.8, 1),
        ))
        outer.add_widget(inner)
        return outer

    def _maybe_add_updates_section(self) -> None:
        updates_svc = self._host.get_service("updates")
        if not updates_svc:
            return
        fw_update = updates_svc.get_framework_update()
        if not fw_update:
            return

        section = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=_BG_UPDATES, padding=[dp(8), dp(8)], spacing=dp(4),
        )
        header = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8),
        )
        header.add_widget(MDIcon(
            icon="update", size_hint=(None, 1), width=dp(24),
            theme_icon_color="Custom", icon_color=_COL_TEAL,
        ))
        header.add_widget(MDLabel(
            text="Framework Update Available",
            font_style="Title", role="small", size_hint=(1, 1),
            theme_text_color="Custom", text_color=_COL_TEAL,
        ))
        section.add_widget(header)

        detail_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(8),
        )
        ver_text = (
            f"AP Framework: {fw_update.get('current','?')} → {fw_update.get('latest','?')}"
        )
        detail_row.add_widget(MDLabel(
            text=ver_text, size_hint=(1, 1), halign="left",
            theme_text_color="Custom", text_color=_COL_FW,
        ))
        has_detection = bool(self._detection and getattr(self._detection, "valid", False))
        dl_btn = MDButton(
            MDButtonText(text="Download"),
            style="filled", size_hint=(None, None), size=(dp(110), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_, u=fw_update: self._download_framework(u),
        )
        dl_btn.disabled = not has_detection
        detail_row.add_widget(dl_btn)
        if not has_detection:
            detail_row.add_widget(MDLabel(
                text="Requires UE4SS installation",
                size_hint=(None, 1), width=dp(180),
                font_style="Label", role="small",
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        section.add_widget(detail_row)
        self._content.add_widget(section)

    def _download_framework(self, update_info: dict) -> None:
        updates_svc = self._host.get_service("updates")
        if not updates_svc:
            return
        dest = _CACHE_DIR / "_framework" / f"framework-{update_info.get('latest','')}.zip"
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
        if not (self._detection and getattr(self._detection, "valid", False)):
            return
        import zipfile, shutil
        platform_dir = getattr(self._detection, "platform_dir", None)
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
    # Section / row builders
    # -----------------------------------------------------------------------

    def _section_header(self, title: str, icon: str, count: int = 0,
                        subtitle: str = "",
                        accent_color: tuple = (0.3, 0.5, 0.9, 1)) -> MDBoxLayout:
        """Collapsible-style section header with left accent bar."""
        outer = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(36),
            md_bg_color=(0.07, 0.09, 0.12, 1),
        )
        # Left accent bar
        outer.add_widget(MDBoxLayout(
            size_hint=(None, 1), width=dp(3),
            md_bg_color=accent_color,
        ))
        inner = MDBoxLayout(
            orientation="horizontal", size_hint=(1, 1),
            padding=[dp(8), 0], spacing=dp(8),
        )
        inner.add_widget(MDIcon(
            icon=icon, size_hint=(None, 1), width=dp(22),
            theme_icon_color="Custom", icon_color=(0.85, 0.88, 0.95, 1),
        ))
        label = f"{title}  ({count})" if count else title
        if subtitle:
            label += f"  — {subtitle}"
        inner.add_widget(MDLabel(
            text=label, font_style="Title", role="small",
            size_hint_x=1, halign="left",
            theme_text_color="Custom", text_color=(0.85, 0.88, 0.95, 1),
        ))
        outer.add_widget(inner)
        return outer

    def _cached_toolbar(self) -> MDBoxLayout:
        """Select All / Select None | Install Selected | Remove Selected toolbar."""
        can_install = self._ue4ss_detected and self._framework_detected
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
        install_btn.disabled = not can_install
        if not can_install:
            toolbar.add_widget(MDLabel(
                text="UE4SS + framework required" if not self._ue4ss_detected else "Framework mod required",
                size_hint=(None, 1), width=dp(200),
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

    def _queue_row(self, item: _QueueItem) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=_BG_ITEM, padding=[dp(8), dp(6)], spacing=dp(4),
        )

        top = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8),
        )
        # Component badges
        if "cpp" in item.components:
            top.add_widget(MDIcon(
                icon="code-braces", size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=_COL_CPP,
            ))
        if "blueprint" in item.components:
            top.add_widget(MDIcon(
                icon="blueprint", size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=_COL_BP,
            ))
        top.add_widget(MDLabel(
            text=item.display_name, font_style="Body",
            size_hint=(1, 1), halign="left", valign="middle",
        ))
        # Status chip
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
            text_color=status_colors.get(item.status, _COL_DIM),
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

    def _cache_row(self, ci: _CacheItem) -> MDBoxLayout:
        from kivymd.uix.selectioncontrol import MDCheckbox
        cache_key = str(ci.cache_path)
        is_checked = cache_key in self._selected_cache

        row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(52),
            md_bg_color=_BG_ITEM, padding=[dp(4), dp(4)], spacing=dp(4),
        )

        # Checkbox
        chk = MDCheckbox(
            size_hint=(None, None), size=(dp(36), dp(36)),
            pos_hint={"center_y": 0.5},
            active=is_checked,
        )
        chk.bind(active=lambda inst, val, k=cache_key: self._on_cache_check(k, val))
        row.add_widget(chk)

        info = MDBoxLayout(orientation="vertical", adaptive_height=True, size_hint=(1, 1))
        name_row = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(24), spacing=dp(4),
        )
        name_row.add_widget(MDLabel(
            text=ci.display_name, font_style="Body",
            size_hint=(1, 1), halign="left", valign="middle",
        ))
        if "cpp" in ci.components:
            name_row.add_widget(MDIcon(
                icon="code-braces", size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=_COL_CPP,
            ))
        if "blueprint" in ci.components:
            name_row.add_widget(MDIcon(
                icon="blueprint", size_hint=(None, 1), width=dp(18),
                theme_icon_color="Custom", icon_color=_COL_BP,
            ))
        info.add_widget(name_row)

        sub_parts = []
        if ci.version:
            sub_parts.append(f"v{ci.version}")
        size = ci.size_mb
        if size > 0:
            sub_parts.append(f"{size:.1f} MB")
        sub_parts.append(f"{ci.owner}/{ci.repo}")
        info.add_widget(MDLabel(
            text="  ·  ".join(sub_parts),
            font_style="Label", role="small",
            size_hint_y=None, height=dp(18),
            theme_text_color="Custom", text_color=_COL_DIM,
        ))
        row.add_widget(info)
        return row

    # -----------------------------------------------------------------------
    # Download logic
    # -----------------------------------------------------------------------

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

    def _download_item_bg(self, item: _QueueItem) -> None:
        try:
            owner  = getattr(item.mod, "owner", "")
            repo   = getattr(item.mod, "repo",  "")
            folder = getattr(item.mod, "folder", getattr(item.mod, "mod_id", ""))
            dest   = _CACHE_DIR / f"{owner}+{repo}" / folder
            dest.mkdir(parents=True, exist_ok=True)

            from ....core.remote.github_api import _BUNDLED_TOKEN_PATH
            token = _BUNDLED_TOKEN_PATH.read_text().strip() \
                if _BUNDLED_TOKEN_PATH.exists() else ""

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

    def _set_progress(self, item: _QueueItem, progress: float) -> None:
        with self._queue_lock:
            item.progress = progress
        Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)

    def _on_item_done(self, item: _QueueItem) -> None:
        self._scan_cache_and_rebuild()
        self._start_next_download()

    def _cancel(self, item: _QueueItem) -> None:
        with self._queue_lock:
            # Only remove if still queued (can't interrupt in-progress)
            if item.status == "queued":
                self._queue.remove(item)
        self._rebuild_ui()

    # -----------------------------------------------------------------------
    # Cache actions
    # -----------------------------------------------------------------------

    def _on_cache_check(self, cache_key: str, checked: bool) -> None:
        if checked:
            self._selected_cache.add(cache_key)
        else:
            self._selected_cache.discard(cache_key)

    def _select_all_cached(self, select: bool) -> None:
        if select:
            self._selected_cache = {str(ci.cache_path) for ci in self._cached}
        else:
            self._selected_cache.clear()
        self._rebuild_ui()

    def _remove_cached(self, ci: _CacheItem) -> None:
        import shutil
        try:
            shutil.rmtree(ci.cache_path, ignore_errors=True)
        except Exception:
            pass
        self._selected_cache.discard(str(ci.cache_path))
        self._scan_cache_and_rebuild()

    def _on_install_selected(self) -> None:
        selected = [ci for ci in self._cached if str(ci.cache_path) in self._selected_cache]
        if not selected:
            return
        self._validate_and_install(selected)

    def _on_remove_selected(self) -> None:
        import shutil
        selected = [ci for ci in self._cached if str(ci.cache_path) in self._selected_cache]
        for ci in selected:
            try:
                shutil.rmtree(ci.cache_path, ignore_errors=True)
            except Exception:
                pass
            self._selected_cache.discard(str(ci.cache_path))
        self._scan_cache_and_rebuild()

    def _validate_and_install(self, items: list) -> None:
        validation_svc = self._host.get_service("validation")
        if validation_svc and self._detection:
            results = validation_svc.validate_cached(items, self._detection)
            errors   = [r for r in results if r.status == "error"]
            warnings = [r for r in results if r.status == "warn"]
            if errors:
                self._show_install_warn(errors, warnings, allow_proceed=False)
                return
            if warnings:
                self._show_install_warn(errors, warnings, allow_proceed=True,
                                        items=items)
                return
        self._do_install(items)

    # Keep old _on_install_all for backwards compatibility with any callers
    def _on_install_all(self) -> None:
        self._validate_and_install(self._cached)

    def _show_install_warn(self, errors, warnings, allow_proceed: bool,
                          items: Optional[list] = None) -> None:
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        lines  = [f"[ERROR] {r.label}: {r.detail}" for r in errors]
        lines += [f"[WARN]  {r.label}: {r.detail}" for r in warnings]
        title  = "Cannot Install" if not allow_proceed else "Install with Warnings?"
        install_items = items or self._cached
        btns: list = [
            Widget(),
            MDButton(MDButtonText(text="Cancel"), style="text",
                     on_release=lambda *_: dlg.dismiss()),
        ]
        if allow_proceed:
            btns.append(MDButton(
                MDButtonText(text="Install Anyway"), style="filled",
                on_release=lambda *_: (dlg.dismiss(), self._do_install(install_items)),
            ))
        dlg = MDDialog(
            MDDialogHeadlineText(text=title),
            MDDialogSupportingText(text="\n".join(lines) or "Validation issue."),
            MDDialogButtonContainer(*btns),
        )
        dlg.open()

    def _do_install(self, items: list) -> None:
        deploy_svc = self._host.get_service("deploy")
        if not deploy_svc or not self._detection:
            return

        game_id = self._game_id
        for ci in list(items):
            try:
                components   = ci.components
                bp_pak_files = ci.bp_pak_files
                metadata     = {
                    "mod_id":       getattr(ci.mod_ref, "mod_id",  "") if ci.mod_ref else "",
                    "folder_name":  ci.folder_name,
                    "source_repo":  f"{ci.owner}/{ci.repo}",
                    "source_folder": ci.folder_name,
                    "version":      ci.version,
                }
                deploy_svc.deploy_mod(
                    ci.cache_path, ci.folder_name,
                    components, bp_pak_files,
                    self._detection, game_id, metadata,
                )
                self._host.log(f"[downloads] Installed {ci.display_name}")
            except Exception as exc:
                self._host.log(f"[downloads] Install failed for {ci.folder_name}: {exc}")

        mods_svc = self._host.get_service("mods")
        if mods_svc:
            mods_svc.rescan()

        if self._on_switch_to_installed:
            self._on_switch_to_installed()

    # -----------------------------------------------------------------------
    # Badge count
    # -----------------------------------------------------------------------

    def get_download_count(self) -> int:
        """Active queue count, or cached count if queue is idle."""
        with self._queue_lock:
            active = sum(1 for q in self._queue if q.status in ("queued", "downloading"))
        if active:
            return active
        return len(self._cached)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_components(folder: Path) -> list:
    found = []
    if (folder / "scripts" / "main.lua").exists():
        found.append("lua")
    if (folder / "dlls" / "main.dll").exists():
        found.append("cpp")
    lm = folder / "LogicMods"
    if lm.is_dir() and any(
        f.suffix.lower() in (".pak", ".ucas", ".utoc")
        for f in lm.iterdir() if f.is_file()
    ):
        found.append("blueprint")
    return found or ["lua"]


def _detect_bp_paks(folder: Path) -> list:
    lm = folder / "LogicMods"
    if not lm.is_dir():
        return []
    return [
        f.name for f in lm.iterdir()
        if f.is_file() and f.suffix.lower() in (".pak", ".ucas", ".utoc")
    ]


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

    # First pass: collect all file download_urls
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
