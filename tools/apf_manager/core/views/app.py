"""
APFManagerApp — KivyMD root application (view layer).

Startup sequence:
  1. AppController loads APFConfig and discovers/loads plugins
  2. Build ScreenManager: GameHubScreen + SettingsScreen + home screen
  3. If plugin failures exist → navigate to SettingsScreen (all screens locked)
  4. Otherwise → navigate to home_screen contribution (provided by library plugin)
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

from .screens.game_hub import GameHubScreen
from .screens.settings import SettingsScreen


class APFManagerApp(MDApp):
    def __init__(self, devtools_mode: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._devtools_mode = devtools_mode
        try:
            from ...__version__ import __version__, __build_id__, __is_dev__
        except Exception:
            __version__, __build_id__, __is_dev__ = "?.?.?", "dev", True
        self.title = (
            f"APF Manager v{__version__} ({__build_id__})"
            if __is_dev__
            else f"APF Manager v{__version__}"
        )
        from ..controllers.app import AppController
        self._ctrl = AppController(devtools_mode=devtools_mode)
        self._sm: Optional[ScreenManager] = None
        self._game_hub: Optional[GameHubScreen] = None
        self._settings_screen: Optional[SettingsScreen] = None
        self._home_screen: Optional[MDScreen] = None
        self._previous_screen: str = "home"
        self._screens_locked: bool = False
        self._is_maximized: bool = False

    # -----------------------------------------------------------------------
    # MDApp lifecycle
    # -----------------------------------------------------------------------

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "#607D8B"  # Blue Grey 500

        host = self._ctrl.host
        config = self._ctrl.config

        from ..controllers.logging.manager import APFLogManager
        from ..models.logging.config import LogConfig
        APFLogManager.setup(LogConfig(dev_mode=host.dev_mode))

        # Controller loads config and plugins
        self._ctrl.startup(
            navigate_fn=self._navigate_to_game,
            dialog_fn=self._show_dialog,
            failure_fn=self._on_runtime_failure,
        )

        # Build screen manager
        self._sm = ScreenManager(transition=FadeTransition(duration=0.15))

        # Build game hub
        self._game_hub = GameHubScreen(host=host, config=config)
        APFLogManager.attach_panel(self._game_hub.log_panel.append)
        self._game_hub.populate_panels()
        self._sm.add_widget(self._game_hub)

        # Build settings screen
        self._settings_screen = SettingsScreen(host=host, config=config)
        self._sm.add_widget(self._settings_screen)

        # Build home screen from library plugin's home_screen contribution
        home_contribs = host.get_contributions("home_screen")
        if home_contribs and home_contribs[0].panel_class:
            home_widget = home_contribs[0].panel_class(host=host, config=config)
            home_screen = MDScreen(name="home")
            home_screen.add_widget(home_widget)
            self._home_screen = home_screen
            self._sm.add_widget(home_screen)
        else:
            # Fallback: simple "no library plugin" placeholder
            placeholder = MDScreen(name="home")
            lbl = MDLabel(
                text="No game library available.\nEnable the Library plugin in Settings.",
                halign="center",
            )
            placeholder.add_widget(lbl)
            self._home_screen = placeholder
            self._sm.add_widget(placeholder)

        # Restore window size and position
        from kivy.core.window import Window
        Window.minimum_width = 900
        Window.minimum_height = 600

        w = max(config.window_width, 900)
        h = max(config.window_height, 600)
        Window.size = (w, h)

        if not config.window_maximized:
            import ctypes
            screen_w = ctypes.windll.user32.GetSystemMetrics(0)
            screen_h = ctypes.windll.user32.GetSystemMetrics(1)
            Window.left = (screen_w - w) // 2
            Window.top = (screen_h - h) // 2

        Window.bind(on_maximize=self._on_window_maximize)
        Window.bind(on_restore=self._on_window_restore)

        if config.window_maximized:
            Window.maximize()

        # Navigate: if any failures OR no home screen → settings (locked); otherwise → home
        if host.has_failures or not home_contribs:
            for info in host.get_all_plugins():
                if info.status == "failed" and info.error != "Disabled by user.":
                    print(f"[APFManager] Plugin load failure: '{info.name}' — {info.error}", file=sys.stderr)
            self._sm.current = "settings"
            self._settings_screen.refresh()
            self._lock_non_settings_screens()
        else:
            self._sm.current = "home"

        return self._sm

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    def _navigate_to_game(self, profile) -> None:
        self._ctrl.navigate_to_game(profile)
        self._game_hub.activate_for_game(profile)
        self._previous_screen = self._sm.current
        self._sm.current = "game_hub"

    def navigate_to_library(self) -> None:
        self._sm.current = "home"

    def on_stop(self) -> None:
        from kivy.core.window import Window
        config = self._ctrl.config
        config.window_maximized = self._is_maximized
        if not self._is_maximized:
            config.window_width = max(Window.width, 900)
            config.window_height = max(Window.height, 600)
        config.save()

    def _on_window_maximize(self, window) -> None:
        self._is_maximized = True

    def _on_window_restore(self, window) -> None:
        self._is_maximized = False

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
            (c for c in self._ctrl.host.get_contributions("dialog") if c.dialog_id == dialog_id),
            None,
        )
        if contrib and contrib.handler:
            contrib.handler(**kwargs)

    # -----------------------------------------------------------------------
    # Plugin failure screen lock
    # -----------------------------------------------------------------------

    def _on_runtime_failure(self) -> None:
        Clock.schedule_once(lambda dt: self._handle_runtime_failure(), 0)

    def _handle_runtime_failure(self) -> None:
        self._settings_screen.refresh()
        if not self._screens_locked:
            self._lock_non_settings_screens()
        self._sm.current = "settings"

    def _lock_non_settings_screens(self) -> None:
        """Overlay all non-settings screens with a lock message and navigation to Settings."""
        if self._screens_locked:
            return
        self._screens_locked = True

        from kivy.metrics import dp
        from kivy.uix.widget import Widget
        from kivymd.uix.button import MDIconButton, MDButton, MDButtonText

        def _go_settings(*_):
            self._sm.current = "settings"

        for screen in self._sm.screens:
            if screen.name != "settings":
                overlay = MDBoxLayout(
                    orientation="vertical",
                    md_bg_color=(0, 0, 0, 0.85),
                )
                # Top bar with settings cog
                top_bar = MDBoxLayout(
                    orientation="horizontal",
                    size_hint_y=None,
                    height=dp(48),
                    padding=[dp(8), 0],
                )
                top_bar.add_widget(Widget())
                top_bar.add_widget(MDIconButton(icon="cog", on_release=_go_settings))
                overlay.add_widget(top_bar)

                # Non-clickable error heading
                overlay.add_widget(MDLabel(
                    text="Plugin errors detected.",
                    halign="center",
                    theme_text_color="Custom",
                    text_color=(1, 0.4, 0.4, 1),
                    size_hint_y=None,
                    height=dp(40),
                ))

                # Clickable resolve link (centered)
                resolve_btn = MDButton(
                    MDButtonText(text="Resolve them in Settings to continue."),
                    style="text",
                    size_hint_y=None,
                    height=dp(40),
                    on_release=_go_settings,
                )
                btn_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40))
                btn_row.add_widget(Widget())
                btn_row.add_widget(resolve_btn)
                btn_row.add_widget(Widget())
                overlay.add_widget(btn_row)
                overlay.add_widget(Widget())  # bottom spacer

                screen.add_widget(overlay)
