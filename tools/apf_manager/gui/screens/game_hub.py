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

import shutil
import threading
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.screen import MDScreen

from ..widgets.log_panel import LogPanel
from ..widgets.plugin_panel import PluginPanel
from ..widgets.tip_icon_button import TipIconButton

if TYPE_CHECKING:
    from ...core.plugin_host import PluginHost, PluginContribution
    from ...core.config import APFConfig, GameProfile
    from ...core.ue4ss import UE4SSResult


class _NavRailButton(ButtonBehavior, MDBoxLayout):
    """Vertical icon + label button for the navigation rail.

    The entire container is the clickable region (via ButtonBehavior).
    The inner MDIcon is non-interactive; touch events bubble up to this widget.
    """

    def __init__(self, label: str, icon: str, on_select, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(72),
            padding=[dp(4), dp(4)],
            spacing=0,
            **kwargs,
        )
        self._nav_label = label
        self.bind(on_release=lambda *_: on_select(label))

        # Pill-shaped indicator container
        self._indicator = MDBoxLayout(
            size_hint=(1, None),
            height=dp(40),
            md_bg_color=(0, 0, 0, 0),
            radius=[dp(20)],
            padding=[dp(8), 0],
        )
        self._icon = MDIcon(
            icon=icon,
            halign="center",
            size_hint=(1, 1),
        )
        self._indicator.add_widget(self._icon)

        self._lbl = MDLabel(
            text=label,
            font_style="Label",
            role="small",
            halign="center",
            size_hint=(1, None),
            height=dp(16),
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        )
        self.add_widget(self._indicator)
        self.add_widget(self._lbl)

    def set_selected(self, selected: bool) -> None:
        self._indicator.md_bg_color = (0.2, 0.28, 0.4, 1) if selected else (0, 0, 0, 0)
        self._lbl.opacity = 0 if selected else 1


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
        self._current_detection: Optional["UE4SSResult"] = None
        self._pending_nav_label: Optional[str] = None

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

        # hub_action buttons placeholder (populated in populate_panels)
        self._action_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_x=None,
            width="0dp",
            spacing="4dp",
        )
        bar.add_widget(self._action_bar)

        # Remove game button
        remove_btn = TipIconButton(
            icon="trash-can-outline",
            tooltip_text="Remove game",
            on_release=lambda *_: self._on_remove_game(),
        )
        bar.add_widget(remove_btn)

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
        """Called when the user navigates to this game."""
        self._current_profile = profile
        self._current_detection = self._host.get_detection()
        self._game_name_lbl.text = profile.display_name
        if self._active_panel and profile:
            self._active_panel.on_activate(profile)

    # -----------------------------------------------------------------------
    # Remove game
    # -----------------------------------------------------------------------

    def _on_remove_game(self) -> None:
        if not self._current_profile:
            return
        self._show_remove_checklist(self._current_profile, self._current_detection)

    def _show_remove_checklist(self, profile: "GameProfile", detection: Optional["UE4SSResult"]) -> None:
        from kivymd.uix.button import MDButton, MDButtonText
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText,
            MDDialogContentContainer, MDDialogButtonContainer,
        )
        from kivymd.uix.selectioncontrol import MDSwitch
        from kivy.uix.widget import Widget

        is_steam_game = bool(getattr(profile, "steam_app_id", None))

        # Determine which options are available
        deploy_svc = self._host.get_service("deploy")
        has_framework = (
            deploy_svc is not None
            and bool(deploy_svc.get_framework_manifest_files(profile.game_id))
        )
        has_mods_svc = self._host.has_service("mods")
        has_sessions_svc = self._host.has_service("sessions")
        has_ue4ss = (
            detection is not None
            and detection.ue4ss_dir
            and Path(str(detection.ue4ss_dir)).is_dir()
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
        if has_framework:
            _add_row("framework", "Remove AP Framework binaries")
        # Session removal is split into two separate switches:
        #   "deployed_session" — deletes output/session_state.json
        #   "sessions"         — deletes all backups from ~/.apf_manager/sessions/<game_id>/
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
            self._execute_remove(profile, detection, switches)

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

    def _execute_remove(
        self,
        profile: "GameProfile",
        detection: Optional["UE4SSResult"],
        switches: dict,
    ) -> None:
        errors: list[str] = []

        def _run() -> None:
            # 1. Remove deployed AP mods
            if switches.get("mods") and switches["mods"].active:
                mods_svc = self._host.get_service("mods")
                deploy_svc = self._host.get_service("deploy")
                if mods_svc and deploy_svc:
                    try:
                        for mod in mods_svc.scan():
                            if mod.is_ap_mod:
                                deploy_svc.uninstall_mod(mod, profile.game_id)
                    except Exception as exc:
                        errors.append(str(exc))

            # 2. Remove AP Framework binaries
            if switches.get("framework") and switches["framework"].active:
                deploy_svc = self._host.get_service("deploy")
                if deploy_svc:
                    try:
                        for f in deploy_svc.get_framework_manifest_files(profile.game_id):
                            try:
                                Path(f).unlink(missing_ok=True)
                            except Exception as exc:
                                errors.append(f"Could not remove {Path(f).name}: {exc}")
                        manifest = (
                            Path.home() / ".apf_manager" / "deployments"
                            / f"{profile.game_id}_framework.json"
                        )
                        manifest.unlink(missing_ok=True)
                    except Exception as exc:
                        errors.append(str(exc))

            # 3a. Remove deployed session file
            if switches.get("deployed_session") and switches["deployed_session"].active:
                if detection and detection.mods_dir:
                    state_path = (
                        Path(str(detection.mods_dir))
                        / "APFrameworkMod" / "output" / "session_state.json"
                    )
                    try:
                        state_path.unlink(missing_ok=True)
                    except Exception as exc:
                        errors.append(f"Could not remove deployed session: {exc}")

            # 3b. Remove session history (backups)
            if switches.get("sessions") and switches["sessions"].active:
                sessions_svc = self._host.get_service("sessions")
                if sessions_svc:
                    try:
                        sessions_svc.clear_sessions(profile.game_id)
                    except Exception as exc:
                        errors.append(str(exc))

            # 4. Uninstall UE4SS
            if switches.get("ue4ss") and switches["ue4ss"].active:
                if detection and detection.ue4ss_dir:
                    try:
                        shutil.rmtree(str(detection.ue4ss_dir))
                    except Exception as exc:
                        errors.append(f"Could not remove UE4SS: {exc}")

            # 5. Remove from library (always — this is the committed action)
            self._config.remove_game(profile.game_id)

            Clock.schedule_once(lambda dt: self._after_remove(errors), 0)

        threading.Thread(target=_run, daemon=True).start()

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
