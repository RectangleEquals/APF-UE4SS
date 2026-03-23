"""
GameHubScreen — the per-game screen.

Layout:
  ┌─ Top bar (game name, hub_action buttons, Settings) ──────────────────────┐
  │                                                                           │
  ├─ NavigationRail (left) ─┬─ PluginPanel host (center) ─────────────────── │
  │  icon per hub_panel     │  active plugin fills this area                 │
  │                         │                                                 │
  └─────────────────────────┴─────────────────────────────────────────────── │
  │  LogPanel (bottom, collapsible)                                           │
  └───────────────────────────────────────────────────────────────────────────┘

The NavigationRail is populated from all registered hub_panel contributions.
"""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING, Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen

from ..widgets.log_panel import LogPanel
from ..widgets.plugin_panel import PluginPanel

if TYPE_CHECKING:
    from ...core.plugin_host import PluginHost, PluginContribution
    from ...core.config import APFConfig, GameProfile


class _NavRailButton(MDIconButton):
    """Icon button for the navigation rail with tooltip label."""

    def __init__(self, label: str, icon: str, on_select, **kwargs):
        super().__init__(icon=icon, **kwargs)
        self._label = label
        self._on_select = on_select
        self.size_hint = (None, None)
        self.size = (dp(48), dp(48))

    def on_release(self):
        self._on_select(self._label)


class GameHubScreen(MDScreen):
    def __init__(self, host: "PluginHost", config: "APFConfig", **kwargs):
        super().__init__(name="game_hub", **kwargs)
        self._host = host
        self._config = config
        self._active_panel: Optional[PluginPanel] = None
        self._panel_map: dict[str, PluginPanel] = {}  # label -> panel instance
        self._nav_buttons: dict[str, _NavRailButton] = {}
        self._log_panel = LogPanel()

        # Wire host log to our panel
        host.set_log_fn(self._log_panel.append)

        self._build()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build(self) -> None:
        root = MDBoxLayout(orientation="vertical")

        # Top bar
        self._top_bar = self._build_top_bar()
        root.add_widget(self._top_bar)

        # Middle: nav rail + panel host
        middle = MDBoxLayout(orientation="horizontal", size_hint_y=1)
        self._nav_rail = self._build_nav_rail()
        middle.add_widget(self._nav_rail)

        self._panel_host = MDBoxLayout(orientation="vertical", size_hint_x=1)
        middle.add_widget(self._panel_host)
        root.add_widget(middle)

        # Log panel (bottom)
        root.add_widget(self._log_panel)

        self.add_widget(root)

    def _build_top_bar(self) -> MDBoxLayout:
        bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="56dp",
            md_bg_color=(0.15, 0.2, 0.25, 1),
            padding=("8dp", 0),
            spacing="4dp",
        )
        # Back button
        back_btn = MDIconButton(
            icon="arrow-left",
            on_release=self._go_home,
        )
        bar.add_widget(back_btn)

        # Game name label
        self._game_name_lbl = MDLabel(
            text="",
            font_style="Headline",
            role="small",
            halign="left",
            size_hint_x=1,
        )
        bar.add_widget(self._game_name_lbl)

        # hub_action buttons placeholder (populated in populate_panels)
        self._action_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_x=None,
            width="0dp",
            spacing="4dp",
        )
        bar.add_widget(self._action_bar)

        # Settings button
        settings_btn = MDIconButton(
            icon="cog",
            on_release=self._go_settings,
        )
        bar.add_widget(settings_btn)
        return bar

    def _build_nav_rail(self) -> MDBoxLayout:
        rail = MDBoxLayout(
            orientation="vertical",
            size_hint_x=None,
            width="56dp",
            md_bg_color=(0.1, 0.1, 0.1, 1),
            padding=(0, "8dp"),
            spacing="4dp",
        )
        self._nav_rail_inner = rail
        return rail

    # -----------------------------------------------------------------------
    # Populate with plugin contributions
    # -----------------------------------------------------------------------

    def populate_panels(self) -> None:
        """Called after plugins are loaded to register all hub_panel contributions."""
        panels = self._host.get_contributions("hub_panel")
        actions = self._host.get_contributions("hub_action")

        # Build nav rail buttons
        for contrib in panels:
            btn = _NavRailButton(
                label=contrib.label,
                icon=contrib.icon or "puzzle",
                on_select=self._select_panel,
            )
            self._nav_buttons[contrib.label] = btn
            self._nav_rail_inner.add_widget(btn)

            # Instantiate the panel
            if contrib.panel_class:
                panel = contrib.panel_class(host=self._host)
                self._panel_map[contrib.label] = panel

        # Build action buttons
        action_width = 0
        for contrib in actions:
            btn = MDIconButton(
                icon=contrib.icon or "lightning-bolt",
                on_release=lambda _, c=contrib: c.handler() if c.handler else None,
            )
            self._action_bar.add_widget(btn)
            action_width += dp(48)
        self._action_bar.width = str(action_width) + "dp"

        # Select first panel
        if panels:
            self._select_panel(panels[0].label)

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    def _select_panel(self, label: str) -> None:
        if self._active_panel is not None:
            self._active_panel.on_deactivate()
            self._panel_host.remove_widget(self._active_panel)

        panel = self._panel_map.get(label)
        if panel is None:
            return

        self._active_panel = panel
        self._panel_host.add_widget(panel)

        profile = self._host.get_game_context()
        if profile:
            panel.on_activate(profile)

    def activate_for_game(self, profile: "GameProfile") -> None:
        """Called when the user navigates to this game."""
        self._game_name_lbl.text = profile.display_name
        if self._active_panel and profile:
            self._active_panel.on_activate(profile)

    def _go_home(self, *_) -> None:
        app = self._get_app()
        if app:
            app.navigate_to_library()

    def _go_settings(self, *_) -> None:
        app = self._get_app()
        if app:
            app.root.current = "settings"

    def _get_app(self):
        from kivymd.app import MDApp
        return MDApp.get_running_app()

    # -----------------------------------------------------------------------
    # Log passthrough
    # -----------------------------------------------------------------------

    @property
    def log_panel(self) -> LogPanel:
        return self._log_panel
