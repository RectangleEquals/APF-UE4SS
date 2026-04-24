"""
ContentPipelinePanel — 5-tab hub panel for apf.builtin.content.

Tabs (in order):
  1 — Registries   database-search
  2 — Content      layers-search        (merges old Templates + Mods)
  3 — Downloads    tray-arrow-down      (replaces old Queue)
  4 — Installed    package-variant-plus (replaces old Install)
  5 — Load Order   format-list-numbered

A persistent warning bar is shown at the top when UE4SS is not detected.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.core.text import Label as CoreLabel
from kivy.metrics import dp, sp
from kivy.properties import NumericProperty, ColorProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.tab import MDTabsPrimary, MDTabsCarousel, MDTabsItem, MDTabsItemIcon, MDTabsItemText

from ...gui.widgets.plugin_panel import PluginPanel

from .shared.ui.tabs.registries_tab import RegistriesTab
from .shared.ui.tabs.content.content_tab import ContentTab
from .shared.ui.tabs.downloads.downloads_tab import DownloadsTab
from .shared.ui.tabs.install.install_tab import InstalledTab
from .shared.ui.tabs.load_order_tab import LoadOrderTab

if TYPE_CHECKING:
    from ...core.config import GameProfile


_TABS = [
    ("Registries",  "database-search"),
    ("Content",     "layers-search"),
    ("Downloads",   "tray-arrow-down"),
    ("Installed",   "package-variant-plus"),
    ("Load Order",  "format-list-numbered"),
]

# Tab indices (0-based)
_TAB_REGISTRIES = 0
_TAB_CONTENT    = 1
_TAB_DOWNLOADS  = 2
_TAB_INSTALLED  = 3
_TAB_LOAD_ORDER = 4


_COL_BADGE_NEUTRAL = (0.45, 0.55, 0.75, 1.0)
_COL_BADGE_RED     = (1.0,  0.3,  0.3,  1.0)
_COL_BADGE_BLUE    = (0.25, 0.55, 1.0,  1.0)


class _BadgeIcon(MDTabsItemIcon):
    """Tab icon that renders a circular badge overlay using canvas.after.

    Supports an optional secondary badge (top-left of icon) drawn alongside
    the primary badge (top-right).  Use update_secondary() to manage it.
    """

    badge_count = NumericProperty(0)
    badge_color = ColorProperty(list(_COL_BADGE_NEUTRAL))
    _secondary_count: int = 0
    _secondary_color: tuple = _COL_BADGE_BLUE

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(
            badge_count=self._redraw,
            badge_color=self._redraw,
            pos=self._redraw,
            size=self._redraw,
        )

    def update(self, count: int, color: tuple = None) -> None:
        if color is not None:
            self.badge_color = list(color)
        self.badge_count = count

    def update_secondary(self, count: int, color: tuple = None) -> None:
        self._secondary_count = count
        if color is not None:
            self._secondary_color = color
        self._redraw()

    def _draw_badge(self, bx: float, by: float, bs: float, color: tuple, text: str) -> None:
        with self.canvas.after:
            Color(*color)
            RoundedRectangle(pos=(bx - bs / 2, by - bs / 2), size=(bs, bs), radius=[bs / 2])
        lbl = CoreLabel(text=text, font_size=sp(8), bold=True)
        lbl.refresh()
        tex = lbl.texture
        if tex:
            tw, th = tex.size
            with self.canvas.after:
                Color(1, 1, 1, 1)
                Rectangle(texture=tex, pos=(bx - tw / 2, by - th / 2), size=(tw, th))

    def _redraw(self, *_args) -> None:
        self.canvas.after.clear()
        bs = dp(14)
        # Primary badge — top-right of icon
        if self.badge_count > 0:
            bx = self.center_x + dp(9)
            by = self.center_y + dp(9)
            self._draw_badge(bx, by, bs, tuple(self.badge_color), str(min(self.badge_count, 99)))
        # Secondary badge — top-left of icon (updates indicator)
        if self._secondary_count > 0:
            bx2 = self.center_x - dp(9)
            by2 = self.center_y + dp(9)
            self._draw_badge(bx2, by2, bs, self._secondary_color, str(min(self._secondary_count, 99)))


class ContentPipelinePanel(PluginPanel):
    """5-tab Mods hub panel."""

    def __init__(self, host, **kwargs):
        super().__init__(host=host, **kwargs)
        self._profile: Optional["GameProfile"] = None
        self._detection = None
        self._fw_conflict: list = []
        self._fw_dir = None

        self._warning_bar: Optional[MDBoxLayout] = None
        self._warning_bar_icon: Optional[MDIcon] = None
        self._warning_bar_lbl: Optional[MDLabel] = None
        self._tab_registries: Optional[RegistriesTab] = None
        self._tab_content: Optional[ContentTab] = None
        self._tab_downloads: Optional[DownloadsTab] = None
        self._tab_installed: Optional[InstalledTab] = None
        self._tab_load_order: Optional[LoadOrderTab] = None

        # Badge refs — updated in _update_badges()
        self._badge_content: Optional[_BadgeIcon] = None
        self._badge_downloads: Optional[_BadgeIcon] = None
        self._badge_installed: Optional[_BadgeIcon] = None
        self._badge_load_order: Optional[_BadgeIcon] = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Persistent UE4SS warning bar — hidden until we know UE4SS status.
        self._warning_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(36),
            padding=[dp(12), 0],
            spacing=dp(8),
            md_bg_color=(0.18, 0.14, 0.06, 1),
        )
        self._warning_bar_icon = MDIcon(
            icon="alert",
            size_hint=(None, 1),
            width=dp(24),
            theme_text_color="Custom",
            text_color=(0.9, 0.6, 0.1, 1),
        )
        self._warning_bar_lbl = MDLabel(
            text="UE4SS not detected — install and deploy are unavailable",
            size_hint=(1, 1),
            theme_text_color="Custom",
            text_color=(0.9, 0.6, 0.1, 1),
        )
        self._warning_bar.add_widget(self._warning_bar_icon)
        self._warning_bar.add_widget(self._warning_bar_lbl)
        self._warning_bar.opacity = 0
        self._warning_bar.height = 0
        self.add_widget(self._warning_bar)

        # Tab bar — MDTabsPrimary collapses to its own natural height.
        tabs = MDTabsPrimary()
        for label, icon in _TABS:
            if label == "Content":
                badge_icon = _BadgeIcon(icon=icon)
                self._badge_content = badge_icon
                tabs.add_widget(MDTabsItem(badge_icon, MDTabsItemText(text=label)))
            elif label == "Downloads":
                badge_icon = _BadgeIcon(icon=icon)
                self._badge_downloads = badge_icon
                tabs.add_widget(MDTabsItem(badge_icon, MDTabsItemText(text=label)))
            elif label == "Installed":
                badge_icon = _BadgeIcon(icon=icon)
                self._badge_installed = badge_icon
                tabs.add_widget(MDTabsItem(badge_icon, MDTabsItemText(text=label)))
            elif label == "Load Order":
                badge_icon = _BadgeIcon(icon=icon)
                self._badge_load_order = badge_icon
                tabs.add_widget(MDTabsItem(badge_icon, MDTabsItemText(text=label)))
            else:
                tabs.add_widget(MDTabsItem(
                    MDTabsItemIcon(icon=icon),
                    MDTabsItemText(text=label),
                ))

        # Carousel — sibling to tabs, fills remaining vertical space.
        carousel = MDTabsCarousel(size_hint=(1, 1))

        # Wire carousel ↔ tabs (mirrors MDTabsPrimary internal setup).
        tabs._tabs_carousel = carousel
        carousel._tabs = tabs
        carousel.bind(_offset=tabs.android_animation, index=tabs.on_carousel_index)
        carousel.bind(index=self._on_tab_index_changed)

        # Instantiate tab content widgets and add to carousel.
        self._tab_registries = RegistriesTab(
            host=self.host,
            on_registry_changed=self._refresh_content_tab,
        )
        self._tab_content = ContentTab(
            host=self.host,
            on_queue=self._on_mods_queued,
        )
        self._tab_downloads = DownloadsTab(
            host=self.host,
            on_switch_to_installed=self._switch_to_installed,
        )
        self._tab_installed = InstalledTab(host=self.host)
        self._tab_load_order = LoadOrderTab(host=self.host)

        carousel.add_widget(self._tab_registries)
        carousel.add_widget(self._tab_content)
        carousel.add_widget(self._tab_downloads)
        carousel.add_widget(self._tab_installed)
        carousel.add_widget(self._tab_load_order)

        self._carousel = carousel
        self.add_widget(tabs)
        self.add_widget(MDDivider())
        self.add_widget(carousel)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_activate(self, game_profile: Optional["GameProfile"]) -> None:
        self._profile = game_profile
        self._detection = self.host.get_detection()
        # Notify RegistryService of the new game context so it clears stale cache.
        if self.host.has_service("registry"):
            self.host.get_service("registry").on_game_changed(game_profile)
        # Detect framework mod state (conflict / present / absent)
        self._refresh_framework_state()
        self._update_warning_bar()
        self._refresh_all()

    def on_deactivate(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ue4ss_detected(self) -> bool:
        return bool(self._detection and self._detection.valid)

    def _refresh_framework_state(self) -> None:
        """Query mod_service for framework mod state; store for use across tabs."""
        mods_svc = self.host.get_service("mods") if self._ue4ss_detected() else None
        if mods_svc:
            self._fw_conflict = mods_svc.get_framework_mod_conflict()
            self._fw_dir = mods_svc.get_framework_mod_dir()
        else:
            self._fw_conflict = []
            self._fw_dir = None

    def _update_warning_bar(self) -> None:
        ue4ss_ok = self._ue4ss_detected()
        if self._fw_conflict:
            names = ", ".join(
                p.name if hasattr(p, "name") else str(p) for p in self._fw_conflict
            )
            self._warning_bar_icon.icon = "alert-octagon"
            self._warning_bar_icon.text_color = (1.0, 0.3, 0.3, 1)
            self._warning_bar_lbl.text = (
                f"Multiple framework mods detected for '{self._game_id()}' — "
                f"resolve the conflict before managing mods.  Conflicting: {names}"
            )
            self._warning_bar_lbl.text_color = (1.0, 0.5, 0.5, 1)
            self._warning_bar.md_bg_color = (0.22, 0.06, 0.06, 1)
            self._warning_bar.opacity = 1
            self._warning_bar.height = dp(48)
        elif not ue4ss_ok:
            self._warning_bar_icon.icon = "alert"
            self._warning_bar_icon.text_color = (0.9, 0.6, 0.1, 1)
            self._warning_bar_lbl.text = "UE4SS not detected — install and deploy are unavailable"
            self._warning_bar_lbl.text_color = (0.9, 0.6, 0.1, 1)
            self._warning_bar.md_bg_color = (0.18, 0.14, 0.06, 1)
            self._warning_bar.opacity = 1
            self._warning_bar.height = dp(36)
        elif ue4ss_ok and self._fw_dir is None:
            self._warning_bar_icon.icon = "alert"
            self._warning_bar_icon.text_color = (0.9, 0.6, 0.1, 1)
            self._warning_bar_lbl.text = (
                "Framework mod not installed — Templates and Mods cannot be deployed."
            )
            self._warning_bar_lbl.text_color = (0.9, 0.6, 0.1, 1)
            self._warning_bar.md_bg_color = (0.18, 0.14, 0.06, 1)
            self._warning_bar.opacity = 1
            self._warning_bar.height = dp(36)
        else:
            self._warning_bar.opacity = 0
            self._warning_bar.height = 0

    def _refresh_all(self) -> None:
        game_id = self._game_id()
        ue4ss_ok = self._ue4ss_detected()

        if self._tab_registries:
            self._tab_registries.refresh(game_id, ue4ss_detected=ue4ss_ok)

        if self._tab_content:
            self._tab_content.refresh(game_id)
            self._tab_content.set_framework_state(ue4ss_ok, self._fw_dir, self._fw_conflict)

        if self._tab_downloads:
            self._tab_downloads.refresh(game_id, detection=self._detection)

        if self._tab_installed:
            if hasattr(self._tab_installed, "set_framework_state"):
                self._tab_installed.set_framework_state(ue4ss_ok, self._fw_dir, self._fw_conflict)
            self._tab_installed.refresh(self._profile, self._detection)

        if self._tab_load_order:
            self._tab_load_order.refresh(self._profile, self._detection)

        self._update_badges()

    def _update_badges(self) -> None:
        """Update tab icon badge counts and colors."""
        if self._badge_content and self._tab_content:
            # Primary RED badge = available content count
            count = self._tab_content.get_available_count()
            self._badge_content.update(count, _COL_BADGE_RED if count else _COL_BADGE_NEUTRAL)
            # Secondary BLUE badge = pending UE4SS / framework binary updates
            update_count = self._count_content_updates()
            self._badge_content.update_secondary(update_count, _COL_BADGE_BLUE)

        if self._badge_downloads and self._tab_downloads:
            count  = self._tab_downloads.get_download_count()
            active = self._tab_downloads.get_active_download_count()
            color  = _COL_BADGE_RED if active > 0 else _COL_BADGE_NEUTRAL
            self._badge_downloads.update(count, color if count else None)

        if self._badge_installed and self._tab_installed:
            result   = self._tab_installed.get_installed_count()
            total    = result[0] if isinstance(result, tuple) else int(result)
            orphaned = result[1] if isinstance(result, tuple) else 0
            color    = _COL_BADGE_RED if orphaned > 0 else _COL_BADGE_NEUTRAL
            self._badge_installed.update(total, color if total else None)

        if self._badge_load_order and self._tab_load_order:
            count = self._tab_load_order.get_error_count()
            color = _COL_BADGE_RED if count > 0 else _COL_BADGE_NEUTRAL
            self._badge_load_order.update(count, color if count else None)

    def _count_content_updates(self) -> int:
        """Return count of pending UE4SS / framework binary updates (content-specific)."""
        if not self.host.has_service("updates"):
            return 0
        updates_svc = self.host.get_service("updates")
        count = 0
        ue4ss = updates_svc.get_update_info("ue4ss")
        if ue4ss and ue4ss.is_update_available:
            count += 1
        framework = updates_svc.get_update_info("framework")
        if framework and framework.is_update_available:
            count += 1
        return count

    def _on_tab_index_changed(self, carousel, index: int) -> None:
        """Triggered whenever the user switches tabs. Re-scans Downloads if stale."""
        if index == _TAB_DOWNLOADS and self._tab_downloads:
            if getattr(self._tab_downloads, "_cache_dirty", False):
                self._tab_downloads._cache_dirty = False
                self._tab_downloads._scan_cache_and_rebuild()

    def mark_downloads_stale(self) -> None:
        """Mark the Downloads tab cache as stale so it re-scans on next activation."""
        if self._tab_downloads:
            self._tab_downloads.mark_stale()
        # If the Downloads tab is currently active, re-scan immediately
        if self._carousel and self._carousel.index == _TAB_DOWNLOADS:
            if self._tab_downloads:
                self._tab_downloads._cache_dirty = False
                self._tab_downloads._scan_cache_and_rebuild()

    def _refresh_content_tab(self) -> None:
        """Called by RegistriesTab whenever the registry list changes."""
        game_id = self._game_id()
        if self._tab_content:
            self._tab_content.refresh(game_id)
        self._update_badges()

    def _on_mods_queued(self, items: list) -> None:
        """Called by ContentTab when user clicks Queue for Download.

        items: list of (mod_obj, category) tuples.
        """
        if self._tab_downloads:
            self._tab_downloads.add_to_queue(items)
        self._update_badges()
        self._switch_to_downloads()

    def _switch_to_downloads(self) -> None:
        if self._carousel:
            self._carousel.index = _TAB_DOWNLOADS

    def _switch_to_installed(self) -> None:
        if self._carousel:
            self._carousel.index = _TAB_INSTALLED
        if self._tab_installed:
            self._tab_installed.refresh(self._profile, self._detection)

    def _game_id(self) -> str:
        """Derive game_id from the registry service or fall back to profile."""
        if self.host.has_service("registry"):
            svc = self.host.get_service("registry")
            gid = svc._get_game_id() if hasattr(svc, "_get_game_id") else ""
            if gid:
                return gid
        if self._profile:
            name = getattr(self._profile, "display_name", None) or getattr(self._profile, "name", "")
            return name.lower().replace(" ", "_") if name else ""
        return ""
