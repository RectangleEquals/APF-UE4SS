"""
SettingsScreen — global settings and plugin management.

Sections:
  - Mode toggle: Player / Dev
  - Plugin Manager: list all plugins, enable/disable, install .apfplugin
  - Steam library path override
  - Restart Required banner (shown after toggling plugins)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.selectioncontrol import MDSwitch

if TYPE_CHECKING:
    from ...core.plugin_host import PluginHost, PluginInfo
    from ...core.config import APFConfig


class SettingsScreen(MDScreen):
    def __init__(self, host: "PluginHost", config: "APFConfig", **kwargs):
        super().__init__(name="settings", **kwargs)
        self._host = host
        self._config = config
        self._restart_needed = False
        self._original_mode = config.mode
        self._original_disabled = set(config.disabled_plugins)
        self._build()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build(self) -> None:
        root = MDBoxLayout(orientation="vertical")

        # Top bar
        bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="56dp",
            md_bg_color=(0.15, 0.2, 0.25, 1),
            padding=("8dp", 0),
        )
        back_btn = MDIconButton(icon="arrow-left", on_release=self._go_back)
        bar.add_widget(back_btn)
        bar.add_widget(MDLabel(text="Settings", font_style="Headline", role="small", halign="left"))
        root.add_widget(bar)

        # Restart required banner (hidden by default)
        self._restart_banner = self._build_restart_banner()
        root.add_widget(self._restart_banner)

        # Scrollable content
        scroll = MDScrollView()
        content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding="16dp",
            spacing="12dp",
        )
        content.bind(minimum_height=content.setter("height"))

        content.add_widget(self._build_mode_section())
        content.add_widget(MDDivider())
        content.add_widget(self._build_plugin_section())
        content.add_widget(MDDivider())
        content.add_widget(self._build_steam_section())

        scroll.add_widget(content)
        root.add_widget(scroll)
        self.add_widget(root)

    def _build_restart_banner(self) -> MDBoxLayout:
        banner = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=0,
            opacity=0,
            md_bg_color=(0.7, 0.1, 0.1, 1),
            padding=("16dp", "4dp"),
            spacing="8dp",
        )
        lbl = MDLabel(
            text="Restart required to apply changes",
            font_style="Label",
            role="small",
            halign="left",
            size_hint_x=1,
        )
        restart_btn = MDButton(
            MDButtonText(text="Restart"),
            style="filled",
            size_hint_x=None,
            width=dp(96),
            on_release=self._restart_app,
        )
        banner.add_widget(lbl)
        banner.add_widget(restart_btn)
        self._restart_banner_widget = banner
        return banner

    def _build_mode_section(self) -> MDBoxLayout:
        section = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height="80dp",
            spacing="4dp",
        )
        section.add_widget(MDLabel(text="Mode", font_style="Title",
                                   role="large",
                                   size_hint_y=None, height="28dp"))
        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height="40dp", spacing="8dp")
        player_lbl = MDLabel(text="Player", size_hint_x=None, width="60dp")
        switch = MDSwitch()
        switch.active = (self._config.mode == "dev")
        switch.bind(active=self._on_mode_toggle)
        dev_lbl = MDLabel(text="Dev", size_hint_x=None, width="40dp")
        row.add_widget(player_lbl)
        row.add_widget(switch)
        row.add_widget(dev_lbl)
        section.add_widget(row)
        return section

    def _build_plugin_section(self) -> MDBoxLayout:
        section = MDBoxLayout(orientation="vertical", size_hint_y=None, spacing="4dp")
        section.add_widget(MDLabel(
            text="Plugins",
            font_style="Title",
            role="large",
            size_hint_y=None,
            height="28dp",
        ))

        self._plugin_list_box = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing="2dp",
        )
        self._plugin_list_box.bind(minimum_height=self._plugin_list_box.setter("height"))
        self._refresh_plugin_list()
        section.add_widget(self._plugin_list_box)
        section.bind(minimum_height=section.setter("height"))

        # Install plugin button
        install_btn = MDButton(
            MDButtonText(text="Install .apfplugin…"),
            style="text",
            size_hint_y=None,
            height="40dp",
            on_release=self._install_plugin,
        )
        section.add_widget(install_btn)
        return section

    def _build_steam_section(self) -> MDBoxLayout:
        section = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height="80dp",
            spacing="4dp",
        )
        section.add_widget(MDLabel(
            text="Steam Library",
            font_style="Title",
            role="large",
            size_hint_y=None,
            height="28dp",
        ))
        override = self._config.steam_library_override or ""
        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height="40dp", spacing="8dp")
        from kivymd.uix.textfield import MDTextField
        self._steam_path_field = MDTextField(
            text=override,
            hint_text="libraryfolders.vdf path (leave blank for auto-detect)",
            size_hint_x=1,
        )
        save_btn = MDButton(
            MDButtonText(text="Save"),
            style="text",
            size_hint_x=None,
            width=dp(60),
            on_release=self._save_steam_override,
        )
        row.add_widget(self._steam_path_field)
        row.add_widget(save_btn)
        section.add_widget(row)
        return section

    # -----------------------------------------------------------------------
    # Plugin list
    # -----------------------------------------------------------------------

    def _refresh_plugin_list(self) -> None:
        self._plugin_list_box.clear_widgets()
        for info in self._host.get_all_plugins():
            self._plugin_list_box.add_widget(self._make_plugin_row(info))

    def _make_plugin_row(self, info: "PluginInfo") -> MDBoxLayout:
        is_failed = info.status == "failed"
        is_disabled = info.plugin_id in self._config.disabled_plugins

        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="48dp",
            padding=("8dp", 0),
            spacing="8dp",
            md_bg_color=(0.3, 0.05, 0.05, 1) if is_failed else (0.12, 0.12, 0.12, 1),
        )

        # Status icon
        icon = "alert-circle" if is_failed else ("toggle-switch-off" if is_disabled else "puzzle-check")
        icon_color = (1, 0.3, 0.3, 1) if is_failed else (0.7, 0.7, 0.7, 1)
        row.add_widget(MDIconButton(
            icon=icon,
            theme_icon_color="Custom",
            icon_color=icon_color,
            size_hint_x=None,
            width=dp(40),
            disabled=True,
        ))

        # Name + version + error
        info_box = MDBoxLayout(orientation="vertical", size_hint_x=1)
        info_box.add_widget(MDLabel(
            text=f"{info.name}  v{info.version}  [{info.mode}]",
            font_style="Body",
            size_hint_y=None,
            height="22dp",
        ))
        if is_failed and info.error:
            info_box.add_widget(MDLabel(
                text=info.error,
                font_style="Label",
            role="small",
                theme_text_color="Custom",
                text_color=(1, 0.5, 0.5, 1),
                size_hint_y=None,
                height="18dp",
            ))
        row.add_widget(info_box)

        # Enable/disable toggle (can't disable built-in required plugins)
        switch = MDSwitch()
        switch.active = not is_disabled
        switch.bind(active=lambda _, val, pid=info.plugin_id: self._on_plugin_toggle(pid, val))
        row.add_widget(switch)

        return row

    # -----------------------------------------------------------------------
    # Callbacks
    # -----------------------------------------------------------------------

    def _on_mode_toggle(self, widget, value: bool) -> None:
        self._config.mode = "dev" if value else "player"
        self._config.save()
        self._update_restart_banner()

    def _on_plugin_toggle(self, plugin_id: str, enabled: bool) -> None:
        self._config.set_plugin_disabled(plugin_id, not enabled)
        self._update_restart_banner()
        self._refresh_plugin_list()

    def _update_restart_banner(self) -> None:
        dirty = (
            self._config.mode != self._original_mode
            or set(self._config.disabled_plugins) != self._original_disabled
        )
        if dirty and not self._restart_needed:
            self._restart_needed = True
            self._restart_banner_widget.height = dp(44)
            self._restart_banner_widget.opacity = 1
        elif not dirty and self._restart_needed:
            self._restart_needed = False
            self._restart_banner_widget.height = 0
            self._restart_banner_widget.opacity = 0

    def _restart_app(self, *_) -> None:
        """Close and relaunch the application."""
        python = sys.executable
        os.execv(python, [python] + sys.argv)

    def _save_steam_override(self, *_) -> None:
        val = self._steam_path_field.text.strip() or None
        self._config.steam_library_override = val
        self._config.save()

    def _install_plugin(self, *_) -> None:
        # TODO: file picker for .apfplugin — implement with plyer or kivy FileChooser
        pass

    def _go_back(self, *_) -> None:
        from kivymd.app import MDApp
        app = MDApp.get_running_app()
        if app and hasattr(app, "navigate_back"):
            app.navigate_back()

    def refresh(self) -> None:
        """Called when screen is shown — refresh plugin list."""
        self._refresh_plugin_list()
