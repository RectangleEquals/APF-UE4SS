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
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
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
    game_id: str = ""            # game this item was queued for; "" = any game

    @property
    def key(self) -> str:
        if self.category == "template":
            path  = getattr(self.mod, "path", str(id(self.mod)))
            owner = getattr(self.mod, "owner", "")
            repo  = getattr(self.mod, "repo", "")
            return f"tmpl:{owner}+{repo}/{path}"
        if self.category == "other":
            owner = getattr(self.mod, "owner", "")
            repo  = getattr(self.mod, "repo", "")
            tag   = getattr(self.mod, "tag", getattr(self.mod, "name", str(id(self.mod))))
            return f"other:{owner}+{repo}/{tag}"
        folder = getattr(self.mod, "folder", getattr(self.mod, "mod_id", ""))
        owner  = getattr(self.mod, "owner", "")
        repo   = getattr(self.mod, "repo",  "")
        return f"{owner}+{repo}/{folder}"

    @property
    def display_name(self) -> str:
        if self.category == "template":
            path = getattr(self.mod, "path", "")
            return path.rsplit("/", 1)[-1] if path else "Template"
        if self.category == "other":
            return getattr(self.mod, "name", "Other")
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
    game_name: str = ""
    install_type: str = ""

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
        self._selected_cache: set[str] = set()        # set of cache_path str for checked rows
        self._collapsed_sections: set[str] = set()   # collapsed section/sub-section keys
        self._expanded_cache: set[str] = set()        # expanded cached-row detail panels
        self._cache_dirty: bool = False               # True when cache needs re-scan (e.g. after clear)
        self._title_label = None                      # set by _build_ui
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
        self._ue4ss_detected = bool(detection and getattr(detection, "valid", False))
        mods_svc = self._host.get_service("mods")
        self._framework_detected = bool(
            mods_svc and mods_svc.get_framework_mod_dir() is not None
        ) if self._ue4ss_detected else False
        self._cache_dirty = False
        self._scan_cache_and_rebuild()

    def mark_stale(self) -> None:
        """Mark the cache as dirty so it re-scans the next time the tab is shown/activated."""
        self._cache_dirty = True

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
                qi = _QueueItem(mod=mod_obj, category=category, game_id=self._game_id or "")
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
        import json as _json
        items = []
        if not _CACHE_DIR.is_dir():
            return items
        registry_svc = self._host.get_service("registry")
        mod_by_folder: dict[str, object] = {}
        if registry_svc and self._game_id:
            for m in (registry_svc.get_mods(self._game_id) or []):
                mod_by_folder[getattr(m, "folder", "")] = m

        _SKIP = {"github", "_framework"}

        def _read_meta(folder_dir: Path) -> tuple[str, str, str]:
            """Return (category, game_name, install_type) from .apf_meta.json or defaults."""
            meta_file = folder_dir / ".apf_meta.json"
            if meta_file.exists():
                try:
                    m = _json.loads(meta_file.read_text())
                    return m.get("category", "mod"), m.get("game_name", ""), m.get("install_type", "")
                except Exception:
                    pass
            return "mod", "", ""

        def _add_item(folder_dir: Path, owner: str, repo: str) -> None:
            category, game_name, install_type = _read_meta(folder_dir)
            # Skip items that belong to a different game.
            # Official UE4SS / framework binaries write game_name="" so they always pass.
            if game_name and game_name != self._game_id:
                return
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
                category=category,
                game_name=game_name,
                install_type=install_type,
            ))

        for repo_dir in _CACHE_DIR.iterdir():
            if not repo_dir.is_dir():
                continue
            if repo_dir.name in _SKIP:
                continue
            # _other/ — two levels deep: _other/<owner+repo>/<tag>/
            if repo_dir.name == "_other":
                for ue4ss_repo_dir in repo_dir.iterdir():
                    if not ue4ss_repo_dir.is_dir():
                        continue
                    parts = ue4ss_repo_dir.name.split("+", 1)
                    owner = parts[0] if len(parts) >= 1 else ""
                    repo  = parts[1] if len(parts) == 2 else ""
                    for tag_dir in ue4ss_repo_dir.iterdir():
                        if tag_dir.is_dir():
                            _add_item(tag_dir, owner, repo)
                continue

            parts = repo_dir.name.split("+", 1)
            owner = parts[0] if len(parts) >= 1 else ""
            repo  = parts[1] if len(parts) == 2 else ""

            for folder_dir in repo_dir.iterdir():
                if not folder_dir.is_dir():
                    continue
                # Check if this is a Templates/ sub-directory (extra depth for templates)
                if folder_dir.name == "Templates":
                    for game_dir in folder_dir.iterdir():
                        if game_dir.is_dir():
                            _add_item(game_dir, owner, repo)
                    continue
                _add_item(folder_dir, owner, repo)

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

    def _update_title_size(self) -> None:
        """Refresh title label with total and per-game cache sizes."""
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
                except Exception:
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
        except Exception:
            self._title_label.text = "Downloads"

    def _rebuild_ui(self) -> None:
        self._content.clear_widgets()
        self._update_title_size()

        # APF Updates section (framework update)
        self._maybe_add_updates_section()

        # Queue section — only show items queued for the current game
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

        # Cached section
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

    def _add_items_by_category(self, items: list, row_builder, section: str = "") -> None:
        """Render items grouped by category, with a collapsible sub-header per category."""
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
        """Indented sub-section header for category grouping within Queue/Cached. Click to toggle."""
        chevron = "chevron-right" if collapsed else "chevron-down"
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
        inner.add_widget(MDIcon(
            icon=chevron, size_hint=(None, 1), width=dp(16),
            theme_icon_color="Custom", icon_color=(0.45, 0.47, 0.55, 1),
        ))
        outer.add_widget(inner)

        if key:
            def _on_touch(widget, touch):
                if widget.collide_point(*touch.pos) and touch.button == "left":
                    if key in self._collapsed_sections:
                        self._collapsed_sections.discard(key)
                    else:
                        self._collapsed_sections.add(key)
                    from kivy.clock import Clock
                    Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)
                    return True
            outer.bind(on_touch_down=_on_touch)
        return outer

    def _maybe_add_updates_section(self) -> None:
        updates_svc = self._host.get_service("updates")
        if not updates_svc:
            return
        fw_info = updates_svc.get_update_info("framework")
        if not (fw_info and fw_info.is_update_available and fw_info.latest_stable):
            return

        latest_tag = fw_info.latest_stable.tag_name
        current    = fw_info.current if fw_info.current != "unknown" else "?"

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
        ver_text = f"AP Framework: {current} → {latest_tag}"
        detail_row.add_widget(MDLabel(
            text=ver_text, size_hint=(1, 1), halign="left",
            theme_text_color="Custom", text_color=_COL_FW,
        ))
        has_detection = bool(self._detection and getattr(self._detection, "valid", False))
        dl_btn = MDButton(
            MDButtonText(text="Download"),
            style="filled", size_hint=(None, None), size=(dp(110), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._download_framework(fw_info),
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
                        accent_color: tuple = (0.3, 0.5, 0.9, 1),
                        collapsed: bool = False) -> MDBoxLayout:
        """Collapsible section header with left accent bar. Click to toggle."""
        chevron_icon = "chevron-right" if collapsed else "chevron-down"
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
        inner.add_widget(MDIcon(
            icon=chevron_icon, size_hint=(None, 1), width=dp(20),
            theme_icon_color="Custom", icon_color=(0.5, 0.52, 0.6, 1),
        ))
        outer.add_widget(inner)

        def _on_touch(widget, touch):
            if widget.collide_point(*touch.pos) and touch.button == "left":
                key = title
                if key in self._collapsed_sections:
                    self._collapsed_sections.discard(key)
                else:
                    self._collapsed_sections.add(key)
                from kivy.clock import Clock
                Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)
                return True
        outer.bind(on_touch_down=_on_touch)
        return outer

    def _cached_toolbar(self) -> MDBoxLayout:
        """Select All / Select None | Install Selected | Remove Selected toolbar."""
        # Other-category items (UE4SS, framework binaries) can always be installed.
        # Mods and templates require UE4SS + framework. Show informational label
        # when prereqs are absent, but keep the button enabled (items that can't
        # install will be skipped with a logged error in _do_install).
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
        expanded   = cache_key in self._expanded_cache

        container = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=_BG_ITEM,
        )

        header = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(52),
            padding=[dp(4), dp(4)], spacing=dp(4),
        )

        # Checkbox
        chk = MDCheckbox(
            size_hint=(None, None), size=(dp(36), dp(36)),
            pos_hint={"center_y": 0.5},
            active=is_checked,
        )
        chk.bind(active=lambda inst, val, k=cache_key: self._on_cache_check(k, val))
        header.add_widget(chk)

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
        if ci.owner or ci.repo:
            sub_parts.append(f"{ci.owner}/{ci.repo}")
        info.add_widget(MDLabel(
            text="  ·  ".join(sub_parts),
            font_style="Label", role="small",
            size_hint_y=None, height=dp(18),
            theme_text_color="Custom", text_color=_COL_DIM,
        ))
        header.add_widget(info)

        chevron_icon = "chevron-up" if expanded else "chevron-down"
        header.add_widget(MDIconButton(
            icon=chevron_icon,
            size_hint=(None, None), size=(dp(32), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_, k=cache_key: self._toggle_cache_expand(k),
        ))
        # Make the whole header row clickable (not just the chevron)
        def _on_header_touch(w, touch, k=cache_key):
            if w.collide_point(*touch.pos) and touch.button == "left":
                self._toggle_cache_expand(k)
                return True
        info.bind(on_touch_down=_on_header_touch)
        container.add_widget(header)

        if expanded:
            container.add_widget(self._cache_detail(ci))
        return container

    def _cache_detail(self, ci: _CacheItem) -> MDBoxLayout:
        """Expanded detail panel for a cached item."""
        panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, adaptive_height=True,
            md_bg_color=(0.08, 0.09, 0.11, 1),
            padding=[dp(16), dp(6), dp(8), dp(8)], spacing=dp(4),
        )
        # Source
        if ci.owner or ci.repo:
            panel.add_widget(MDLabel(
                text=f"Source: {ci.owner}/{ci.repo}",
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        # Version
        if ci.version:
            panel.add_widget(MDLabel(
                text=f"Version: v{ci.version}",
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        # Components
        comp_labels = {"lua": "Lua", "cpp": "C++", "blueprint": "Blueprint"}
        comp_texts = [comp_labels.get(c, c) for c in ci.components]
        if comp_texts:
            comp_row = MDBoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(18), spacing=dp(8),
            )
            comp_row.add_widget(MDLabel(
                text="Components:",
                font_style="Label", role="small", size_hint=(None, 1), width=dp(80),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
            for ct in comp_texts:
                comp_row.add_widget(MDLabel(
                    text=ct, font_style="Label", role="small",
                    size_hint=(None, 1), width=dp(64),
                    theme_text_color="Custom", text_color=(0.6, 0.8, 1.0, 1),
                ))
            panel.add_widget(comp_row)
        # Size
        size = ci.size_mb
        if size > 0:
            panel.add_widget(MDLabel(
                text=f"Cache size: {size:.1f} MB",
                font_style="Label", role="small", size_hint_y=None, height=dp(16),
                theme_text_color="Custom", text_color=_COL_DIM,
            ))
        # Category
        cat_display = {"template": "Template", "mod": "Mod", "other": "Other"}.get(
            ci.category, ci.category.capitalize() if ci.category else "Mod"
        )
        panel.add_widget(MDLabel(
            text=f"Category: {cat_display}",
            font_style="Label", role="small", size_hint_y=None, height=dp(16),
            theme_text_color="Custom", text_color=_COL_DIM,
        ))
        # Changelog button for other-category items (UE4SS / framework releases)
        # Resolve the _OtherEntry for this cached item by matching owner/repo/tag
        _other_ref = ci.mod_ref
        if ci.category == "other" and _other_ref is None:
            registry_svc = self._host.get_service("registry") if self._host.has_service("registry") else None
            updates_svc = self._host.get_service("updates") if self._host.has_service("updates") else None
            all_other: list = []
            if registry_svc and hasattr(registry_svc, "get_other_content"):
                all_other += registry_svc.get_other_content(self._game_id) or []
            if updates_svc and hasattr(updates_svc, "get_ue4ss_releases_for_content"):
                all_other += updates_svc.get_ue4ss_releases_for_content() or []
            if updates_svc and hasattr(updates_svc, "get_framework_releases_for_content"):
                all_other += updates_svc.get_framework_releases_for_content() or []
            for entry in all_other:
                if (getattr(entry, "owner", "") == ci.owner and
                        getattr(entry, "repo", "") == ci.repo):
                    _other_ref = entry
                    break
        if ci.category == "other" and _other_ref is not None:
            changelog = getattr(_other_ref, "changelog", "")
            if changelog:
                def _show_changelog(*_, _cl=changelog):
                    from kivymd.uix.dialog import (
                        MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
                        MDDialogButtonContainer,
                    )
                    from kivymd.uix.button import MDButton, MDButtonText
                    dlg_ref = [None]
                    def _close(*_):
                        if dlg_ref[0]:
                            dlg_ref[0].dismiss()
                    dlg = MDDialog(
                        MDDialogHeadlineText(text="Release Notes"),
                        MDDialogSupportingText(text=_cl),
                        MDDialogButtonContainer(
                            MDButton(MDButtonText(text="Close"), style="text", on_release=_close),
                        ),
                    )
                    dlg_ref[0] = dlg
                    dlg.open()
                from kivymd.uix.button import MDButton, MDButtonText
                panel.add_widget(MDButton(
                    MDButtonText(text="Release Notes"),
                    style="text",
                    size_hint_y=None, height=dp(36),
                    on_release=_show_changelog,
                ))
        return panel

    def _toggle_cache_expand(self, key: str) -> None:
        if key in self._expanded_cache:
            self._expanded_cache.discard(key)
        else:
            self._expanded_cache.clear()   # auto-collapse all other rows
            self._expanded_cache.add(key)
        Clock.schedule_once(lambda dt: self._rebuild_ui(), 0)

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
            import json as _json
            owner  = getattr(item.mod, "owner", "")
            repo   = getattr(item.mod, "repo",  "")
            folder = getattr(item.mod, "folder", getattr(item.mod, "mod_id", ""))

            if item.category == "template":
                path = getattr(item.mod, "path", folder)
                dest = _CACHE_DIR / f"{owner}+{repo}" / path
            elif item.category == "other":
                ue4ss_owner = getattr(item.mod, "owner", "")
                ue4ss_repo  = getattr(item.mod, "repo", "")
                tag         = getattr(item.mod, "tag", "unknown")
                dest = _CACHE_DIR / "_other" / f"{ue4ss_owner}+{ue4ss_repo}" / tag
            else:
                dest = _CACHE_DIR / f"{owner}+{repo}" / folder

            dest.mkdir(parents=True, exist_ok=True)

            # Write metadata immediately after mkdir so category is recoverable
            # even if the download fails partway through.
            if item.category == "other":
                _install_type = getattr(item.mod, "install_type", "")
                _reg_owner    = getattr(item.mod, "registry_owner", "")
                if _install_type == "framework_binary" or not _reg_owner:
                    # Official UE4SS or APF Framework binaries — game-agnostic
                    _game_name = ""
                else:
                    # Custom registry-provided fork — game-specific
                    _game_name = self._game_id
            else:
                _mod_id = getattr(item.mod, "mod_id", "")
                _id_parts = _mod_id.split(".")
                # Derive game_name: prefer mod_id segment, then game_id attr, then current game
                _game_name = (
                    _id_parts[1] if len(_id_parts) >= 2 and _id_parts[1]
                    else getattr(item.mod, "game_id", "") or self._game_id
                )
            (dest / ".apf_meta.json").write_text(_json.dumps({
                "category":     item.category,
                "game_name":    _game_name,
                "install_type": getattr(item.mod, "install_type", ""),
            }))

            from ....core.remote.github_api import GitHubAPI, _BUNDLED_TOKEN_PATH
            token = _BUNDLED_TOKEN_PATH.read_text().strip() \
                if _BUNDLED_TOKEN_PATH.exists() else ""

            if item.category == "other":
                import zipfile as _zipfile
                opt = item.mod
                opt_type = getattr(opt, "type", "manual")
                self._host.log(
                    f"[downloads] other-download: opt_type={opt_type!r} "
                    f"owner={getattr(opt,'owner','')!r} repo={getattr(opt,'repo','')!r} "
                    f"tag={getattr(opt,'tag','')!r} name={getattr(opt,'name','')!r}"
                )
                if opt_type == "github_release":
                    api = GitHubAPI(
                        repo_owner=getattr(opt, "owner", ""),
                        repo_name=getattr(opt, "repo", ""),
                        token_file_path=_BUNDLED_TOKEN_PATH if _BUNDLED_TOKEN_PATH.exists() else None,
                        on_status=lambda lvl, msg: None,
                    )
                    # Build list of assets to download from per-asset selection
                    _raw_assets = getattr(opt, "assets", []) or []
                    selected_assets = [a for a in _raw_assets if getattr(a, "selected", False)]
                    if not selected_assets:
                        # Backwards compat: no assets list — use legacy single url field
                        direct_url = getattr(opt, "url", "")
                        if direct_url:
                            from ..registry_service import _OtherAsset as _OA
                            _fname = direct_url.split("/")[-1].split("?")[0] or f"{getattr(opt,'tag','release')}.zip"
                            selected_assets = [_OA(name=_fname, url=direct_url)]
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
                        # Per-file integrity check (zip assets only)
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
                # For templates, the source path in the repo is the template's `path` field.
                # TemplateEntry has no `folder` attribute — use `path` directly.
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
        # "other" items (UE4SS, framework binaries) bypass all mod-level validation.
        other_items = [ci for ci in items if getattr(ci, "category", "mod") == "other"]
        mod_items   = [ci for ci in items if getattr(ci, "category", "mod") != "other"]

        validation_svc = self._host.get_service("validation")
        if validation_svc and self._detection and mod_items:
            results = validation_svc.validate_cached(mod_items, self._detection)
            errors   = [r for r in results if r.status == "error"]
            warnings = [r for r in results if r.status == "warn"]
            if errors:
                self._show_install_warn(errors, warnings, allow_proceed=False)
                return
            if warnings:
                self._show_install_warn(errors, warnings, allow_proceed=True,
                                        items=items)
                return
        # Install all items (other items bypass validation entirely)
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
                if ci.category == "template":
                    # Templates require UE4SS + framework mod
                    if not (self._ue4ss_detected and self._framework_detected):
                        self._host.log(
                            f"[downloads] Skipped template '{ci.display_name}': "
                            "framework mod required"
                        )
                        continue
                    game_name = ci.game_name or game_id
                    deploy_svc.deploy_template(ci.cache_path, game_name)
                    self._host.log(f"[downloads] Installed template {ci.display_name}")

                elif ci.category == "other":
                    # Other items (UE4SS, framework binaries) — no prereqs required
                    deploy_svc.deploy_other(ci.cache_path, ci.install_type, self._detection)
                    self._host.log(f"[downloads] Installed other '{ci.display_name}'")

                else:
                    # Mod — requires UE4SS
                    if not self._ue4ss_detected:
                        self._host.log(
                            f"[downloads] Skipped mod '{ci.display_name}': UE4SS required"
                        )
                        continue
                    components   = ci.components
                    bp_pak_files = ci.bp_pak_files
                    metadata     = {
                        "mod_id":        getattr(ci.mod_ref, "mod_id", "") if ci.mod_ref else "",
                        "folder_name":   ci.folder_name,
                        "source_repo":   f"{ci.owner}/{ci.repo}",
                        "source_folder": ci.folder_name,
                        "version":       ci.version,
                    }
                    deploy_svc.deploy_mod(
                        ci.cache_path, ci.folder_name,
                        components, bp_pak_files,
                        self._detection, game_id, metadata,
                    )
                    self._host.log(f"[downloads] Installed mod {ci.display_name}")

            except Exception as exc:
                self._host.log(f"[downloads] Install failed for {ci.display_name}: {exc}")

        mods_svc = self._host.get_service("mods")
        if mods_svc:
            mods_svc.rescan()

        ue4ss_installed = any(
            ci.category == "other" and getattr(ci.mod, "install_type", "") == "ue4ss"
            for ci in items
        )
        if ue4ss_installed:
            profile = self._host.get_game_context()
            if profile:
                from ....core.ue4ss import UE4SSDetector
                new_detection = UE4SSDetector.detect(profile.game_root)
                self._detection = new_detection
                self._host.set_game_context(profile, new_detection)

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

    def get_active_download_count(self) -> int:
        """Count of items actively queued or downloading (not cached)."""
        with self._queue_lock:
            return sum(1 for q in self._queue if q.status in ("queued", "downloading"))


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
