"""
APFManagerApp — KivyMD root application.

Startup sequence:
  1. Load APFConfig from ~/.apf_manager/config.json
  2. Initialize PluginHost
  3. Discover + load plugins from lib/plugins/ and custom_plugins/
  4. Build ScreenManager: GameHubScreen + SettingsScreen
  5. If plugin failures exist → navigate to SettingsScreen (all screens locked)
  6. Otherwise → navigate to home_screen contribution (provided by library plugin)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, FadeTransition
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen

from ..core.config import APFConfig, GameProfile
from ..core.plugin_host import PluginHost
from ..core.ue4ss import UE4SSDetector
from .screens.game_hub import GameHubScreen
from .screens.settings import SettingsScreen


def _builtin_plugins_dir() -> Path:
    """
    Returns the built-in plugins directory.
    In development: tools/apf_manager/plugins/ (relative to this file).
    In frozen build: lib/plugins/ (relative to executable).
    """
    if getattr(sys, "frozen", False):
        # cx_Freeze frozen build
        return Path(sys.executable).parent / "lib" / "plugins"
    else:
        return Path(__file__).parent.parent / "plugins"


def _custom_plugins_dir() -> Path:
    """User-installed plugins: next to the executable (frozen) or ~/.apf_manager/plugins/."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "custom_plugins"
    return Path.home() / ".apf_manager" / "plugins"


class APFManagerApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "APF Manager"
        self._config = APFConfig()
        self._host = PluginHost()
        self._sm: Optional[ScreenManager] = None
        self._game_hub: Optional[GameHubScreen] = None
        self._settings_screen: Optional[SettingsScreen] = None
        self._home_screen: Optional[MDScreen] = None
        self._previous_screen: str = "home"

    # -----------------------------------------------------------------------
    # MDApp lifecycle
    # -----------------------------------------------------------------------

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "BlueGray"
        self.theme_cls.material_style = "M3"

        self._config.load()

        # Load plugins
        builtin = _builtin_plugins_dir()
        custom = _custom_plugins_dir()
        self._host.discover_and_load(
            plugin_dirs=[builtin, custom],
            disabled_ids=self._config.disabled_plugins,
            dev_mode=self._config.is_dev,
        )

        # Wire host callbacks
        self._host.set_navigate_fn(self._navigate_to_game)
        self._host.set_dialog_fn(self._show_dialog)

        # Build screen manager
        self._sm = ScreenManager(transition=FadeTransition(duration=0.15))

        # Build game hub
        self._game_hub = GameHubScreen(host=self._host, config=self._config)
        self._game_hub.populate_panels()
        self._sm.add_widget(self._game_hub)

        # Build settings screen
        self._settings_screen = SettingsScreen(host=self._host, config=self._config)
        self._sm.add_widget(self._settings_screen)

        # Build home screen from library plugin's home_screen contribution
        home_contribs = self._host.get_contributions("home_screen")
        if home_contribs and home_contribs[0].panel_class:
            home_widget = home_contribs[0].panel_class(host=self._host, config=self._config)
            home_screen = MDScreen(name="home")
            home_screen.add_widget(home_widget)
            self._home_screen = home_screen
            self._sm.add_widget(home_screen)
        else:
            # Fallback: simple "no library plugin" placeholder
            placeholder = MDScreen(name="home")
            lbl = MDLabel(
                text="Library plugin not loaded.\nConfigure a game in Settings.",
                halign="center",
            )
            placeholder.add_widget(lbl)
            self._home_screen = placeholder
            self._sm.add_widget(placeholder)

        # Navigate: if any failures → settings (locked); otherwise → home
        if self._host.has_failures:
            self._sm.current = "settings"
            self._settings_screen.refresh()
            # Lock all screens except settings
            self._lock_non_settings_screens()
        else:
            self._sm.current = "home"

        return self._sm

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    def _navigate_to_game(self, profile: GameProfile) -> None:
        from ..core.ue4ss import UE4SSDetector
        detection = UE4SSDetector.detect(profile.game_root)
        self._host.set_game_context(profile, detection)
        self._config.last_game_id = profile.game_id
        self._config.save()
        self._game_hub.activate_for_game(profile)
        self._previous_screen = self._sm.current
        self._sm.current = "game_hub"

    def navigate_to_library(self) -> None:
        self._sm.current = "home"

    def navigate_back(self) -> None:
        if self._sm.current == "settings":
            self._sm.current = self._previous_screen if self._previous_screen != "settings" else "home"
        else:
            self._sm.current = "home"

    # -----------------------------------------------------------------------
    # Dialog dispatcher
    # -----------------------------------------------------------------------

    def _show_dialog(self, dialog_id: str, kwargs: dict) -> None:
        contrib = next(
            (c for c in self._host.get_contributions("dialog") if c.dialog_id == dialog_id),
            None,
        )
        if contrib and contrib.handler:
            contrib.handler(**kwargs)

    # -----------------------------------------------------------------------
    # Plugin failure screen lock
    # -----------------------------------------------------------------------

    def _lock_non_settings_screens(self) -> None:
        """Overlay all non-settings screens with a lock message."""
        for screen in self._sm.screens:
            if screen.name != "settings":
                overlay = MDBoxLayout(
                    orientation="vertical",
                    md_bg_color=(0, 0, 0, 0.75),
                )
                overlay.add_widget(MDLabel(
                    text="Plugin errors detected.\nResolve them in Settings to continue.",
                    halign="center",
                    theme_text_color="Custom",
                    text_color=(1, 0.4, 0.4, 1),
                ))
                screen.add_widget(overlay)
