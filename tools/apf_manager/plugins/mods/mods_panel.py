"""
ModsPanel — 6-tab hub panel for apf.builtin.mods.

Tabs (in order):
  1 — Registries   database-search
  2 — Templates    puzzle-outline
  3 — Mods         magnify
  4 — Queue        tray-arrow-down
  5 — Deploy       rocket-launch
  6 — Load Order   format-list-numbered

A persistent warning bar is shown at the top when UE4SS is not detected.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.tab import MDTabsPrimary, MDTabsCarousel, MDTabsItem, MDTabsItemIcon, MDTabsItemText

from ...gui.widgets.plugin_panel import PluginPanel

from .tabs.registries_tab import RegistriesTab
from .tabs.templates_tab import TemplatesTab
from .tabs.mods_tab import ModsTab
from .tabs.queue_tab import QueueTab
from .tabs.deploy_tab import DeployTab
from .tabs.load_order_tab import LoadOrderTab

if TYPE_CHECKING:
    from ...core.config import GameProfile


_TABS = [
    ("Registries",  "database-search"),
    ("Templates",   "puzzle-outline"),
    ("Mods",        "magnify"),
    ("Queue",       "tray-arrow-down"),
    ("Deploy",      "rocket-launch"),
    ("Load Order",  "format-list-numbered"),
]


class ModsPanel(PluginPanel):
    """6-tab Mods hub panel."""

    def __init__(self, host, **kwargs):
        super().__init__(host=host, **kwargs)
        self._profile: Optional["GameProfile"] = None
        self._detection = None

        self._warning_bar: Optional[MDBoxLayout] = None
        self._warning_bar_icon: Optional[MDIcon] = None
        self._warning_bar_lbl: Optional[MDLabel] = None
        self._tab_registries: Optional[RegistriesTab] = None
        self._tab_templates: Optional[TemplatesTab] = None
        self._tab_mods: Optional[ModsTab] = None
        self._tab_queue: Optional[QueueTab] = None
        self._tab_deploy: Optional[DeployTab] = None
        self._tab_load_order: Optional[LoadOrderTab] = None

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

        # Instantiate tab content widgets and add to carousel.
        self._tab_registries = RegistriesTab(host=self.host, on_registry_changed=self._refresh_other_tabs)
        self._tab_templates = TemplatesTab(host=self.host)
        self._tab_mods = ModsTab(host=self.host)
        self._tab_queue = QueueTab(host=self.host)
        self._tab_deploy = DeployTab(host=self.host)
        self._tab_load_order = LoadOrderTab(host=self.host)

        carousel.add_widget(self._tab_registries)
        carousel.add_widget(self._tab_templates)
        carousel.add_widget(self._tab_mods)
        carousel.add_widget(self._tab_queue)
        carousel.add_widget(self._tab_deploy)
        carousel.add_widget(self._tab_load_order)

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
        self._update_warning_bar()
        self._refresh_all()

    def on_deactivate(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ue4ss_detected(self) -> bool:
        return bool(self._detection and self._detection.valid)

    def _update_warning_bar(self) -> None:
        if not self._ue4ss_detected():
            self._warning_bar.opacity = 1
            self._warning_bar.height = dp(36)
        else:
            self._warning_bar.opacity = 0
            self._warning_bar.height = 0

    def _refresh_all(self) -> None:
        game_id = self._game_id()

        # Registries tab always gets the full profile context.
        if self._tab_registries:
            self._tab_registries.refresh(game_id, ue4ss_detected=self._ue4ss_detected())

        # Templates and Mods require a game_id to filter.
        if self._tab_templates:
            self._tab_templates.refresh(game_id)

        if self._tab_mods:
            self._tab_mods.refresh(game_id)

        # Queue is driven by staged state (game_id for validation).
        if self._tab_queue:
            self._tab_queue.refresh(game_id)

        # Deploy and Load Order need profile + detection.
        if self._tab_deploy:
            self._tab_deploy.refresh(self._profile, self._detection)

        if self._tab_load_order:
            self._tab_load_order.refresh(self._profile, self._detection)

    def _refresh_other_tabs(self) -> None:
        """Called by RegistriesTab whenever the registry list changes."""
        game_id = self._game_id()
        if self._tab_templates:
            self._tab_templates.refresh(game_id)
        if self._tab_mods:
            self._tab_mods.refresh(game_id)
        if self._tab_queue:
            self._tab_queue.refresh(game_id)

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
