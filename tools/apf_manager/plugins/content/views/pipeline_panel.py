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

from ....core.views.widgets.plugin_panel import PluginPanel

from .tabs.registries import RegistriesTab
from .tabs.content import ContentTab
from .tabs.downloads import DownloadsTab
from .tabs.installed import InstalledTab
from .tabs.load_order import LoadOrderTab

from ..controllers.pipeline import PipelineController

if TYPE_CHECKING:
    from ....core.models.config import GameProfile


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
        self._ctrl = PipelineController(host)

        # Cached framework state (updated on activate + detection change)
        self._fw_state: dict = {
            "ue4ss_ok": False,
            "fw_conflict": [],
            "fw_dir": None,
            "fw_conflict_names": "",
            "detection": None,
        }

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

        # Subscribe to state change notifications
        self.host.subscribe_state_change("install", self._on_install_state_changed)
        self.host.subscribe_state_change("registry", self._on_registry_state_changed)
        # X-4: re-query framework state when detection changes (e.g. after UE4SS install)
        self.host.subscribe_state_change("detection", self._on_detection_state_changed)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_activate(self, game_profile: Optional["GameProfile"]) -> None:
        self._profile = game_profile
        self._ctrl.on_activate(game_profile)
        self._fw_state = self._ctrl.get_framework_state()
        self._update_warning_bar(self._fw_state)
        self._refresh_all()

    def on_deactivate(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Warning bar
    # ------------------------------------------------------------------

    def _update_warning_bar(self, state: dict) -> None:
        ue4ss_ok = state.get("ue4ss_ok", False)
        fw_conflict = state.get("fw_conflict", [])
        fw_conflict_names = state.get("fw_conflict_names", "")

        if fw_conflict:
            game_id = self._ctrl.get_game_id(self._profile)
            self._warning_bar_icon.icon = "alert-octagon"
            self._warning_bar_icon.text_color = (1.0, 0.3, 0.3, 1)
            self._warning_bar_lbl.text = (
                f"Multiple framework mods detected for '{game_id}' — "
                f"resolve the conflict before managing mods.  Conflicting: {fw_conflict_names}"
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
        elif ue4ss_ok and not state.get("fw_dir"):
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

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        game_id = self._ctrl.get_game_id(self._profile)
        ue4ss_ok = self._fw_state.get("ue4ss_ok", False)
        fw_dir = self._fw_state.get("fw_dir")
        fw_conflict = self._fw_state.get("fw_conflict", [])
        detection = self._fw_state.get("detection")

        if self._tab_registries:
            self._tab_registries.refresh(game_id, ue4ss_detected=ue4ss_ok)

        if self._tab_content:
            self._tab_content.refresh(game_id)
            self._tab_content.set_framework_state(ue4ss_ok, fw_dir, fw_conflict)

        if self._tab_downloads:
            self._tab_downloads.refresh(game_id, detection=detection)

        if self._tab_installed:
            if hasattr(self._tab_installed, "set_framework_state"):
                self._tab_installed.set_framework_state(ue4ss_ok, fw_dir, fw_conflict)
            self._tab_installed.refresh(self._profile, detection)

        if self._tab_load_order:
            self._tab_load_order.refresh(self._profile, detection)

        self._update_badges()

    def _update_badges(self) -> None:
        if self._badge_content and self._tab_content:
            count = self._tab_content.get_available_count()
            self._badge_content.update(count, _COL_BADGE_RED if count else _COL_BADGE_NEUTRAL)
            update_count = self._ctrl.count_content_updates()
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

    # ------------------------------------------------------------------
    # Tab callbacks
    # ------------------------------------------------------------------

    def _on_tab_index_changed(self, carousel, index: int) -> None:
        if index == _TAB_DOWNLOADS and self._tab_downloads:
            if getattr(self._tab_downloads, "_cache_dirty", False):
                self._tab_downloads._cache_dirty = False
                self._tab_downloads._scan_cache_and_rebuild()

    def mark_downloads_stale(self) -> None:
        if self._tab_downloads:
            self._tab_downloads.mark_stale()
        if self._carousel and self._carousel.index == _TAB_DOWNLOADS:
            if self._tab_downloads:
                self._tab_downloads._cache_dirty = False
                self._tab_downloads._scan_cache_and_rebuild()

    def _refresh_content_tab(self) -> None:
        game_id = self._ctrl.get_game_id(self._profile)
        if self._tab_content:
            self._tab_content.refresh(game_id)
        self._update_badges()

    def _on_mods_queued(self, items: list) -> None:
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
        detection = self._fw_state.get("detection")
        if self._tab_installed:
            self._tab_installed.refresh(self._profile, detection)

    # ------------------------------------------------------------------
    # State change notifications
    # ------------------------------------------------------------------

    def _on_install_state_changed(self) -> None:
        # Re-query framework state so child tabs receive fresh detection data.
        self._fw_state = self._ctrl.get_framework_state()
        detection = self._fw_state.get("detection")
        if self._tab_load_order:
            self._tab_load_order.refresh(self._profile, detection)
        if self._tab_installed:
            self._tab_installed.refresh(self._profile, detection)
        self._update_badges()

    def _on_registry_state_changed(self) -> None:
        game_id = self._ctrl.get_game_id(self._profile)
        if self._tab_content:
            self._tab_content.refresh(game_id)
        self._update_badges()

    def _on_detection_state_changed(self) -> None:
        """X-4: Re-query framework state after UE4SS install completes."""
        self._fw_state = self._ctrl.get_framework_state()
        self._update_warning_bar(self._fw_state)
