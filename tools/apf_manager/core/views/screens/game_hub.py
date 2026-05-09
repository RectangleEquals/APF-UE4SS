"""
GameHubScreen — the per-game screen (view layer).

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
Business logic is delegated to GameHubController.
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.screen import MDScreen

from ..logging.log_panel import LogPanel
from ..widgets.plugin_panel import PluginPanel
from ..widgets.tip_icon_button import TipIconButton, ImageIconButton

if TYPE_CHECKING:
    from ...controllers.plugin_host import PluginHost, PluginContribution
    from ...models.config import APFConfig, GameProfile
    from ...models.ue.result import DetectionResult

_HERE = Path(__file__).parent
_DISCORD_ICON = (
    Path(sys.executable).parent / "data" / "Discord_Symbol_White.png"
    if getattr(sys, "frozen", False)
    else _HERE.parent.parent.parent / "data" / "Discord_Symbol_White.png"
)
# game_hub.py is in core/views/screens/ which is INSIDE library.zip in frozen builds.
# __file__ is a zip path in frozen mode; use sys.executable instead.
# Dev: _HERE.parent.parent.parent = apf_manager/ → data/  ✓
# Frozen: exe_dir/data/  ✓


class _NavRailButton(ButtonBehavior, MDBoxLayout):
    """Vertical icon + label button for the navigation rail.

    The entire container is the clickable region (via ButtonBehavior).
    The inner MDIcon is non-interactive; touch events bubble up to this widget.
    Label is always visible; selection is indicated by background color on outer container.
    """

    def __init__(self, label: str, icon: str, on_select, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(56),
            padding=[dp(8), dp(6)],
            spacing=dp(4),
            radius=[dp(8)],
            **kwargs,
        )
        self._nav_label = label
        self.bind(on_release=lambda *_: on_select(label))

        # AnchorLayout centers MDIcon regardless of adaptive_size overriding size_hint
        from kivy.uix.anchorlayout import AnchorLayout
        icon_anchor = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(1, 1))
        self._icon = MDIcon(icon=icon)
        icon_anchor.add_widget(self._icon)

        self._lbl = MDLabel(
            text=label,
            font_style="Label",
            role="small",
            halign="center",
            size_hint=(1, None),
            height=dp(14),
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        )
        self.add_widget(icon_anchor)
        self.add_widget(self._lbl)

    def set_selected(self, selected: bool) -> None:
        # Background covers the entire button; label always visible
        self.md_bg_color = (0.2, 0.28, 0.4, 1) if selected else (0, 0, 0, 0)


class GameHubScreen(MDScreen):
    def __init__(self, host: "PluginHost", config: "APFConfig", **kwargs):
        super().__init__(name="game_hub", **kwargs)
        self._host = host
        self._config = config
        self._active_panel: Optional[PluginPanel] = None
        self._panel_map: dict[str, PluginPanel] = {}  # label -> panel instance
        self._nav_buttons: dict[str, _NavRailButton] = {}
        self._log_panel = LogPanel()
        self._current_profile: Optional["GameProfile"] = None
        self._pending_nav_label: Optional[str] = None

        from ...controllers.screens.game_hub import GameHubController
        self._ctrl = GameHubController(host)

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
        back_btn = TipIconButton(
            icon="arrow-left",
            tooltip_text="Back to library",
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

        # Remove game button — before action bar so fixed buttons stay right-anchored
        remove_btn = TipIconButton(
            icon="trash-can-outline",
            tooltip_text="Remove game",
            on_release=lambda *_: self._on_remove_game(),
        )
        bar.add_widget(remove_btn)

        # hub_action buttons placeholder (populated in populate_panels)
        self._action_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_x=None,
            adaptive_width=True,
            spacing="4dp",
        )
        bar.add_widget(self._action_bar)

        # Discord button — just before settings, consistent with LibraryScreen
        if _DISCORD_ICON.exists():
            discord_btn = ImageIconButton(source=str(_DISCORD_ICON), tooltip_text="Join our Discord")
            discord_btn.bind(on_release=lambda *_: webbrowser.open("https://discord.gg/xhcVRhnjK"))
            bar.add_widget(discord_btn)

        # Settings button
        settings_btn = TipIconButton(
            icon="cog",
            tooltip_text="Settings",
            on_release=self._go_settings,
        )
        bar.add_widget(settings_btn)
        return bar

    def _build_nav_rail(self) -> MDBoxLayout:
        rail = MDBoxLayout(
            orientation="vertical",
            size_hint_x=None,
            width="88dp",
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
                contrib.panel_instance = panel

        # Build action buttons — width handled automatically by adaptive_width=True
        for contrib in actions:
            btn = MDIconButton(
                icon=contrib.icon or "lightning-bolt",
                on_release=lambda _, c=contrib: c.handler() if c.handler else None,
            )
            self._action_bar.add_widget(btn)

        # Select first panel
        if panels:
            self._select_panel(panels[0].label)

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    def _select_panel(self, label: str) -> None:
        if self._active_panel is not None:
            # No-op if already on this panel
            active_label = next(
                (l for l, p in self._panel_map.items() if p is self._active_panel), None
            )
            if label == active_label:
                return
            if not self._active_panel.can_deactivate():
                self._pending_nav_label = label  # panel will call _trigger_pending_nav on resolve
                return
            self._active_panel.on_deactivate()
            self._panel_host.remove_widget(self._active_panel)

        panel = self._panel_map.get(label)
        if panel is None:
            return

        self._active_panel = panel
        self._panel_host.add_widget(panel)

        # Update nav rail selection indicator
        for btn_label, btn in self._nav_buttons.items():
            btn.set_selected(btn_label == label)

        profile = self._host.get_game_context()
        if profile:
            panel.on_activate(profile)

    def activate_for_game(self, profile: "GameProfile") -> None:
        """Called when the user navigates to this game. Updates UI only — no detection cache."""
        self._current_profile = profile
        self._game_name_lbl.text = profile.display_name
        if self._active_panel and profile:
            self._active_panel.on_activate(profile)

    # -----------------------------------------------------------------------
    # Remove game — delegates to controller
    # -----------------------------------------------------------------------

    def _on_remove_game(self) -> None:
        if not self._current_profile:
            return
        self._show_remove_checklist(self._current_profile)

    def _show_remove_checklist(self, profile: "GameProfile") -> None:
        from kivymd.uix.button import MDButton, MDButtonText
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText,
            MDDialogContentContainer, MDDialogButtonContainer,
        )
        from kivymd.uix.selectioncontrol import MDSwitch
        from kivy.uix.widget import Widget

        # Use current detection state for UI availability checks only
        detection = self._host.get_detection()

        is_steam_game = bool(getattr(profile, "steam_app_id", None))

        # Determine which options are available
        has_mods_svc = self._host.has_service("mods")
        has_sessions_svc = self._host.has_service("sessions")
        has_ue4ss = (
            detection is not None
            and detection.ue4ss is not None
            and detection.ue4ss.ue4ss_dir is not None
            and detection.ue4ss.ue4ss_dir.is_dir()
        )

        switches: dict[str, MDSwitch] = {}
        content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(4),
            padding=(0, dp(8)),
        )
        content.bind(minimum_height=content.setter("height"))

        def _add_row(key: str, text: str, active: bool = False, locked: bool = False) -> MDSwitch:
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(44),
                spacing=dp(8),
            )
            sw = MDSwitch(pos_hint={"center_y": 0.5})
            sw.active = active
            if locked:
                sw.disabled = True
            lbl = MDLabel(text=text, size_hint_x=1)
            row.add_widget(sw)
            row.add_widget(lbl)
            content.add_widget(row)
            switches[key] = sw
            return sw

        # "Remove from library": custom games — toggleable (default OFF); Steam — locked off
        if is_steam_game:
            _add_row("library", "Remove from library (Steam tiles are managed automatically)",
                     active=False, locked=True)
        else:
            _add_row("library", "Remove from library", active=False, locked=False)

        if has_mods_svc:
            _add_row("mods", "Remove deployed AP mods")
        if has_sessions_svc:
            deployed_session_sw = _add_row("deployed_session", "Remove deployed session")
            sessions_sw = _add_row("sessions", "Remove session history (backups)")
        if has_ue4ss:
            ue4ss_sw = _add_row("ue4ss", "Uninstall UE4SS")
            # Uninstalling UE4SS removes ue4ss/Mods/ entirely, which encompasses
            # AP mods, deployed session, and session history. Auto-check and lock all three.
            mods_sw = switches.get("mods")
            def _on_ue4ss_toggle(inst, val):
                if mods_sw is not None:
                    mods_sw.active = val
                    mods_sw.disabled = val
                if has_sessions_svc:
                    deployed_session_sw.active = val
                    deployed_session_sw.disabled = val
                    sessions_sw.active = val
                    sessions_sw.disabled = val
            ue4ss_sw.bind(active=_on_ue4ss_toggle)

        dialog = [None]

        def _dismiss(*_):
            if dialog[0]:
                dialog[0].dismiss()

        def _on_remove(*_):
            _dismiss()
            # Collect switch states and delegate to controller
            states = {k: sw.active for k, sw in switches.items()}
            self._ctrl.execute_remove(
                profile, states,
                after_remove_cb=self._after_remove,
                after_partial_cb=self._after_partial_remove,
            )

        dialog[0] = MDDialog(
            MDDialogHeadlineText(text=f'Remove "{profile.display_name}"?'),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_dismiss),
                MDButton(MDButtonText(text="Remove Selected"), style="filled",
                         on_release=_on_remove),
            ),
        )
        dialog[0].open()

    def _after_remove(self, errors: list[str]) -> None:
        app = self._get_app()
        if app:
            app.navigate_to_library()
            # Refresh the home/library screen if it supports it
            if hasattr(app, "_home_screen") and app._home_screen:
                children = app._home_screen.children
                if children and hasattr(children[0], "refresh"):
                    children[0].refresh()
        if errors:
            self._show_snackbar(f"Removed ({len(errors)} error(s) — see console).")
        else:
            self._show_snackbar("Removed.")

    def _after_partial_remove(self, errors: list[str]) -> None:
        """Called when removal completed but game was NOT removed from library."""
        if errors:
            self._show_snackbar(f"Done ({len(errors)} error(s) — see console).")
        else:
            self._show_snackbar("Done.")
        # Refresh active panel (e.g. Sessions panel) to reflect changes
        if self._active_panel and hasattr(self._active_panel, "_refresh"):
            self._active_panel._refresh()

    def _show_snackbar(self, text: str) -> None:
        from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
        MDSnackbar(
            MDSnackbarText(text=text),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.8,
            duration=3,
        ).open()

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    def _go_home(self, *_) -> None:
        if self._active_panel and not self._active_panel.can_deactivate():
            self._pending_nav_label = "__home__"
            return
        app = self._get_app()
        if app:
            app.navigate_to_library()

    def _go_settings(self, *_) -> None:
        if self._active_panel and not self._active_panel.can_deactivate():
            self._pending_nav_label = "__settings__"
            return
        app = self._get_app()
        if app:
            app._previous_screen = "game_hub"
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
